import logging
from typing import Optional
from temporalio.client import Client

try:
    from src.config.settings import settings
except ImportError:
    from config.settings import settings

logger = logging.getLogger("artemis.temporal")

_temporal_client: Optional[Client] = None


async def get_temporal_client() -> Optional[Client]:
    """Retrieves or establishes a singleton connection to the Temporal workflow engine."""
    global _temporal_client
    if _temporal_client is not None:
        return _temporal_client

    hosts_to_try = [settings.temporal_host]
    if settings.temporal_host in ("localhost", "127.0.0.1") and "127.0.1.1" not in hosts_to_try:
        hosts_to_try.append("127.0.1.1")

    for h in hosts_to_try:
        target = f"{h}:{settings.temporal_port}"
        try:
            logger.info(f"Connecting to Temporal workflow engine at {target} (namespace: {settings.temporal_namespace})...")
            _temporal_client = await Client.connect(
                target,
                namespace=settings.temporal_namespace,
            )
            logger.info(f"Successfully connected to Temporal server at {target}.")
            return _temporal_client
        except Exception as e:
            logger.debug(f"Failed to connect to Temporal at {target}: {e}")

    logger.warning(
        f"Temporal server at {settings.temporal_host}:{settings.temporal_port} is unreachable. "
        "Workflows will fall back to local direct execution."
    )
    return None


def reset_temporal_client() -> None:
    """Resets the singleton connection (primarily for testing)."""
    global _temporal_client
    _temporal_client = None
