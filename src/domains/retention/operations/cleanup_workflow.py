import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

try:
    from temporalio import activity, workflow
    from temporalio.common import RetryPolicy
except ImportError:
    class _MockWorkflow:
        @staticmethod
        def defn(*args, **kwargs):
            if args and callable(args[0]):
                return args[0]
            def decorator(fn_or_cls):
                return fn_or_cls
            return decorator
        @staticmethod
        def run(fn):
            return fn
        @staticmethod
        async def execute_activity(*args, **kwargs):
            return {}
    workflow = _MockWorkflow()
    activity = _MockWorkflow()
    RetryPolicy = dict

try:
    from src.config.settings import settings
except ImportError:
    from config.settings import settings

from src.domains.retention.operations.cleanup_engine import CleanupEngine

logger = logging.getLogger("artemis.retention.cleanup_workflow")

_background_task: Optional[asyncio.Task] = None


@activity.defn(name="run_retention_cleanup_activity")
async def run_retention_cleanup_activity(args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Executes the scheduled or on-demand retention cleanup pass."""
    params = args or {}
    engine = CleanupEngine()
    run_contract = engine.evaluate_and_cleanup(
        project_id=params.get("project_id"),
        dry_run=bool(params.get("dry_run", False)),
        include_query_artifacts=bool(params.get("include_query_artifacts", True)),
        trigger_type=params.get("trigger_type", "SCHEDULED"),
        initiated_by=params.get("initiated_by", "system"),
    )
    return run_contract.model_dump(mode="json")


@workflow.defn
class RetentionCleanupWorkflow:
    """Temporal workflow executing scheduled dataset & query artifact TTL cleanup."""

    @workflow.run
    async def run(self, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )
        return await workflow.execute_activity(
            "run_retention_cleanup_activity",
            args or {"trigger_type": "SCHEDULED", "initiated_by": "system"},
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )


async def _periodic_cleanup_loop(interval_seconds: int) -> None:
    """Lightweight asyncio periodic background loop for automated TTL cleanup."""
    logger.info(f"Started periodic TTL auto-cleanup background scheduler (interval: {interval_seconds}s).")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await run_retention_cleanup_activity(
                {"trigger_type": "SCHEDULED", "initiated_by": "system_scheduler"}
            )
        except asyncio.CancelledError:
            logger.info("Periodic TTL auto-cleanup background scheduler stopped.")
            break
        except Exception as e:
            logger.warning(f"Periodic TTL auto-cleanup tick notice: {e}")


def start_background_cleanup_scheduler(interval_seconds: Optional[int] = None) -> Optional[asyncio.Task]:
    """Starts the non-blocking background TTL cleanup loop inside FastAPI lifespan."""
    global _background_task
    if _background_task is not None and not _background_task.done():
        return _background_task
    interval = interval_seconds or getattr(settings, "cleanup_interval_seconds", 300)
    try:
        loop = asyncio.get_running_loop()
        _background_task = loop.create_task(_periodic_cleanup_loop(interval))
        return _background_task
    except RuntimeError:
        return None


async def stop_background_cleanup_scheduler() -> None:
    """Cancels the background TTL cleanup task cleanly on shutdown."""
    global _background_task
    if _background_task is not None and not _background_task.done():
        _background_task.cancel()
        try:
            await _background_task
        except asyncio.CancelledError:
            pass
    _background_task = None
