import json
import pytest

try:
    from src.services.graph.osint_importer import OsintImporter
except ImportError:
    from services.graph.osint_importer import OsintImporter


def test_spiderfoot_json_export_parsing(mock_memgraph_client):
    sample_export = [
        {
            "type": "IP_ADDRESS",
            "data": "198.51.100.24",
            "source": "malicious-domain.com",
            "module": "sfp_dns",
            "confidence": 0.9,
        },
        {
            "type": "DOMAIN_NAME",
            "data": "malicious-domain.com",
            "source": "TARGET",
            "module": "sfp_whois",
            "confidence": 1.0,
        },
    ]
    importer = OsintImporter(client=mock_memgraph_client)
    nodes, edges = importer.parse_spiderfoot_json(json.dumps(sample_export))

    assert len(nodes) == 2
    assert nodes[0]["name"] == "198.51.100.24"
    assert nodes[0]["label"] == "IP_ADDRESS"
    assert nodes[1]["name"] == "malicious-domain.com"
    assert nodes[1]["label"] == "DOMAIN_NAME"

    assert len(edges) == 1
    assert edges[0]["source"] == "198.51.100.24"
    assert edges[0]["target"] == "malicious-domain.com"
    assert edges[0]["relationship"] == "RESOLVES_TO"


def test_invalid_osint_payload_handling(mock_memgraph_client):
    importer = OsintImporter(client=mock_memgraph_client)
    with pytest.raises(ValueError):
        importer.parse_spiderfoot_json("invalid json string")
