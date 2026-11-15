import re
import time
import uuid
from typing import Any, Dict, List, Optional
from google.genai import types


class MockGenAIModels:
    """Simulates the Gemini models endpoint for dynamic function calling and generation."""

    def __init__(self):
        self._turn_counters: Dict[str, int] = {}

    def generate_content(
        self,
        model: str,
        contents: List[Any],
        config: Optional[Any] = None,
    ) -> Any:
        # Extract user prompt and tool responses from contents
        prompt_text = ""
        has_tool_results = False
        tool_responses = []

        for c in contents:
            if hasattr(c, "parts"):
                for p in c.parts:
                    if hasattr(p, "text") and p.text:
                        prompt_text += p.text + " "
                    if hasattr(p, "function_response") and p.function_response:
                        has_tool_results = True
                        resp_dict = getattr(p.function_response, "response", {}) or {}
                        tool_responses.append((p.function_response.name, resp_dict.get("result", resp_dict)))

        prompt_lower = prompt_text.lower()

        # If we already have tool results, synthesize the final response
        if has_tool_results:
            response_sections = []
            for fn_name, res in tool_responses:
                if not isinstance(res, dict):
                    continue
                if fn_name == "find_cross_project_entities":
                    corr = res.get("correlation", {})
                    matches = corr.get("matches", [])
                    projs = sorted(list(set(m.get("project_id") for m in matches if isinstance(m, dict) and m.get("project_id"))))
                    if projs:
                        response_sections.append(f"Entity found in projects: {', '.join(projs)}.")
                    else:
                        response_sections.append("No accessible projects reference this entity.")
                elif fn_name == "discover_workspace_schema":
                    if res.get("status") == "NOT_FOUND":
                        response_sections.append("Project not found or access denied.")
                    else:
                        ws = res.get("workspace", {})
                        p_id = ws.get("project_id", "")
                        r_names = [r.get("resource_id", "") for r in ws.get("resources", []) if isinstance(r, dict)]
                        response_sections.append(f"Project {p_id} contains datasets: {', '.join(r_names)} with columns and attributes.")
                elif fn_name == "get_data_lineage":
                    if res.get("status") == "NOT_FOUND":
                        response_sections.append("Dataset not found or access denied.")
                    else:
                        lin = res.get("lineage", {})
                        d_id = lin.get("dataset_id") or lin.get("resource_id", "")
                        edges = lin.get("edges", [])
                        if lin.get("is_root") or not edges:
                            response_sections.append(f"Dataset {d_id} is a root dataset with no upstream dependencies.")
                        else:
                            srcs = sorted(list(set(e.get("source") for e in edges if isinstance(e, dict) and e.get("source"))))
                            response_sections.append(f"Dataset {d_id} is derived from: {', '.join(srcs)}.")
                elif fn_name == "query_graph":
                    response_sections.append(res.get("summary", "Memgraph graph query executed."))
                elif fn_name == "query_analytics":
                    response_sections.append(res.get("summary", "DuckDB analytics query executed."))

            if not response_sections:
                response_sections.append(
                    "**Autonomous Agent Multi-Database Assessment**:\n"
                    "Intelligence retrieved from internal DuckDB telemetry lake and Memgraph knowledge graph.\n"
                    "System anomalies and operational metrics have been correlated."
                )

            final_ans = "\n".join(response_sections)
            if "198.51.100.24" in prompt_text or "anomalies" in prompt_lower:
                final_ans += "\nAnomalies correlated with IP 198.51.100.24."

            part = types.Part.from_text(text=final_ans)
            content = types.Content(role="model", parts=[part])
            candidate = types.Candidate(content=content)
            return types.GenerateContentResponse(candidates=[candidate])

        # If identity query
        if any(kw in prompt_lower for kw in ["what agent", "who are you", "what are you", "what can you do"]):
            response_text = (
                "I am **Artemis AI**, an autonomous systems analyst and threat intelligence agent.\n\n"
                "I operate a Dynamic Agent Tool Loop with read-only access to two primary data layers:\n"
                "1. **Operational Telemetry (MinIO / DuckDB)**: Partitioned Parquet logs capturing sensor metrics, CPU load, and network telemetry.\n"
                "2. **Threat Knowledge Graph (Memgraph)**: Correlated cybersecurity indicators, anomalous IPs, and C2 relationships."
            )
            part = types.Part.from_text(text=response_text)
            content = types.Content(role="model", parts=[part])
            candidate = types.Candidate(content=content)
            return types.GenerateContentResponse(candidates=[candidate])

        # Tool calling generation based on prompt heuristics
        parts = []

        is_lineage = any(kw in prompt_lower for kw in ["lineage", "origin of", "provenance", "derived from", "where does dataset"])
        is_schema = any(kw in prompt_lower for kw in ["what datasets", "what columns", "datasets and columns", "workspace schema"])
        is_entity = any(kw in prompt_lower for kw in ["which projects", "cross project", "cross-project", "reference", "referencing", "appear across", "across projects"])
        is_analytics = any(kw in prompt_lower for kw in ["cpu", "sensor", "load", "metric", "temperature", "average", "spike", "telemetry"])
        is_graph = any(kw in prompt_lower for kw in ["anomaly", "anomalies", "threat", "indicator", "c2", "darknet", "malicious"])

        if is_lineage:
            proj_match = re.search(r"\bproject\s+([a-zA-Z0-9_\-]+)", prompt_text, re.IGNORECASE)
            ds_match = re.search(r"\bdataset\s+([a-zA-Z0-9_\-]+)", prompt_text, re.IGNORECASE)
            target_proj = proj_match.group(1) if proj_match else "default-project"
            target_ds = ds_match.group(1) if ds_match else "dataset"
            fc = types.FunctionCall(name="get_data_lineage", args={"project_id": target_proj, "dataset_id": target_ds})
            parts.append(types.Part(function_call=fc))

        elif is_schema:
            proj_match = re.search(r"\bproject\s+([a-zA-Z0-9_\-]+)", prompt_text, re.IGNORECASE)
            target_proj = proj_match.group(1) if proj_match else "default-project"
            fc = types.FunctionCall(name="discover_workspace_schema", args={"project_id": target_proj})
            parts.append(types.Part(function_call=fc))

        elif is_entity:
            val_match = re.search(r"\b(?:account|customer|subject|email|ip)\s+([a-zA-Z0-9_\-@\.]+)", prompt_text, re.IGNORECASE)
            if not val_match:
                val_match = re.search(r"\b(?:reference|referencing)\s+([a-zA-Z0-9_\-@\.]+)", prompt_text, re.IGNORECASE)
            val = val_match.group(1).rstrip("?.,") if val_match else "ACCT-99812"
            fc = types.FunctionCall(name="find_cross_project_entities", args={"value": val, "fuzzy": False})
            parts.append(types.Part(function_call=fc))

        else:
            if is_analytics:
                sql = "SELECT metric_name, AVG(value) as avg_val FROM read_parquet('s3://telemetry/**/*.parquet') GROUP BY metric_name"
                fc = types.FunctionCall(name="query_analytics", args={"sql_query": sql})
                parts.append(types.Part(function_call=fc))

            if is_graph or not is_analytics:
                cypher = "MATCH (a:ANOMALY)-[r:ASSOCIATED_WITH]->(ip) RETURN a.id, ip.id, type(r) LIMIT 10"
                fc = types.FunctionCall(name="query_graph", args={"cypher_query": cypher})
                parts.append(types.Part(function_call=fc))

        content = types.Content(role="model", parts=parts)
        candidate = types.Candidate(content=content)
        return types.GenerateContentResponse(candidates=[candidate])


class MockGenAIClient:
    """In-memory test double for google.genai.Client."""

    def __init__(self, api_key: str = "mock-api-key"):
        self.api_key = api_key
        self.models = MockGenAIModels()
