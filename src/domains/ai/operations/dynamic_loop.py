import logging
import time
import uuid
import warnings
from typing import Dict, Any, List, Optional

from google import genai
from google.genai import types

from src.config.settings import settings
from src.core.exceptions import ConfigurationError, ServiceUnavailableError
from src.domains.ai.operations.tools import AgentTools

# Silence SDK AFC guidance warning when manually handling function calling in multi-turn loop
warnings.filterwarnings("ignore", message=".*Direct use of automatic function calling.*")
logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google.genai.models").setLevel(logging.ERROR)

logger = logging.getLogger("artemis.ai.dynamic_loop")

MAX_AGENT_TURNS = 5


class DynamicAgentLoop:
    """Executes an autonomous dynamic tool loop using Gemini Function Calling."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        tools: Optional[AgentTools] = None,
        client: Optional[genai.Client] = None,
    ):
        self.api_key = settings.google_api_key if api_key is None else api_key
        self.model = model or settings.gemini_model
        self.tools = tools or AgentTools()

        if client is not None:
            self._client = client
        else:
            is_placeholder_key = not self.api_key or "your_google_ai_studio_api_key_here" in self.api_key
            if is_placeholder_key:
                raise ConfigurationError(
                    "Google AI Studio API key is missing or set to placeholder value.",
                    key="google_api_key",
                )
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                raise ConfigurationError(
                    f"Could not initialize Google GenAI client: {e}",
                    key="google_api_key",
                ) from e

    async def run(self, prompt: str, user_id: str = "analyst") -> Dict[str, Any]:
        """Executes the dynamic agent loop for the given prompt."""
        start_time = time.time()
        query_id = f"qry-{uuid.uuid4().hex[:8]}"

        try:
            return await self._run_live_loop(prompt, query_id, start_time)
        except Exception as e:
            logger.error(f"Live Gemini agent loop failed: {e}")
            raise ServiceUnavailableError(
                f"Dynamic agent loop execution failed: {e}",
                service="gemini",
                original_cause=e,
            ) from e

    async def _run_live_loop(self, prompt: str, query_id: str, start_time: float) -> Dict[str, Any]:
        """Multi-turn Gemini Function Calling execution loop."""
        tool_records: List[Dict[str, Any]] = []
        databases_consulted = set()

        # Tool definitions used to declare schemas to the Gemini model
        def query_analytics(sql_query: str) -> Dict[str, Any]:
            """Run read-only DuckDB SQL over telemetry Parquet files (e.g. read_parquet('s3://telemetry/**/*.parquet'))."""
            return {}

        def query_graph(cypher_query: str) -> Dict[str, Any]:
            """Run read-only Cypher queries over Memgraph knowledge graph."""
            return {}

        def get_schema_info(target: str = "all") -> Dict[str, Any]:
            """Inspect table or graph schema information."""
            return {}

        def discover_workspace_schema(project_id: str) -> Dict[str, Any]:
            """Inspect datasets, attributes, taxonomies, and entity counts in a project workspace."""
            return {}

        def find_cross_project_entities(
            value: Optional[str] = None,
            entity_type: Optional[str] = None,
            fuzzy: bool = False,
        ) -> Dict[str, Any]:
            """Correlate entities across member projects, returning metadata only."""
            return {}

        def get_data_lineage(
            project_id: str,
            dataset_id: str,
            depth: int = 10,
        ) -> Dict[str, Any]:
            """Trace data provenance and derivation history for a dataset."""
            return {}

        tool_map = {
            "query_analytics": self.tools.query_analytics,
            "query_graph": self.tools.query_graph,
            "get_schema_info": self.tools.get_schema_info,
            "discover_workspace_schema": self.tools.discover_workspace_schema,
            "find_cross_project_entities": self.tools.find_cross_project_entities,
            "get_data_lineage": self.tools.get_data_lineage,
        }

        # Setup initial content and configuration
        system_instruction = (
            "You are Artemis AI, an autonomous cybersecurity and systems analyst agent with universal domain-agnostic knowledge discovery capabilities.\n"
            "You have access to internal databases and discovery tools:\n"
            "- 'query_graph': Run read-only Cypher queries over Memgraph property graph for cyber threats, anomalies, IP addresses, domains, and threat actors.\n"
            "- 'query_analytics': Run read-only DuckDB SQL over telemetry Parquet files in MinIO.\n"
            "- 'get_schema_info': Inspect table columns or graph schema labels ('analytics', 'graph', or 'all').\n"
            "- 'discover_workspace_schema': Inspect datasets, attributes, taxonomies, and entity counts in a project workspace.\n"
            "- 'find_cross_project_entities': Correlate entities across projects you have access to by value or entity_type.\n"
            "- 'get_data_lineage': Trace data provenance and derivation history for a dataset.\n"
            "Security Rule: You can only access project workspaces and entities for projects the current user is an authorized member of. Projects outside membership leave zero trace.\n"
            "Always ground your final response strictly on retrieved database records."
        )

        config = types.GenerateContentConfig(
            tools=[
                query_analytics,
                query_graph,
                get_schema_info,
                discover_workspace_schema,
                find_cross_project_entities,
                get_data_lineage,
            ],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            system_instruction=system_instruction,
            temperature=0.1,
        )

        contents: List[Any] = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        final_text = ""

        for turn in range(MAX_AGENT_TURNS):
            response = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            # Check if model requested function calls
            has_func_calls = False
            candidate_content = response.candidates[0].content if response.candidates else None
            if candidate_content and candidate_content.parts:
                contents.append(candidate_content)
                for part in candidate_content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        has_func_calls = True
                        func_name = part.function_call.name
                        func_args = dict(part.function_call.args) if part.function_call.args else {}
                        call_id = f"call-{uuid.uuid4().hex[:6]}"

                        t_start = time.time()
                        if func_name in tool_map:
                            tool_fn = tool_map[func_name]
                            tool_res = await tool_fn(**func_args)
                            duration_ms = int((time.time() - t_start) * 1000)

                            if func_name == "query_analytics":
                                databases_consulted.add("duckdb")
                            elif func_name in ("query_graph", "discover_workspace_schema", "find_cross_project_entities", "get_data_lineage"):
                                databases_consulted.add("memgraph")

                            tool_records.append({
                                "call_id": call_id,
                                "tool_name": func_name,
                                "arguments": func_args,
                                "duration_ms": duration_ms,
                                "summary": tool_res.get("summary"),
                                "error": tool_res.get("error"),
                            })

                            # Feed function response back with role="user"
                            contents.append(
                                types.Content(
                                    role="user",
                                    parts=[
                                        types.Part.from_function_response(
                                            name=func_name,
                                            response={"result": tool_res.get("data", tool_res)},
                                        )
                                    ],
                                )
                            )
                        else:
                            contents.append(
                                types.Content(
                                    role="user",
                                    parts=[
                                        types.Part.from_function_response(
                                            name=func_name,
                                            response={"error": f"Unknown tool '{func_name}'"},
                                        )
                                    ],
                                )
                            )

            if not has_func_calls:
                final_text = response.text or ""
                break

        if not final_text and tool_records:
            try:
                synth_contents = contents + [
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text="Synthesize a concise, direct summary answering the original question based strictly on the retrieved database records above. If both databases returned 0 records or are empty, explicitly explain that both the DuckDB telemetry lake and Memgraph knowledge graph are currently empty.")],
                    )
                ]
                synth_config = types.GenerateContentConfig(
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    temperature=0.1,
                )
                final_response = self._client.models.generate_content(
                    model=self.model,
                    contents=synth_contents,
                    config=synth_config,
                )
                final_text = final_response.text or ""

            except Exception as e:
                logger.debug(f"Final synthesis call fallback: {e}")

        if not final_text and tool_records:
            summaries = [f"- {tc['tool_name']}: {tc.get('summary') or 'Executed'}" for tc in tool_records]
            final_text = "Retrieved intelligence from consulted databases:\n" + "\n".join(summaries)
        elif not final_text:
            final_text = "Both the DuckDB analytics lake and the Memgraph knowledge graph are currently empty."

        elapsed_total = int((time.time() - start_time) * 1000)
        return {
            "query_id": query_id,
            "response": final_text or "No data available to answer the query.",
            "model_used": self.model,
            "cached": False,
            "duration_ms": elapsed_total,
            "context": [tc.get("arguments", {}) for tc in tool_records],
            "tool_calls": tool_records,
            "databases_consulted": sorted(list(databases_consulted)),
        }
