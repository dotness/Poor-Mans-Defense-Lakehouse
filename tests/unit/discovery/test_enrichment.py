from unittest.mock import MagicMock, patch
import pytest
from src.domains.discovery.operations.enrichment import EnrichmentService
from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
from src.services.graph.memgraph_client import MemgraphClient


@pytest.fixture
def mock_graph_store(mock_kdg_store):
    return mock_kdg_store


def test_enrichment_skipped_no_ai_when_no_api_key(mock_graph_store):
    with patch.dict("os.environ", {}, clear=True):
        service = EnrichmentService(graph_store=mock_graph_store, api_key="")
        result = service.enrich_resource(
            project_id="test-proj",
            resource_id="patients",
            text_or_samples=["sample data"],
        )
        assert result["status"] == "SKIPPED_NO_AI"
        assert result.get("reason") == "No Gemini API key configured"


def test_taxonomy_cosine_thresholds():
    service = EnrichmentService(graph_store=MagicMock(), api_key="dummy-key")

    # High match >= 0.85
    high_match = service.evaluate_similarity(score=0.92)
    assert high_match["mapped"] is True
    assert high_match["low_confidence"] is False
    assert high_match["confidence"] == 0.92

    # Medium match 0.70 <= score < 0.85
    med_match = service.evaluate_similarity(score=0.76)
    assert med_match["mapped"] is True
    assert med_match["low_confidence"] is True
    assert med_match["confidence"] == 0.76

    # Low match < 0.70
    low_match = service.evaluate_similarity(score=0.62)
    assert low_match["mapped"] is False


def test_mocked_gemini_ner_and_mapping(mock_graph_store):
    service = EnrichmentService(graph_store=mock_graph_store, api_key="test-api-key")

    mock_llm_response = """
    [
        {"entity": "Dr. Sarah Adams", "type": "Person", "confidence": 0.95},
        {"entity": "Metformin 500mg", "type": "Medication", "confidence": 0.88}
    ]
    """

    with patch.object(service, "_call_gemini_ner", return_value=mock_llm_response):
        with patch.object(service, "_compute_taxonomy_similarity", return_value=("Taxonomy:ClinicalNote", 0.91)):
            result = service.enrich_resource(
                project_id="test-proj",
                resource_id="clinical_note_1",
                text_or_samples=["Patient was examined by Dr. Sarah Adams. Prescribed Metformin 500mg."],
                attribute_name="content",
            )

            assert result["status"] == "SUCCESS"
            assert len(result["extracted_entities"]) == 2
            assert result["taxonomy_mapping"] == "Taxonomy:ClinicalNote"
            assert result["confidence"] == 0.91
