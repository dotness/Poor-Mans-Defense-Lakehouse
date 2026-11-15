import pytest
from src.domains.ai.operations.guardrails import validate_readonly_sql, validate_readonly_cypher


def test_valid_readonly_sql_queries():
    valid_queries = [
        "SELECT count(*) FROM read_parquet('s3://telemetry/**/*.parquet')",
        "select metric_name, value from telemetry where value > 100",
        "DESCRIBE telemetry",
        "SHOW TABLES",
        "EXPLAIN SELECT 1",
        "WITH cte AS (SELECT * FROM t) SELECT * FROM cte",
    ]
    for q in valid_queries:
        assert validate_readonly_sql(q) == q.strip()


def test_reject_mutating_sql_queries():
    mutating_queries = [
        "DROP TABLE telemetry",
        "DELETE FROM telemetry WHERE 1=1",
        "INSERT INTO telemetry VALUES (1, 2)",
        "UPDATE telemetry SET value = 0",
        "ALTER TABLE telemetry ADD COLUMN x INT",
        "CREATE TABLE test (id INT)",
        "ATTACH 'db.duckdb' AS remote",
        "SELECT * FROM t; DROP TABLE t",
    ]
    for q in mutating_queries:
        with pytest.raises(PermissionError):
            validate_readonly_sql(q)


def test_valid_readonly_cypher_queries():
    valid_cyphers = [
        "MATCH (n:Entity) RETURN n.id, n.type LIMIT 10",
        "match (a:ANOMALY)-[:ASSOCIATED_WITH]->(b) return a, b",
        "MATCH (n) WHERE n.name = 'test' RETURN n",
    ]
    for q in valid_cyphers:
        assert validate_readonly_cypher(q) == q.strip()


def test_reject_mutating_cypher_queries():
    mutating_cyphers = [
        "CREATE (n:Entity {id: '1'})",
        "MATCH (n:Entity) DETACH DELETE n",
        "MATCH (n:Entity) DELETE n",
        "MATCH (n:Entity) SET n.name = 'hacked'",
        "MATCH (n:Entity) REMOVE n.prop",
        "MERGE (n:Entity {id: '1'})",
        "DROP INDEX ON :Entity(id)",
    ]
    for q in mutating_cyphers:
        with pytest.raises(PermissionError):
            validate_readonly_cypher(q)
