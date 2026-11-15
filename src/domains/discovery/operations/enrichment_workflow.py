import asyncio
from datetime import timedelta
import logging
from typing import Dict, Any, List, Optional

try:
    from temporalio import activity, workflow
    from temporalio.common import RetryPolicy
except ImportError:
    # Dummy decorators for environments without temporalio
    class _MockWorkflow:
        @staticmethod
        def defn(*args, **kwargs):
            if args and callable(args[0]):
                return args[0]
            def decorator(fn_or_cls):
                return fn_or_cls
            return decorator
        @staticmethod
        def run(fn): return fn
        @staticmethod
        async def execute_activity(*args, **kwargs): return {}
    workflow = _MockWorkflow()
    activity = _MockWorkflow()
    RetryPolicy = dict

try:
    from src.domains.discovery.operations.enrichment import EnrichmentService
    from src.domains.discovery.operations.job_repository import IndexJobRepository
except ImportError:
    from domains.discovery.operations.enrichment import EnrichmentService
    from domains.discovery.operations.job_repository import IndexJobRepository

logger = logging.getLogger("artemis.discovery.enrichment_workflow")


@activity.defn(name="kdg_enrich_resource_activity")
async def kdg_enrich_resource_activity(args: Dict[str, Any]) -> Dict[str, Any]:
    """Activity that executes Phase 2 semantic enrichment and updates job status."""
    job_id = args.get("job_id")
    project_id = args.get("project_id")
    resource_id = args.get("resource_id")
    samples = args.get("samples", [])
    attribute_name = args.get("attribute_name", "content")

    job_repo = IndexJobRepository()
    enrichment_svc = EnrichmentService()

    if job_id:
        job_repo.transition_status(job_id, status="running", phase="phase2_enrichment")

    try:
        result = enrichment_svc.enrich_resource(
            project_id=project_id,
            resource_id=resource_id,
            text_or_samples=samples,
            attribute_name=attribute_name,
        )

        # Phase 2b: Cross-project entity resolution
        try:
            from src.domains.discovery.operations.entity_resolution import EntityResolver
            resolver = EntityResolver()
            resolver.resolve_entities_for_resource(project_id, resource_id)
        except Exception as res_err:
            logger.warning(f"Entity resolution hook error: {res_err}")

        final_status = "completed"
        if result.get("status") == "SKIPPED_NO_AI":
            final_status = "completed"  # Phase 1 is done, Phase 2 skipped gracefully

        if job_id:
            job_repo.transition_status(job_id, status=final_status, phase="phase2_enrichment")

        return result
    except Exception as e:
        logger.error(f"Enrichment activity failed for {project_id}/{resource_id}: {e}", exc_info=True)
        if job_id:
            job_repo.record_failure(job_id, error_message=str(e))
        raise e


@workflow.defn
class KDGEnrichmentWorkflow:
    """Temporal workflow executing asynchronous Phase 2 enrichment with exponential backoff."""

    @workflow.run
    async def run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )

        result = await workflow.execute_activity(
            "kdg_enrich_resource_activity",
            args,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )
        return result


async def dispatch_enrichment_job(
    job_id: str,
    project_id: str,
    resource_id: str,
    samples: List[str],
    attribute_name: str = "content",
) -> None:
    """Dispatches enrichment workflow to Temporal, or falls back to background coroutine."""
    payload = {
        "job_id": job_id,
        "project_id": project_id,
        "resource_id": resource_id,
        "samples": samples,
        "attribute_name": attribute_name,
    }

    try:
        from src.config.settings import settings
        from temporalio.client import Client

        client = await Client.connect(f"{settings.temporal_host}:{settings.temporal_port}")
        await client.start_workflow(
            KDGEnrichmentWorkflow.run,
            payload,
            id=f"kdg-enrich-{job_id}",
            task_queue="discovery-task-queue",
        )
        logger.info(f"Dispatched Temporal enrichment workflow for {job_id}")
    except Exception as e:
        logger.info(f"Temporal unavailable or error ({e}), running enrichment asynchronously in-process.")
        # Non-blocking in-process fallback
        asyncio.create_task(kdg_enrich_resource_activity(payload))
