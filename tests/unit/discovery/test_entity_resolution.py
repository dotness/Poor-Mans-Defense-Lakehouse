import pytest
from src.domains.discovery.operations.entity_resolution import EntityResolver, DisjointSetUnion


def test_disjoint_set_union():
    dsu = DisjointSetUnion()
    dsu.union("a", "b")
    dsu.union("b", "c")
    dsu.union("d", "e")

    assert dsu.find("a") == dsu.find("c")
    assert dsu.find("a") != dsu.find("d")
    assert dsu.find("d") == dsu.find("e")


def test_normalization():
    resolver = EntityResolver()
    assert resolver.normalize("  ACCT-99812  ") == "acct-99812"
    assert resolver.normalize("Alice.Smith@Hospital.org") == "alice.smith@hospital.org"


def test_exact_resolution():
    resolver = EntityResolver()
    ent1 = {"id": "e1", "type": "Identifier", "value": "ACCT-99812", "project_id": "p1"}
    ent2 = {"id": "e2", "type": "Identifier", "value": "acct-99812", "project_id": "p2"}

    matches = resolver.resolve_pair(ent1, ent2)
    assert matches is not None
    assert matches["method"] == "exact"
    assert matches["confidence"] == 1.0


def test_jaro_winkler_fuzzy_resolution():
    resolver = EntityResolver(fuzzy_threshold=0.93)
    # Very similar (1 character typo in long string)
    ent1 = {"id": "e1", "type": "Person", "value": "Alexander Hamilton", "project_id": "p1"}
    ent2 = {"id": "e2", "type": "Person", "value": "Alexandre Hamilton", "project_id": "p2"}

    match = resolver.resolve_pair(ent1, ent2)
    assert match is not None
    assert match["method"] == "jaro_winkler"
    assert match["confidence"] >= 0.93

    # Dissimilar strings below 0.93
    ent3 = {"id": "e3", "type": "Person", "value": "George Washington", "project_id": "p1"}
    assert resolver.resolve_pair(ent1, ent3) is None


def test_type_mismatch_rejected():
    resolver = EntityResolver()
    # Same value, but different types (e.g. Person vs IP_Address)
    ent1 = {"id": "e1", "type": "Person", "value": "192.168.1.1", "project_id": "p1"}
    ent2 = {"id": "e2", "type": "IP_Address", "value": "192.168.1.1", "project_id": "p2"}

    assert resolver.resolve_pair(ent1, ent2) is None
