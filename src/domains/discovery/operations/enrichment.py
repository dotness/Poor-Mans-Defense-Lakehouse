import json
import logging
import os
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

try:
    from src.config.settings import settings
    from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
except ImportError:
    from config.settings import settings
    from domains.discovery.operations.kdg_graph_store import KDGGraphStore

logger = logging.getLogger("artemis.discovery.enrichment")


class EnrichmentService:
    """Phase 2 Semantic Enrichment using Gemini open-vocabulary NER and taxonomy mapping."""

    DEFAULT_TAXONOMIES = [
        {"name": "Taxonomy:PatientIdentifier", "description": "Subject, patient, clinical identifier"},
        {"name": "Taxonomy:ContactInformation", "description": "Email, phone number, physical address"},
        {"name": "Taxonomy:ClinicalNote", "description": "Clinical narrative, doctor consultation, discharge summary"},
        {"name": "Taxonomy:FinancialAccount", "description": "Bank account, invoice number, credit balance"},
        {"name": "Taxonomy:VitalSigns", "description": "Blood pressure, heart rate, body temperature"},
        {"name": "Taxonomy:DiagnosisCode", "description": "ICD-10, SNOMED diagnostic classification code"},
    ]

    def __init__(
        self,
        graph_store: Optional[KDGGraphStore] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        high_threshold: Optional[float] = None,
        low_threshold: Optional[float] = None,
    ):
        self.graph_store = graph_store or KDGGraphStore()
        raw_key = api_key if api_key is not None else (getattr(settings, "google_api_key", None) or os.getenv("GEMINI_API_KEY", ""))
        self.api_key = raw_key
        self.model = model or getattr(settings, "gemini_model", "gemini-2.5-flash")
        self.high_threshold = high_threshold or getattr(settings, "discovery_taxonomy_high_threshold", 0.85)
        self.low_threshold = low_threshold or getattr(settings, "discovery_taxonomy_low_threshold", 0.70)

        self._cache: Dict[str, Any] = {}
        self._client: Optional[Any] = None

        if self.is_configured() and genai is not None:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini Client: {e}")

    def is_configured(self) -> bool:
        """Returns True if a valid Gemini API key is configured."""
        if not self.api_key:
            return False
        if "your_google_ai_studio_api_key_here" in self.api_key:
            return False
        return True

    def evaluate_similarity(self, score: float) -> Dict[str, Any]:
        """Evaluates taxonomy similarity score against threshold boundaries."""
        if score >= self.high_threshold:
            return {"mapped": True, "low_confidence": False, "confidence": round(score, 4)}
        elif score >= self.low_threshold:
            return {"mapped": True, "low_confidence": True, "confidence": round(score, 4)}
        else:
            return {"mapped": False, "low_confidence": True, "confidence": round(score, 4)}

    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Computes cosine similarity between two float vectors using numpy."""
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _call_gemini_ner(self, text: str) -> str:
        """Calls Gemini API to perform open-vocabulary NER on the given text."""
        if not self._client:
            return "[]"

        prompt = f"""
You are an entity recognition assistant. Extract named entities (such as people, organizations, identifiers, medical conditions, medications, or locations) from the following text.
Respond with a STRICT JSON array of objects, with no markdown code blocks or text outside the JSON:
[
  {{"entity": "Entity Name", "type": "Category", "confidence": 0.95}}
]

Text:
{text[:4000]}
"""
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            return response.text or "[]"
        except Exception as e:
            logger.error(f"Gemini NER generation failed: {e}")
            return "[]"

    def _compute_taxonomy_similarity(self, text: str) -> Tuple[Optional[str], float]:
        """Maps text to the best matching semantic taxonomy concept."""
        # Simple heuristic fallback or embedding similarity
        text_lower = text.lower()
        best_name = None
        best_score = 0.0

        for tax in self.DEFAULT_TAXONOMIES:
            name = tax["name"]
            desc = tax["description"].lower()
            overlap = sum(1 for w in desc.split() if w.strip(",.") in text_lower)
            if overlap > 0:
                score = min(0.70 + (overlap * 0.1), 0.95)
                if score > best_score:
                    best_score = score
                    best_name = name

        if best_name and best_score >= self.low_threshold:
            return best_name, best_score
        return None, 0.0

    def enrich_resource(
        self,
        project_id: str,
        resource_id: str,
        text_or_samples: List[str],
        attribute_name: Optional[str] = "content",
    ) -> Dict[str, Any]:
        """Runs open-vocabulary NER and taxonomy mapping for a resource attribute."""
        if not self.is_configured():
            logger.info(f"Skipping AI enrichment for {project_id}/{resource_id}: No API key")
            return {
                "status": "SKIPPED_NO_AI",
                "reason": "No Gemini API key configured",
                "resource_id": resource_id,
            }

        combined_text = " ".join([str(s) for s in text_or_samples if s])
        if not combined_text.strip():
            return {
                "status": "SUCCESS",
                "resource_id": resource_id,
                "extracted_entities": [],
                "taxonomy_mapping": None,
                "confidence": 0.0,
            }

        # Check cache
        cache_key = f"ner:{hash(combined_text[:1000])}"
        if cache_key in self._cache:
            ner_raw = self._cache[cache_key]
        else:
            ner_raw = self._call_gemini_ner(combined_text)
            self._cache[cache_key] = ner_raw

        # Parse NER entities
        extracted = []
        try:
            cleaned = ner_raw.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            parsed = json.loads(cleaned.strip())
            if isinstance(parsed, list):
                extracted = parsed
        except Exception as e:
            logger.warning(f"Could not parse NER JSON response: {e}")

        # Merge extracted entities into graph store
        for item in extracted:
            ent_val = str(item.get("entity", "")).strip()
            ent_type = str(item.get("type", "GenericEntity")).strip()
            if ent_val:
                self.graph_store.merge_generic_entity(
                    project_id=project_id,
                    resource_id=resource_id,
                    attribute_name=attribute_name or "content",
                    entity_type=ent_type,
                    value=ent_val,
                    normalized_value=ent_val.lower(),
                )

        # Taxonomy mapping
        tax_name, tax_score = self._compute_taxonomy_similarity(combined_text)
        if tax_name:
            eval_res = self.evaluate_similarity(tax_score)
            if eval_res["mapped"]:
                self.graph_store.merge_semantic_taxonomy(
                    concept_id=tax_name.lower().replace(":", "-"),
                    name=tax_name,
                )
                self.graph_store.map_attribute_to_taxonomy(
                    project_id=project_id,
                    resource_id=resource_id,
                    attribute_name=attribute_name or "content",
                    taxonomy_name=tax_name,
                    confidence=eval_res["confidence"],
                    low_confidence=eval_res["low_confidence"],
                )

        return {
            "status": "SUCCESS",
            "resource_id": resource_id,
            "extracted_entities": extracted,
            "taxonomy_mapping": tax_name,
            "confidence": tax_score,
        }
