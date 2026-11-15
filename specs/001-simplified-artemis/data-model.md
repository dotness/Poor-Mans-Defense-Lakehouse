# Data Model: Simplified Artemis

This document defines the core domain entities, storage mechanisms, validation constraints, and state lifecycles across the platform.

---

## 1. Telemetry Event (Time-Series / Analytics)

A high-frequency, time-stamped metric reading ingested from an operational edge sensor or device.

### Storage
- **Ingestion Buffer**: Mosquitto MQTT in-memory queue flushed to local append-only disk buffer (`/var/log/artemis/buffer/`).
- **Lakehouse Storage**: MinIO Object Storage under `s3://telemetry/year=YYYY/month=MM/day=DD/<batch_id>.parquet`.
- **Query Engine**: DuckDB vectorized reader (`read_parquet('s3://telemetry/**/*.parquet')`).

### Attributes & Types
| Field | Type | Required | Description |
|---|---|---|---|
| `event_id` | UUIDv4 / ULID | Yes | Globally unique identifier generated upon ingestion buffer write. |
| `timestamp` | Timestamp (ISO-8601 UTC) | Yes | Device-reported reading time (`YYYY-MM-DDTHH:MM:SS.fffZ`). |
| `device_id` | String (max 64 chars) | Yes | Unique edge identifier (e.g. `sensor-alpha-01`). Alphanumeric, hyphens, underscores. |
| `metric_name` | String (max 64 chars) | Yes | Metric identifier (e.g. `temperature`, `cpu_usage`, `battery_pct`). |
| `value` | Double Precision Float | Yes | Numerical measurement value. |
| `unit` | String (max 16 chars) | No | Unit of measurement (e.g. `celsius`, `pct`, `volts`). |
| `metadata` | JSONB / JSON Map | No | Arbitrary contextual tags (firmware version, GPS lat/long, site location). |

### Validation Rules
1. `timestamp` must not be more than 24 hours in the future or more than 30 days in the past relative to broker arrival.
2. `device_id` must match regex `^[a-zA-Z0-9_-]{3,64}$`.
3. `value` must be a valid non-NaN, non-infinite floating point number.
4. Payload size must not exceed 64 KB per message.

### Lifecycle & State Transitions
```text
[MQTT Publish] → [Mosquitto Ingest] → [Disk Buffer Write] → [Batch Flush Worker] → [MinIO Parquet Object] → [DuckDB Available]
```

---

## 2. Intelligence Node & Edge (Graph)

Entities and relationships extracted from telemetry, OSINT (SpiderFoot), or analyst reports to model complex interactions.

### Storage
- **Storage**: Memgraph (In-Memory C++ Graph Engine with openCypher interface and Bolt protocol).

### Node Schema
| Field | Type | Required | Description |
|---|---|---|---|
| `node_id` | UUIDv4 / String | Yes | Unique entity identifier (e.g. `entity-ip-198-51-100-24`). |
| `label` | String | Yes | Graph label (`Person`, `Organization`, `IP_Address`, `Domain`, `Incident`). |
| `name` | String | Yes | Human-readable title or entity value. |
| `confidence` | Float (0.0 - 1.0) | Yes | Intelligence confidence score (default `0.8`). |
| `properties` | JSON / Map | No | Label-specific key-values (e.g. ASN, country code, aliases). |
| `created_at` | Timestamp UTC | Yes | Time node was recorded in the graph. |

### Edge Schema
| Field | Type | Required | Description |
|---|---|---|---|
| `relationship` | String | Yes | openCypher relationship type (`COMMUNICATES_WITH`, `RESOLVES_TO`, `ATTRIBUTED_TO`). |
| `source_id` | UUIDv4 | Yes | Originating node ID. |
| `target_id` | UUIDv4 | Yes | Destination node ID. |
| `weight` | Float (0.0 - 1.0) | No | Correlation strength or frequency weight. |

### Validation Rules
1. `label` must be an uppercase alphanumeric token matching `^[A-Z][A-Za-z0-9_]{2,31}$`.
2. `confidence` must be between `0.0` and `1.0`.
3. Self-referential edges with identical source and target IDs are rejected unless explicitly tagged as cyclical loops.

---

## 3. Data Pipeline (Relational / Orchestration)

Scheduled or event-driven workflow controlling data movement (e.g. buffer flushes, analytics aggregations, OSINT graph imports).

### Storage
- **Storage**: PostgreSQL (`pipelines` and `pipeline_runs` tables) or embedded Kestra/Dagster relational catalog.

### Attributes
| Field | Type | Required | Description |
|---|---|---|---|
| `pipeline_id` | UUIDv4 | Yes | Unique pipeline registration key. |
| `name` | String (max 100 chars) | Yes | Pipeline name (e.g. `mqtt_to_minio_flush`). |
| `schedule` | String | No | Cron expression or `EVENT_DRIVEN`. |
| `status` | Enum | Yes | `ACTIVE`, `PAUSED`, `DISABLED`. |
| `last_status` | Enum | No | `SUCCESS`, `FAILED`, `RUNNING`. |
| `last_run_at` | Timestamp UTC | No | Timestamp of most recent execution. |

### State Transitions
```text
[REGISTERED] → [ACTIVE] ⇄ [PAUSED]
                  ↓
          [DISPATCHED / RUNNING]
             ↙           ↘
        [SUCCESS]      [FAILED] (Triggers retry / alert)
```

---

## 4. AI Query & Audit Log (Relational / Analytics)

Natural language queries dispatched to Google AI Studio, including retrieved graph/lakehouse context and audit records.

### Storage
- **Storage**: PostgreSQL (`ai_queries` table) + Redis semantic cache (1-hour TTL for identical prompt hashes).

### Attributes
| Field | Type | Required | Description |
|---|---|---|---|
| `query_id` | UUIDv4 | Yes | Unique trace identifier for the interaction. |
| `user_id` | String | Yes | Analyst username or API client ID. |
| `prompt` | Text | Yes | Natural language query text. |
| `context_payload` | JSONB | Yes | Subgraph nodes and DuckDB summary rows injected into prompt context. |
| `response` | Text | Yes | Markdown-formatted answer synthesized by Google AI Studio. |
| `model_used` | String | Yes | Google AI Studio model identifier (e.g. `gemini-2.5-flash`). |
| `cached` | Boolean | Yes | True if served from Redis semantic cache. |
| `duration_ms` | Integer | Yes | Round-trip latency in milliseconds. |
| `created_at` | Timestamp UTC | Yes | Timestamp of request execution. |

### Validation Rules
1. `prompt` must be non-empty and between 3 and 4,096 characters.
2. `user_id` must be authenticated via Authelia/reverse proxy headers before query dispatch.
