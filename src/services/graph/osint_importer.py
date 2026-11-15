import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.services.graph.memgraph_client import MemgraphClient

logger = logging.getLogger(__name__)


class OsintImporter:
    """Service to parse and ingest SpiderFoot OSINT exports into Memgraph."""

    def __init__(
        self,
        client: Optional[MemgraphClient] = None,
    ):
        self.client = client or MemgraphClient()

    def parse_spiderfoot_json(self, data: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Parses a SpiderFoot JSON export into graph nodes and directed edges."""
        try:
            parsed = json.loads(data)
        except Exception as e:
            raise ValueError(f"Invalid JSON data: {e}") from e

        if not isinstance(parsed, list):
            raise ValueError("Expected top-level JSON array for SpiderFoot export")

        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        seen_nodes: set = set()

        for entry in parsed:
            if not isinstance(entry, dict):
                continue

            entity_name = str(entry.get("data", "")).strip()
            entity_type = str(entry.get("type", "ENTITY")).strip()
            source = entry.get("source")
            module = str(entry.get("module", "")).strip()
            confidence = float(entry.get("confidence", 0.8))

            if entity_name and entity_name not in seen_nodes:
                seen_nodes.add(entity_name)
                nodes.append({
                    "name": entity_name,
                    "label": entity_type,
                    "confidence": confidence,
                    "module": module,
                })

            if source and str(source).strip().upper() != "TARGET":
                src_target = str(source).strip()
                if entity_type in ("IP_ADDRESS", "IPV4_ADDRESS", "IPV6_ADDRESS"):
                    relationship = "RESOLVES_TO"
                elif entity_type in ("SUBDOMAIN", "AFFILIATE_DOMAIN_NAME"):
                    relationship = "SUBDOMAIN_OF"
                else:
                    relationship = "ASSOCIATED_WITH"

                edges.append({
                    "source": entity_name,
                    "target": src_target,
                    "relationship": relationship,
                    "module": module,
                })

        return nodes, edges

    def import_to_memgraph(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """Inserts parsed nodes and edges into Memgraph."""
        nodes_count = 0
        edges_count = 0

        for node in nodes:
            props = {"module": node.get("module", "")}
            self.client.add_node(
                label=node.get("label", "ENTITY"),
                name=node["name"],
                properties=props,
                confidence=node.get("confidence", 0.8),
            )
            nodes_count += 1

        for edge in edges:
            props = {"module": edge.get("module", "")}
            self.client.add_edge(
                source_name=edge["source"],
                target_name=edge["target"],
                relationship=edge.get("relationship", "ASSOCIATED_WITH"),
                properties=props,
            )
            edges_count += 1

        return {
            "nodes_imported": nodes_count,
            "edges_imported": edges_count,
        }

    def import_from_file(self, file_path: str) -> Dict[str, int]:
        """Reads a SpiderFoot JSON file and imports all records into Memgraph."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"OSINT export file not found: {file_path}")

        content = path.read_text(encoding="utf-8")
        nodes, edges = self.parse_spiderfoot_json(content)
        return self.import_to_memgraph(nodes, edges)
