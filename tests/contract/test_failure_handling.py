import pytest
from unittest.mock import MagicMock
from src.core.exceptions import ConfigurationError, ServiceUnavailableError
from src.domains.ai.operations.dynamic_loop import DynamicAgentLoop
from src.services.ai.genai_service import GenAIService


def test_dynamic_agent_loop_missing_api_key():
    """Validates that DynamicAgentLoop raises ConfigurationError when API key is missing/placeholder."""
    with pytest.raises(ConfigurationError):
        DynamicAgentLoop(api_key="")

    with pytest.raises(ConfigurationError):
        DynamicAgentLoop(api_key="your_google_ai_studio_api_key_here")


def test_genai_service_missing_api_key():
    """Validates that GenAIService raises ConfigurationError when API key is missing/placeholder."""
    with pytest.raises(ConfigurationError):
        GenAIService(api_key="")


@pytest.mark.asyncio
async def test_dynamic_agent_loop_service_unavailable():
    """Validates that DynamicAgentLoop raises ServiceUnavailableError when Gemini API fails."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("API quota exceeded or 503")

    loop = DynamicAgentLoop(api_key="valid-test-key", client=mock_client)
    with pytest.raises(ServiceUnavailableError):
        await loop.run("What are the recent anomalies?")


def test_genai_service_service_unavailable(mock_query_cache, mock_audit_logger):
    """Validates that GenAIService raises ServiceUnavailableError when Gemini API fails."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("API service 500 error")

    service = GenAIService(
        api_key="valid-test-key",
        client=mock_client,
        cache=mock_query_cache,
        audit_logger=mock_audit_logger,
    )
    with pytest.raises(ServiceUnavailableError):
        service.ask("What is this threat?")
