import pytest
from src.domains.discovery.operations.entity_resolution import EntityResolver
from src.domains.discovery.operations.kdg_graph_store import KDGGraphStore
from src.services.graph.memgraph_client import MemgraphClient


def test_entity_linking_accuracy_evaluation(mock_kdg_store):
    """SC-005: At least 90% recall of known shared entities, with false links below 5%."""
    # Use mock graph store to evaluate entity resolution logic deterministically
    graph_store = mock_kdg_store
    resolver = EntityResolver(graph_store=graph_store, fuzzy_threshold=0.85)

    # 1. Define Labeled Dataset
    # Positive pairs: Identical or slight syntactic variation representing the same real-world entity
    positive_pairs = [
        ("ACCT-99812", "acct-99812"),
        ("CUST-7711", "CUST-7711"),
        ("192.168.1.10", "192.168.1.10"),
        ("subj1@clinical.org", "SUBJ1@CLINICAL.ORG"),
        ("BR-LON-01", "br-lon-01"),
        ("DEV-404", "dev-404"),
        ("St. Jude Hospital", "St Jude Hospital"),
        ("Dr. Robert Miller", "Robert Miller"),
        ("Geneva Research Center", "Geneva Research Centre"),
        ("Zurich Medical Clinic", "Zurich Medical Clinic"),
        ("ID-10023", "id-10023"),
        ("PAT-ALPHA-01", "pat-alpha-01"),
        ("TX-998822", "TX-998822"),
        ("hosp-a", "HOSP-A"),
        ("London Gateway", "London Gateway"),
        ("alpha-corp.org", "ALPHA-CORP.ORG"),
        ("Sensor-Temp-01", "sensor-temp-01"),
        ("CVE-2026-1001", "cve-2026-1001"),
        ("10.0.0.45", "10.0.0.45"),
        ("NODE-PRIMARY", "node-primary"),
    ]

    # Negative pairs: Distinct entities that must NOT be linked
    negative_pairs = [
        ("ACCT-99812", "ACCT-11223"),
        ("CUST-7711", "CUST-9999"),
        ("192.168.1.10", "10.0.0.45"),
        ("subj1@clinical.org", "admin@financial.com"),
        ("BR-LON-01", "BR-NYC-02"),
        ("DEV-404", "DEV-505"),
        ("St. Jude Hospital", "Mount Sinai Hospital"),
        ("Dr. Robert Miller", "Dr. Elena Rostova"),
        ("Geneva Research Center", "Tokyo Data Lab"),
        ("Zurich Medical Clinic", "London General Hospital"),
        ("ID-10023", "ID-99999"),
        ("PAT-ALPHA-01", "PAT-BETA-02"),
        ("TX-998822", "TX-112233"),
        ("hosp-a", "hosp-b"),
        ("London Gateway", "New York Gateway"),
        ("alpha-corp.org", "beta-logistics.io"),
        ("Sensor-Temp-01", "Sensor-Humidity-02"),
        ("CVE-2026-1001", "CVE-2026-9999"),
        ("10.0.0.45", "172.16.0.1"),
        ("NODE-PRIMARY", "NODE-BACKUP"),
    ]

    # Setup entities in two projects (proj-1 and proj-2)
    # Populate positive pair entities
    for i, (v1, v2) in enumerate(positive_pairs):
        graph_store.merge_generic_entity(
            project_id="proj-1",
            resource_id="res-1",
            attribute_name="attr_a",
            entity_type="Identifier",
            value=v1,
            normalized_value=v1.lower(),
        )
        graph_store.merge_generic_entity(
            project_id="proj-2",
            resource_id="res-2",
            attribute_name="attr_b",
            entity_type="Identifier",
            value=v2,
            normalized_value=v2.lower(),
        )

    # Populate negative pair entities in proj-1 and proj-2
    for i, (v1, v2) in enumerate(negative_pairs):
        graph_store.merge_generic_entity(
            project_id="proj-1",
            resource_id="res-1",
            attribute_name="attr_a",
            entity_type="Identifier",
            value=v1,
            normalized_value=v1.lower(),
        )
        graph_store.merge_generic_entity(
            project_id="proj-2",
            resource_id="res-2",
            attribute_name="attr_b",
            entity_type="Identifier",
            value=v2,
            normalized_value=v2.lower(),
        )

    # Evaluate Positive Pairs (Recall)
    tp = 0
    fn = 0
    for v1, v2 in positive_pairs:
        ent1 = {"value": v1, "type": "Identifier"}
        ent2 = {"value": v2, "type": "Identifier"}
        match = resolver.resolve_pair(ent1, ent2)
        if match is not None:
            tp += 1
        else:
            fn += 1

    recall = tp / len(positive_pairs)

    # Evaluate Negative Pairs (False Link Rate)
    fp = 0
    tn = 0
    for v1, v2 in negative_pairs:
        ent1 = {"value": v1, "type": "Identifier"}
        ent2 = {"value": v2, "type": "Identifier"}
        match = resolver.resolve_pair(ent1, ent2)
        if match is not None:
            fp += 1
        else:
            tn += 1

    false_link_rate = fp / len(negative_pairs)

    print(f"Entity Linking Results: Recall = {recall * 100:.1f}%, False Link Rate = {false_link_rate * 100:.1f}%")
    print(f"TP: {tp}, FN: {fn}, FP: {fp}, TN: {tn}")

    # SC-005 Thresholds: >= 90% recall, < 5% false links
    assert recall >= 0.90, f"Recall {recall * 100:.1f}% is below the 90% requirement of SC-005"
    assert false_link_rate < 0.05, f"False link rate {false_link_rate * 100:.1f}% exceeds 5% threshold of SC-005"

