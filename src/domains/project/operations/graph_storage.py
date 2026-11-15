import logging
from typing import Any, Dict, List, Optional, Tuple
from src.services.graph.memgraph_client import MemgraphClient

logger = logging.getLogger("artemis.project.graph")


class ProjectGraphStorage:
    """Manages project-scoped knowledge graph operations in Memgraph."""

    def __init__(self, client: Optional[MemgraphClient] = None):
        self.client = client or MemgraphClient()

    def ingest_graph_data(
        self,
        project_id: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> Tuple[int, int]:
        """
        Ingests nodes and edges tagged with project_id.
        Each node dict format: {"name": str, "label": str, "properties": dict}
        Each edge dict format: {"source": str, "target": str, "relationship": str, "properties": dict}
        """
        nodes_imported = 0
        edges_imported = 0

        # Ingest nodes
        for node in nodes:
            name = node.get("name")
            if not name:
                continue
            label = node.get("label", "ENTITY")
            props = node.get("properties", {}).copy()
            props["project_id"] = project_id
            try:
                self.client.add_node(label=label, name=name, properties=props)
                nodes_imported += 1
            except Exception as e:
                logger.warning(f"Error ingesting node {name} for project {project_id}: {e}")

        # Ingest edges
        for edge in edges:
            src = edge.get("source")
            dst = edge.get("target")
            if not src or not dst:
                continue
            rel = edge.get("relationship", "RELATED_TO")
            props = edge.get("properties", {}).copy()
            props["project_id"] = project_id
            try:
                self.client.add_edge(
                    source_name=src,
                    target_name=dst,
                    relationship=rel,
                    properties=props,
                )
                edges_imported += 1
            except Exception as e:
                logger.warning(f"Error ingesting edge {src}->{dst} for project {project_id}: {e}")

        return nodes_imported, edges_imported

    def query_project_graph(self, project_id: str, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Executes a Cypher query scoped with project_id parameter."""
        params = parameters.copy() if parameters else {}
        params["project_id"] = project_id
        return self.client.execute_query(cypher, params)
