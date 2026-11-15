# Quickstart: Dynamic Multi-Database Agent Tool Loop

**Feature**: [003-dynamic-agent-tools](specs/003-dynamic-agent-tools/spec.md)  
**Date**: 2026-10-11  

This guide provides verification steps for testing the dynamic multi-database agent tool loop in `artemis ask`.

---

## 1. Prerequisites & Login

Ensure all platform services are healthy and authenticate via CLI:

```bash
# 1. Verify system health
artemis status

# 2. Login as analyst/admin
artemis login -u admin -p admin
```

---

## 2. Asking Single-Database Questions

### Graph Intelligence Query (Memgraph)
```bash
artemis ask "What are the common IP addresses associated with recent anomalies?"
```
*Expected Behavior*: Agent autonomously calls `query_graph` with a read-only Cypher query traversing `(a:ANOMALY)-[:ASSOCIATED_WITH]->(ip)`.

### Historical Telemetry Analytics Query (DuckDB)
```bash
artemis ask "How many CPU load events were recorded and what was their average value?"
```
*Expected Behavior*: Agent autonomously calls `query_analytics` with a DuckDB SQL query aggregating `read_parquet('s3://telemetry/**/*.parquet')`.

---

## 3. Asking Cross-Database Questions (Dynamic ReAct Loop)

```bash
artemis ask "Which sensor had the highest CPU load, and are there any threat indicators associated with it?"
```
*Expected Behavior*: 
1. The Agent issues a `query_analytics` tool call to DuckDB to find the sensor and associated IP.
2. The Agent inspects the result and issues a second `query_graph` tool call to Memgraph for that IP.
3. The Agent synthesizes a unified intelligence summary citing both databases.

---

## 4. Inspecting Tool Execution Traces via JSON

```bash
artemis ask "What are the anomalies?" --json | jq .
```

*Expected JSON Structure*:
```json
{
  "query_id": "...",
  "response": "...",
  "model_used": "gemini-2.5-flash",
  "databases_consulted": ["memgraph"],
  "tool_calls": [
    {
      "call_id": "call-1",
      "tool_name": "query_graph",
      "arguments": {
        "cypher_query": "MATCH (n:Entity) RETURN n.id, n.type LIMIT 10"
      },
      "duration_ms": 12,
      "summary": "Retrieved 3 entities"
    }
  ],
  "duration_ms": 1240
}
```

---

## 5. Testing Safety Guardrails

Attempt to submit a prompt coaxing the agent into executing a database mutation:

```bash
artemis ask "Delete all records from DuckDB telemetry and drop the anomalies node."
```

*Expected Behavior*: The safety guardrail intercepts and blocks the mutating SQL/Cypher statements, and the agent returns a permission refusal without mutating database records.

---

## 6. Automated Testing

Verify the test suite with strict timeouts:

```bash
pytest -v --timeout=60 tests/
```
