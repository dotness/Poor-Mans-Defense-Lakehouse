import sys
import logging
from pathlib import Path

# Ensure paths
root_dir = Path(__file__).resolve().parent.parent.parent
src_dir = root_dir / "src"
for p in (str(root_dir), str(src_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

from src.services.graph.memgraph_client import MemgraphClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_graph")

SAMPLE_NODES = [
    # IP Addresses
    {"label": "IP_ADDRESS", "name": "198.51.100.24", "confidence": 0.95, "props": {"asn": "AS64496", "country": "NL"}},
    {"label": "IP_ADDRESS", "name": "198.51.100.25", "confidence": 0.85, "props": {"asn": "AS64496", "country": "NL"}},
    {"label": "IP_ADDRESS", "name": "203.0.113.50", "confidence": 0.90, "props": {"asn": "AS64500", "country": "US"}},

    # Domains
    {"label": "DOMAIN_NAME", "name": "c2-controller.darknet.org", "confidence": 0.98, "props": {"registrar": "BadRegistrar LLC"}},
    {"label": "DOMAIN_NAME", "name": "malicious-domain.com", "confidence": 0.92, "props": {"registrar": "BadRegistrar LLC"}},
    {"label": "DOMAIN_NAME", "name": "phishing-portal.net", "confidence": 0.88, "props": {"registrar": "PrivacyProtected Inc"}},

    # Incidents / Anomalies
    {"label": "ANOMALY", "name": "INC-2026-001 (Unauthorized C2 Beaconing)", "confidence": 1.0, "props": {"severity": "CRITICAL"}},
    {"label": "ANOMALY", "name": "INC-2026-002 (Credential Harvesting Campaign)", "confidence": 0.9, "props": {"severity": "HIGH"}},

    # Threat Actors
    {"label": "THREAT_ACTOR", "name": "APT-Artemis-Target", "confidence": 0.80, "props": {"origin": "Unknown"}},
]

SAMPLE_EDGES = [
    {"source": "c2-controller.darknet.org", "target": "198.51.100.24", "relationship": "RESOLVES_TO", "props": {"protocol": "DNS"}},
    {"source": "malicious-domain.com", "target": "198.51.100.24", "relationship": "RESOLVES_TO", "props": {"protocol": "DNS"}},
    {"source": "phishing-portal.net", "target": "203.0.113.50", "relationship": "RESOLVES_TO", "props": {"protocol": "DNS"}},
    {"source": "INC-2026-001 (Unauthorized C2 Beaconing)", "target": "198.51.100.24", "relationship": "ASSOCIATED_WITH", "props": {"evidence": "Flow Logs"}},
    {"source": "INC-2026-001 (Unauthorized C2 Beaconing)", "target": "c2-controller.darknet.org", "relationship": "TRIGGERED_BY", "props": {"evidence": "DNS Query"}},
    {"source": "INC-2026-002 (Credential Harvesting Campaign)", "target": "203.0.113.50", "relationship": "ASSOCIATED_WITH", "props": {"evidence": "Auth Alerts"}},
    {"source": "APT-Artemis-Target", "target": "c2-controller.darknet.org", "relationship": "OPERATES", "props": {"attribution": "OSINT Intel"}},
]


def seed_memgraph(client: MemgraphClient = None) -> dict:
    """Seeds sample intelligence entities and edges into Memgraph."""
    cli = client or MemgraphClient()
    logger.info("Seeding intelligence entities into Memgraph...")

    try:
        nodes_seeded = 0
        for n in SAMPLE_NODES:
            cli.add_node(
                label=n["label"],
                name=n["name"],
                properties=n.get("props"),
                confidence=n.get("confidence", 0.8),
            )
            nodes_seeded += 1

        edges_seeded = 0
        for e in SAMPLE_EDGES:
            cli.add_edge(
                source_name=e["source"],
                target_name=e["target"],
                relationship=e["relationship"],
                properties=e.get("props"),
            )
            edges_seeded += 1

        logger.info(f"Seeding complete: {nodes_seeded} nodes, {edges_seeded} edges created.")
        return {"nodes_seeded": nodes_seeded, "edges_seeded": edges_seeded}
    finally:
        cli.close()


if __name__ == "__main__":
    result = seed_memgraph()
    print(f"\nSuccessfully seeded {result['nodes_seeded']} nodes and {result['edges_seeded']} edges.")
