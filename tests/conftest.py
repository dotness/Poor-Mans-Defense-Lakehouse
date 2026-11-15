import sys
from pathlib import Path
import pytest

root_dir = Path(__file__).resolve().parent.parent
src_dir = root_dir / "src"

for p in (str(src_dir), str(root_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

from src.config.settings import settings
from tests.fixtures.mocks import (
    MockMemgraphClient,
    MockQueryCache,
    MockAuditLogger,
    MockDockerRunner,
    MockGenAIClient,
    MockKDGGraphStore,
)


@pytest.fixture(autouse=True)
def isolate_test_buffer(tmp_path_factory):
    """Isolates the disk buffer to a temporary directory so tests never touch /tmp/artemis/buffer."""
    test_buffer = tmp_path_factory.mktemp("artemis_test_buffer")
    original_buf = settings.disk_buffer_dir
    object.__setattr__(settings, "disk_buffer_dir", str(test_buffer))
    try:
        yield
    finally:
        object.__setattr__(settings, "disk_buffer_dir", original_buf)


@pytest.fixture
def mock_memgraph_client():
    """Provides an isolated in-memory MockMemgraphClient."""
    return MockMemgraphClient()


@pytest.fixture
def mock_query_cache():
    """Provides an isolated in-memory MockQueryCache."""
    return MockQueryCache()


@pytest.fixture
def mock_audit_logger():
    """Provides an isolated in-memory MockAuditLogger."""
    return MockAuditLogger()


@pytest.fixture
def mock_docker_runner(tmp_path):
    """Provides an isolated MockDockerRunner operating in a temp workspace."""
    return MockDockerRunner(workspace_base=tmp_path / "mock_pipeline_workspace")


@pytest.fixture
def mock_genai_client():
    """Provides an isolated MockGenAIClient with simulated dynamic tool loop capabilities."""
    return MockGenAIClient()


@pytest.fixture
def mock_kdg_store(mock_memgraph_client):
    """Provides an in-memory MockKDGGraphStore for discovery domain testing."""
    return MockKDGGraphStore(memgraph_client=mock_memgraph_client)


@pytest.fixture(scope="session", autouse=True)
def cleanup_databases_after_tests():
    """Guarantees that databases (MinIO, Memgraph) are cleaned of any test data after the test session."""
    yield

    # Clean MinIO objects if any test leaked into MinIO bucket
    try:
        from minio import Minio
        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
        if client.bucket_exists(settings.minio_bucket):
            for obj in client.list_objects(settings.minio_bucket, recursive=True):
                client.remove_object(settings.minio_bucket, obj.object_name)
    except Exception:
        pass

    # Clean Memgraph graph if any test leaked into live Memgraph
    try:
        from src.services.graph.memgraph_client import MemgraphClient
        mc = MemgraphClient()
        mc.execute_query("MATCH (n) DETACH DELETE n;")
        mc.close()
    except Exception:
        pass

    # Clean PostgreSQL test projects
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
        )
        with conn.cursor() as cur:
            cur.execute("DELETE FROM projects WHERE project_id LIKE 'test-%';")
            conn.commit()
        conn.close()
    except Exception:
        pass

    # Clean residual docker runner containers
    try:
        import docker
        d_client = docker.from_env()
        for container in d_client.containers.list(all=True, filters={"name": "artemis-runner-test"}):
            try:
                container.remove(force=True)
            except Exception:
                pass
    except Exception:
        pass
