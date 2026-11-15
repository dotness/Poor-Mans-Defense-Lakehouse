import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


class MockMemgraphClient:
    """In-memory test double for MemgraphClient."""

    def __init__(
        self,
        host: Optional[str] = "localhost",
        port: Optional[int] = 7687,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._mock_nodes: Dict[str, Dict[str, Any]] = {}
        self._mock_edges: List[Dict[str, Any]] = []

    def close(self) -> None:
        pass

    def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Executes in-memory Cypher emulation for common test queries."""
        params = parameters or {}
        q_lower = query.lower()

        # Handle MATCH (a:ANOMALY)... queries from dynamic loop
        if "anomaly" in q_lower or "associated_with" in q_lower:
            return [
                {
                    "a.id": "anom-01",
                    "ip.id": "198.51.100.24",
                    "type(r)": "ASSOCIATED_WITH",
                }
            ]

        # Handle simple node lookups or returns
        if "return n" in q_lower and "name" in params:
            name = params["name"]
            if name in self._mock_nodes:
                return [{"n": self._mock_nodes[name]}]
            return [{"n": {"name": name, "label": "ENTITY"}}]

        return []

    def add_node(
        self,
        label: str,
        name: str,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        """Creates or merges an in-memory node."""
        clean_label = label.upper().strip()
        if not IDENTIFIER_PATTERN.match(clean_label):
            clean_label = "ENTITY"

        props = properties or {}
        node_data = {
            "name": name,
            "label": clean_label,
            "confidence": confidence,
            **props,
        }
        self._mock_nodes[name] = node_data
        return node_data

    def add_edge(
        self,
        source_name: str,
        target_name: str,
        relationship: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Creates or merges a directed relationship between two in-memory nodes."""
        clean_rel = relationship.upper().strip()
        if not IDENTIFIER_PATTERN.match(clean_rel):
            clean_rel = "RELATION"

        props = properties or {}
        edge_data = {
            "source": source_name,
            "target": target_name,
            "relationship": clean_rel,
            **props,
        }
        self._mock_edges.append(edge_data)
        return edge_data

    def find_related_entities(self, search_term: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Searches in-memory nodes and edges for matching entities."""
        term_lower = search_term.lower()
        results = []

        for name, node in self._mock_nodes.items():
            if term_lower in name.lower() or term_lower in str(node.get("label", "")).lower():
                results.append({
                    "entity": name,
                    "type": node.get("label", "ENTITY"),
                    "relation": None,
                    "connected_entity": None,
                })

        for edge in self._mock_edges:
            src = edge["source"]
            tgt = edge["target"]
            rel = edge["relationship"]
            if term_lower in src.lower() or term_lower in tgt.lower() or term_lower in rel.lower():
                results.append({
                    "entity": src,
                    "type": self._mock_nodes.get(src, {}).get("label", "ENTITY"),
                    "relation": rel,
                    "connected_entity": tgt,
                })

        return results[:limit]
