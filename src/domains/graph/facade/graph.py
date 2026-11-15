import logging
from typing import List, Dict, Any, Optional
from src.base.facade import DomainFacade
from src.domains.graph.models.contract.graph import (
    GraphNodeContract,
    GraphEdgeContract,
    OsintImportResultContract,
    RelatedEntitiesResultContract,
)
from src.services.graph.memgraph_client import MemgraphClient
from src.services.graph.osint_importer import OsintImporter

logger = logging.getLogger(__name__)


class GraphFacade(DomainFacade):
    """Facade for Memgraph Knowledge Graph and SpiderFoot OSINT ingestion."""

    def __init__(
        self,
        client: Optional[MemgraphClient] = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.client = client or MemgraphClient()
        self.importer = OsintImporter(client=self.client)

    async def add_node(self, node: GraphNodeContract) -> bool:
        """Upserts a graph node via openCypher MERGE."""
        return self.client.add_node(
            label=node.label,
            name=node.name,
            properties=node.properties,
            confidence=node.confidence,
        )

    async def add_edge(self, edge: GraphEdgeContract) -> bool:
        """Upserts a directed relationship between two entities."""
        return self.client.add_edge(
            source_name=edge.source,
            target_name=edge.target,
            relationship=edge.relationship,
            properties=edge.properties,
        )

    async def import_spiderfoot_json(self, raw_json_data: str) -> OsintImportResultContract:
        """Parses and ingests a SpiderFoot reconnaissance export into Memgraph via workflow."""
        from src.domains.graph.operations.import_osint import OsintImportOperation, OsintImportWorkflow
        from src.base.temporal import get_temporal_client
        import time

        temporal_client = await get_temporal_client()
        if temporal_client:
            try:
                import asyncio
                summary = await asyncio.wait_for(
                    temporal_client.execute_workflow(
                        OsintImportWorkflow.run,
                        raw_json_data,
                        id=f"osint-import-{int(time.time()*1000)}",
                        task_queue="artemis-queue",
                    ),
                    timeout=3.0,
                )
            except Exception as e:
                logger.warning(f"Temporal execution error or worker timeout ({e}), executing via direct operation.")
                operation = OsintImportOperation(client=self.client)
                summary = await operation.run(raw_json_data=raw_json_data)
        else:
            operation = OsintImportOperation(client=self.client)
            summary = await operation.run(raw_json_data=raw_json_data)

        return OsintImportResultContract(
            nodes_imported=summary.get("nodes_imported", 0),
            edges_imported=summary.get("edges_imported", 0),
            status=summary.get("status", "SUCCESS"),
        )

    def find_related_entities(self, query_term: str, limit: int = 10) -> RelatedEntitiesResultContract:
        """Retrieves correlated nodes and edges for intelligence RAG."""
        results = self.client.find_related_entities(query_term, limit=limit)
        return RelatedEntitiesResultContract(
            query_term=query_term,
            entities=results,
        )
