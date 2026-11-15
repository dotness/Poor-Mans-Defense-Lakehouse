import pytest
from src.domains.discovery.operations.job_repository import IndexJobRepository
from src.domains.project.operations.project_manager import ProjectManager
from src.domains.project.models.contract.project import ProjectCreateContract


@pytest.fixture
def test_project():
    pm = ProjectManager()
    proj_id = "test-job-repo-proj"
    try:
        pm.delete_project(proj_id)
    except Exception:
        pass
    pm.create_project(ProjectCreateContract(project_id=proj_id, name="Job Repo Test"))
    yield proj_id
    try:
        pm.delete_project(proj_id)
    except Exception:
        pass


def test_job_lifecycle(test_project):
    repo = IndexJobRepository()
    repo.ensure_tables()

    # 1. Create Job
    job = repo.create_job(project_id=test_project, resource_id="metrics_raw", phase="structural")
    assert job.project_id == test_project
    assert job.resource_id == "metrics_raw"
    assert job.status == "pending"
    assert job.attempts == 1

    # 2. Get Job
    fetched = repo.get_job(job.job_id)
    assert fetched is not None
    assert fetched.job_id == job.job_id

    # 3. Transition Status to running
    running = repo.update_status(job.job_id, status="running")
    assert running is not None
    assert running.status == "running"

    # 4. Fail and increment attempt (attempt 2 <= 3 -> pending)
    failed = repo.update_status(job.job_id, status="failed", error="Connection timeout")
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == "Connection timeout"

    retry1 = repo.increment_attempt(job.job_id, max_attempts=3)
    assert retry1 is not None
    assert retry1.attempts == 2
    assert retry1.status == "pending"

    # 5. Increment until exhausted (attempt 3 -> pending, attempt 4 > 3 -> failed)
    retry2 = repo.increment_attempt(job.job_id, max_attempts=3)
    assert retry2.attempts == 3
    assert retry2.status == "pending"

    exhausted = repo.increment_attempt(job.job_id, max_attempts=3)
    assert exhausted.attempts == 4
    assert exhausted.status == "failed"

    # 6. List Jobs
    all_jobs = repo.list_jobs(test_project)
    assert len(all_jobs) >= 1
    failed_jobs = repo.list_jobs(test_project, status="failed")
    assert any(j.job_id == job.job_id for j in failed_jobs)
