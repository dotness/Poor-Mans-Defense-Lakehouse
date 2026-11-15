import logging
from typing import Dict, Any, List, Tuple
from datetime import timedelta
from temporalio import activity, workflow

from src.base.operations import BaseStep, BaseOperation
from src.domains.graph.models.contract.graph import GraphNodeContract, GraphEdgeContract
from src.services.graph.memgraph_client import MemgraphClient
from src.services.graph.osint_importer import OsintImporter

logger = logging.getLogger("artemis.domains.graph.operations.import_osint")


# ============================================================================
# Activity Steps
# ============================================================================

class ParseSpiderfootStep(BaseStep):
    """Parses raw SpiderFoot reconnaissance JSON data into node/edge graph tuples."""

    def __init__(self, importer: OsintImporter = None):
        super().__init__("ParseSpiderfootStep")
        self.importer = importer or OsintImporter()

    @activity.defn(name="parse_spiderfoot_activity")
    async def execute_activity(self, raw_json_data: str) -> Dict[str, Any]:
        return await self.execute({"raw_json_data": raw_json_data})

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        raw_json_data = context.get("raw_json_data", "[]")
        nodes, edges = self.importer.parse_spiderfoot_json(raw_json_data)
        return {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }


class ImportToMemgraphStep(BaseStep):
    """Persists parsed OSINT entities and relationships into Memgraph."""

    def __init__(self, importer: OsintImporter = None):
        super().__init__("ImportToMemgraphStep")
        self.importer = importer or OsintImporter()

    @activity.defn(name="import_to_memgraph_activity")
    async def execute_activity(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.execute(payload)

    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        nodes_raw = context.get("nodes", [])
        edges_raw = context.get("edges", [])

        summary = self.importer.import_to_memgraph(nodes_raw, edges_raw)
        return {
            "status": "SUCCESS",
            "nodes_imported": summary.get("nodes_imported", len(nodes_raw)),
            "edges_imported": summary.get("edges_imported", len(edges_raw)),
        }


# ============================================================================
# Temporal Workflow Definition
# ============================================================================

@workflow.defn
class OsintImportWorkflow:
    """Temporal workflow executing the durable OSINT import sequence."""

    @workflow.run
    async def run(self, raw_json_data: str) -> Dict[str, Any]:
        # Step 1: Parse SpiderFoot JSON
        parsed_res = await workflow.execute_activity(
            "parse_spiderfoot_activity",
            raw_json_data,
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Step 2: Import into Memgraph
        import_res = await workflow.execute_activity(
            "import_to_memgraph_activity",
            parsed_res,
            start_to_close_timeout=timedelta(minutes=2),
        )

        return import_res


# ============================================================================
# Standalone Operation Runner
# ============================================================================

class OsintImportOperation(BaseOperation):
    """Coordinates OSINT parsing and import steps."""

    def __init__(self, client: MemgraphClient = None):
        super().__init__("OsintImportOperation")
        importer = OsintImporter(client=client)
        self.parse_step = ParseSpiderfootStep(importer=importer)
        self.import_step = ImportToMemgraphStep(importer=importer)
        self.add_step(self.parse_step)
        self.add_step(self.import_step)

    async def run(self, **kwargs) -> Dict[str, Any]:
        raw_json_data = kwargs.get("raw_json_data", "[]")
        parsed = await self.parse_step.execute({"raw_json_data": raw_json_data})
        import_res = await self.import_step.execute(parsed)
        return import_res
