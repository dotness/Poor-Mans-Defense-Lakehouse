import time
import json
import asyncio
import logging
from typing import Dict, Any, Optional, List

from src.domains.ai.operations.guardrails import (
    validate_readonly_sql,
    validate_readonly_cypher,
    validate_safe_identifier,
)
from src.domains.analytics.facade.analytics import AnalyticsFacade
from src.domains.analytics.models.contract.query import QueryRequestContract
from src.domains.graph.facade.graph import GraphFacade

logger = logging.getLogger("artemis.ai.tools")

TOOL_TIMEOUT_SECONDS = 5.0


class AgentTools:
    """Encapsulates autonomous database tools accessible to the AI Agent."""

    def __init__(
        self,
        analytics_facade: Optional[AnalyticsFacade] = None,
        graph_facade: Optional[GraphFacade] = None,
        discovery_facade: Optional[Any] = None,
        user: Optional[Any] = None,
    ):
        self.user = user
        self.analytics_facade = analytics_facade or AnalyticsFacade()
        self.graph_facade = graph_facade or GraphFacade()
        try:
            from src.domains.discovery.facade.discovery import DiscoveryFacade
            self.discovery_facade = discovery_facade or DiscoveryFacade(user=user)
        except ImportError:
            from domains.discovery.facade.discovery import DiscoveryFacade
            self.discovery_facade = discovery_facade or DiscoveryFacade(user=user)

    async def discover_workspace_schema(self, project_id: str) -> Dict[str, Any]:
        """Inspects datasets, attributes, taxonomies, and entity counts in a project workspace."""
        start_time = time.time()
        try:
            safe_project_id = validate_safe_identifier(project_id)
            summary = await asyncio.wait_for(
                self.discovery_facade.get_workspace_knowledge(safe_project_id, user=self.user),
                timeout=TOOL_TIMEOUT_SECONDS,
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            if summary is None:
                return {
                    "status": "NOT_FOUND",
                    "duration_ms": elapsed_ms,
                    "message": f"Project workspace '{project_id}' not found or access denied.",
                }
            return {
                "status": "SUCCESS",
                "duration_ms": elapsed_ms,
                "workspace": summary.model_dump(mode="json"),
            }
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"discover_workspace_schema error: {e}")
            return {
                "status": "ERROR",
                "error": str(e),
                "duration_ms": elapsed_ms,
            }

    async def find_cross_project_entities(
        self,
        value: Optional[str] = None,
        entity_type: Optional[str] = None,
        fuzzy: bool = False,
    ) -> Dict[str, Any]:
        """Correlates entities across member projects, returning metadata only."""
        start_time = time.time()
        try:
            res = await asyncio.wait_for(
                self.discovery_facade.find_entities(value=value, entity_type=entity_type, fuzzy=fuzzy, user=self.user),
                timeout=TOOL_TIMEOUT_SECONDS,
            )
            elapsed_ms = int((time.time() - start_time) * 1000)
            return {
                "status": "SUCCESS",
                "duration_ms": elapsed_ms,
                "correlation": res.model_dump(mode="json"),
            }
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"find_cross_project_entities error: {e}")
            return {
                "status": "ERROR",
                "error": str(e),
                "duration_ms": elapsed_ms,
            }

    async def get_data_lineage(
        self,
        project_id: str,
        dataset_id: str,
        depth: int = 10,
    ) -> Dict[str, Any]:
        """Traces data provenance and derivation history for a dataset."""
        start_time = time.time()
        try:
            safe_project_id = validate_safe_identifier(project_id)
            safe_dataset_id = validate_safe_identifier(dataset_id)
            lineage = await asyncio.wait_for(
                self.discovery_facade.get_lineage(project_id=safe_project_id, dataset_id=safe_dataset_id, depth=depth, user=self.user),
                timeout=TOOL_TIMEOUT_SECONDS,
            )
            elapsed_ms = int((time.time() - start_time) * 1000)
            if lineage is None or len(lineage.nodes) == 0:
                return {
                    "status": "NOT_FOUND",
                    "duration_ms": elapsed_ms,
                    "message": f"Dataset '{safe_dataset_id}' in project '{safe_project_id}' not found or access denied.",
                }
            return {
                "status": "SUCCESS",
                "duration_ms": elapsed_ms,
                "lineage": lineage.model_dump(mode="json"),
            }
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"get_data_lineage error: {e}")
            return {
                "status": "ERROR",
                "error": str(e),
                "duration_ms": elapsed_ms,
            }

    async def query_analytics(self, sql_query: str) -> Dict[str, Any]:
        """Executes a read-only DuckDB SQL analytical query against MinIO Parquet telemetry partitions.
        
        Args:
            sql_query: Read-only SQL query (e.g. SELECT metric_name, AVG(value) FROM read_parquet('s3://telemetry/**/*.parquet') GROUP BY metric_name).
        """
        start_time = time.time()
        try:
            validated_sql = validate_readonly_sql(sql_query)
            req = QueryRequestContract(sql=validated_sql, format="json")
            resp = await asyncio.wait_for(self.analytics_facade.execute_query(req), timeout=TOOL_TIMEOUT_SECONDS)
            elapsed_ms = int((time.time() - start_time) * 1000)
            rows = json.loads(resp.formatted_output) if isinstance(resp.formatted_output, str) and resp.formatted_output.strip().startswith("[") else []
            count = len(rows) if isinstance(rows, list) else 0
            summary = (
                f"Retrieved {count} rows from DuckDB analytics"
                if count > 0
                else "DuckDB telemetry lake query completed successfully with 0 records (lake is empty)"
            )
            return {
                "status": "SUCCESS",
                "database": "duckdb",
                "row_count": count,
                "data": rows[:50] if isinstance(rows, list) else rows,
                "duration_ms": elapsed_ms,
                "summary": summary,
            }
        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            err_msg = str(e)
            if "No files found that match the pattern" in err_msg or "No files match" in err_msg:
                return {
                    "status": "SUCCESS",
                    "database": "duckdb",
                    "row_count": 0,
                    "data": [],
                    "duration_ms": elapsed_ms,
                    "summary": "The DuckDB telemetry lake is currently empty (no parquet files stored in MinIO yet)",
                }
            logger.warning(f"query_analytics execution error: {e}")
            return {
                "status": "ERROR",
                "database": "duckdb",
                "error": str(e),
                "duration_ms": elapsed_ms,
                "summary": f"DuckDB query failed: {e}",
            }

    async def query_graph(self, cypher_query: str) -> Dict[str, Any]:
        """Executes a read-only Cypher query against the Memgraph threat intelligence knowledge graph.
        
        Args:
            cypher_query: Read-only Cypher query (e.g. MATCH (a:ANOMALY)-[r:ASSOCIATED_WITH]->(b) RETURN a.id, b.id, type(r) LIMIT 20).
        """
        start_time = time.time()
        try:
            validated_cypher = validate_readonly_cypher(cypher_query)
            raw_results = await asyncio.wait_for(
                asyncio.to_thread(self.graph_facade.client.execute_query, validated_cypher),
                timeout=TOOL_TIMEOUT_SECONDS,
            )
            try:
                from src.domains.retention.operations.query_interceptor import QueryTTLInterceptor
                raw_results = QueryTTLInterceptor().filter_graph_records(raw_results)
            except Exception:
                pass

            elapsed_ms = int((time.time() - start_time) * 1000)
            summary = (
                f"Retrieved {len(raw_results)} graph records from Memgraph"
                if raw_results
                else "Memgraph knowledge graph query executed with 0 records (knowledge graph is empty)"
            )
            return {
                "status": "SUCCESS",
                "database": "memgraph",
                "record_count": len(raw_results),
                "data": raw_results[:50],
                "duration_ms": elapsed_ms,
                "summary": summary,
            }

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"query_graph execution error: {e}")
            return {
                "status": "ERROR",
                "database": "memgraph",
                "error": str(e),
                "duration_ms": elapsed_ms,
                "summary": f"Memgraph query failed: {e}",
            }

    async def get_schema_info(self, target: str = "all") -> Dict[str, Any]:
        """Returns schemas and ontology for analytics tables and graph nodes to guide query formulation.
        
        Args:
            target: 'analytics', 'graph', or 'all'
        """
        schemas = {}
        if target in ("analytics", "all"):
            schemas["duckdb_telemetry"] = {
                "table_pattern": "read_parquet('s3://telemetry/**/*.parquet')",
                "columns": {
                    "event_id": "VARCHAR (UUID)",
                    "timestamp": "VARCHAR / TIMESTAMP (ISO-8601)",
                    "device_id": "VARCHAR (sensor/gateway ID)",
                    "metric_name": "VARCHAR (e.g. cpu_load, memory_used, temperature)",
                    "value": "DOUBLE",
                    "unit": "VARCHAR (percent, celsius, mb)",
                    "metadata": "VARCHAR / JSON",
                },
                "example_query": "SELECT metric_name, AVG(value) FROM read_parquet('s3://telemetry/**/*.parquet') GROUP BY metric_name",
            }

        if target in ("graph", "all"):
            schemas["memgraph_knowledge_graph"] = {
                "node_labels": ["Entity", "Incident", "Indicator", "ANOMALY"],
                "relationships": ["ASSOCIATED_WITH", "TRIGGERED_BY", "DETECTED_ON"],
                "node_properties": ["id", "type", "description", "severity", "timestamp"],
                "example_query": "MATCH (a:ANOMALY)-[r:ASSOCIATED_WITH]->(b) RETURN a.id, b.id LIMIT 10",
            }

        return {"status": "SUCCESS", "schemas": schemas}
