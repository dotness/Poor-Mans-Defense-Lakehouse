# Quickstart: Microservice Architecture Alignment

**Feature**: [002-uservice-alignment](specs/002-uservice-alignment/spec.md)  
**Date**: 2026-10-11  

This guide provides end-to-end verification steps for developers and operators testing the refactored domain services, Temporal workflows, and JWT authentication.

---

## 1. Environment & Infrastructure Setup

Start the updated Docker Compose environment (now including `temporal`):

```bash
# 1. Start all containers including Temporal server
make up

# 2. Check health of all services
artemis status
```

---

## 2. Authenticating via CLI

Authenticate using the new JWT security stack:

```bash
# 1. Login with developer credentials (saves token to ~/.artemis/token)
artemis login --username admin --password admin_password

# 2. Check current session status and token expiration
artemis whoami
```

---

## 3. Running Domain Operations via CLI (Powered by Domain Facades)

```bash
# 1. Ingest simulated telemetry
make simulate-telemetry

# 2. Trigger the buffer flush (now executed as a Temporal Workflow)
artemis pipeline run mqtt_to_minio

# 3. Execute analytical query via AnalyticsFacade
artemis query --sql "SELECT metric_name, COUNT(*) FROM read_parquet('s3://telemetry/**/*.parquet') GROUP BY metric_name"

# 4. Ask intelligence question via AIFacade (with targeted ADK agents)
artemis ask "What are the common IP addresses associated with recent anomalies?"
```

---

## 4. Running Domain Operations via HTTP REST API

Launch the unified FastAPI gateway:

```bash
# Start FastAPI application
uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
```

Obtain a JWT token via REST:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin_password"}' \
  | jq -r .access_token)
```

Query the Analytics Domain via REST:

```bash
curl -s -X POST http://localhost:8000/api/v1/analytics/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT metric_name, COUNT(*) FROM read_parquet('\''s3://telemetry/**/*.parquet'\'') GROUP BY metric_name", "format": "json"}' \
  | jq .
```

---

## 5. Running Automated Tests

Verify contract and integration test compliance:

```bash
# Execute pytest with strict 60-second timeouts
pytest -v --timeout=60 tests/
```
