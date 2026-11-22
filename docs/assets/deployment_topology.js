(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined && text !== null) {
      node.textContent = String(text);
    }
    return node;
  }

  function svgEl(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        node.setAttribute(k, String(attrs[k]));
      });
    }
    return node;
  }

  var DEPLOYMENT_UNITS = [
    {
      id: "dep_cli_sensors",
      zone: "external-edge",
      zoneLabel: "Zone 1: External & Ingress Boundary",
      name: "Operator CLI (artemis) & Edge MQTT Feeds",
      containerName: "Host CLI / Edge Publishers",
      imageOrRuntime: "Python 3.12 Click CLI + paho-mqtt",
      ports: "Outbound -> :80 / :8000 (REST) & :1883 (MQTT)",
      networkPlane: "External / Host Loopback",
      ramProfile: "35 MB (CLI) / 25 MB (Simulator)",
      volumesAndMounts: "~/.artemis/token (0600 JWT cache)",
      restartPolicy: "On-Demand CLI / Burst Script",
      securityPosture: "HS256 Bearer JWT token auth (0600 file mode) + JSON schema validation",
      badge: "INGRESS / CLI",
      badgeClass: "badge-blue",
      svgX: 255,
      svgY: 66,
      svgW: 250,
      svgH: 48,
      svgSub: "artemis CLI • simulate_telemetry.py",
      envVars: [
        "MQTT_BROKER_HOST=localhost",
        "MQTT_BROKER_PORT=1883",
        "MQTT_TOPIC_PREFIX=telemetry",
        "ARTEMIS_AUTH_USER=analyst"
      ],
      configFiles: [
        "src/cli/main.py",
        "tools/simulate_telemetry.py",
        "pyproject.toml ([project.scripts] artemis)"
      ],
      healthAndOpsCmd: "$ artemis login -u admin -p admin\n$ artemis status --json\n$ make simulate-telemetry  # Publishes 10,000 MQTT events to :1883",
      composeOrSpecSnippet: "# Console script entrypoint in pyproject.toml\n[project.scripts]\nartemis = \"src.cli.main:cli\"\n\n# Token cached with strict owner-only permissions\n~/.artemis/token (chmod 0600)",
      detailedRole: "Provides unified operator control across 8 command groups (status, login, whoami, query, ask, pipeline, project, discover) and simulates high-velocity IoT/sensor MQTT bursts (1,000+ events/sec with 3-sigma anomalies) plus SpiderFoot OSINT graph payloads."
    },
    {
      id: "dep_gemini_cloud",
      zone: "external-edge",
      zoneLabel: "Zone 1: External & Ingress Boundary",
      name: "Google AI Studio Cloud API",
      containerName: "External Cloud Endpoint (Zero Local GPU)",
      imageOrRuntime: "gemini-2.5-flash-lite (google-genai SDK)",
      ports: "HTTPS :443 (TLS 1.3 Outbound)",
      networkPlane: "External Public HTTPS API",
      ramProfile: "0 MB Local VRAM / 15 MB SDK Client",
      volumesAndMounts: "Stateless Cloud Inference (Zero local model weights)",
      restartPolicy: "Managed Cloud SLA + Fail-Fast Pre-Check",
      securityPosture: "API Key via .env only; Read-Only Tool Guardrails; 60 req/min Redis Rate Limit",
      badge: "CLOUD LLM",
      badgeClass: "badge-blue",
      svgX: 725,
      svgY: 66,
      svgW: 250,
      svgH: 48,
      svgSub: "gemini-2.5-flash-lite • HTTPS :443",
      envVars: [
        "GOOGLE_AI_STUDIO_API_KEY=<secret>",
        "GEMINI_MODEL=gemini-2.5-flash-lite"
      ],
      configFiles: [
        "src/domains/ai/operations/dynamic_loop.py",
        "src/services/ai/genai_service.py",
        "src/core/exceptions.py"
      ],
      healthAndOpsCmd: "$ artemis ask \"Correlate power spikes with OSINT threat actors\"\n# Fails fast with ConfigurationError if API key is missing",
      composeOrSpecSnippet: "# Offloads 12-16 GB of local LLM RAM to Cloud API\nresponse = self._client.models.generate_content(\n    model=\"gemini-2.5-flash-lite\",\n    contents=contents,\n    config=types.GenerateContentConfig(tools=six_readonly_tools, temperature=0.1)\n)",
      detailedRole: "Executes multi-turn autonomous Function Calling (up to 5 turns across 6 read-only tools spanning DuckDB, Memgraph, and KDG), ADK Planner/Critic validation, and KDG Phase 2 unstructured text NER extraction without consuming local VM RAM or GPU resources."
    },
    {
      id: "dep_buffer_worker",
      zone: "host-native",
      zoneLabel: "Zone 2: Host Linux VM Native Runtime",
      name: "MQTT Listener & POSIX Disk Buffer",
      containerName: "Host Process + Linux VFS Buffer",
      imageOrRuntime: "Python 3.12 + PyArrow Snappy Writer",
      ports: "Subscribes :1883 -> Writes /tmp/artemis/buffer -> S3 :9000",
      networkPlane: "Host Process Space + Local VFS",
      ramProfile: "15 MB (Listener) / 45 MB (Parquet Flush)",
      volumesAndMounts: "/tmp/artemis/buffer/events.jsonl (POSIX O_APPEND)",
      restartPolicy: "Managed by IngestionFacade / Temporal Activity",
      securityPosture: "Pydantic TelemetryEvent validation; crash-safe atomic os.rename() rotation",
      badge: "HOST WORKER",
      badgeClass: "badge-purple",
      svgX: 180,
      svgY: 196,
      svgW: 250,
      svgH: 52,
      svgSub: "/tmp/artemis/buffer • PyArrow Snappy",
      envVars: [
        "DISK_BUFFER_DIR=/tmp/artemis/buffer",
        "MQTT_BROKER_HOST=localhost",
        "MQTT_BROKER_PORT=1883",
        "MINIO_BUCKET=telemetry"
      ],
      configFiles: [
        "src/services/ingestion/mqtt_listener.py",
        "src/domains/ingestion/operations/flush.py",
        "src/pipelines/mqtt_to_minio.py"
      ],
      healthAndOpsCmd: "$ make trigger-pipeline\n$ artemis pipeline run mqtt_to_minio\n$ ls -lh /tmp/artemis/buffer/",
      composeOrSpecSnippet: "# Atomic zero-downtime rotation before Parquet compaction\nprocessing_file = buffer_dir / f\"events.processing.{ts}.jsonl\"\nbuffer_file.rename(processing_file)\nobject_key = minio_writer.write_batch(valid_events)",
      detailedRole: "Decouples high-frequency MQTT ingestion from S3 object creation. Appends validated JSONL events to local disk via lock-free O_APPEND, rotates files atomically via POSIX rename(), recovers interrupted batches on startup, and compacts records into Snappy Parquet files in MinIO."
    },
    {
      id: "dep_fastapi_host",
      zone: "host-native",
      zoneLabel: "Zone 2: Host Linux VM Native Runtime",
      name: "FastAPI Unified Domain Gateway",
      containerName: "uvicorn src.api:app (Host Process)",
      imageOrRuntime: "Python 3.12 / Uvicorn ASGI + 8 Domain Facades",
      ports: "Host :8000 (HTTP REST — 34 Routes)",
      networkPlane: "Host Native (:8000) <-> artemis-net Mapped Ports",
      ramProfile: "110 MB Idle / 180 MB Active",
      volumesAndMounts: "Reads .env, mounts 8 domain routers, spawns Docker SDK containers",
      restartPolicy: "Systemd / Uvicorn Supervisor (make api)",
      securityPosture: "Global JWT Bearer dependency, ContextVar caller identity, Zero-Trust project RBAC",
      badge: "UNIFIED GATEWAY",
      badgeClass: "badge-purple",
      svgX: 490,
      svgY: 196,
      svgW: 270,
      svgH: 52,
      svgSub: "uvicorn :8000 • 8 Domains • 34 Routes",
      envVars: [
        "API_HOST=0.0.0.0",
        "API_PORT=8000",
        "JWT_SECRET_KEY=<secret>",
        "JWT_ALGORITHM=HS256",
        "JWT_EXPIRATION_MINUTES=1440"
      ],
      configFiles: [
        "src/api.py",
        "src/security/middleware.py",
        "src/security/jwt.py",
        "src/domains/*/api/router.py"
      ],
      healthAndOpsCmd: "$ make api  # Starts uvicorn src.api:app --port 8000\n$ curl -s http://127.0.0.1:8000/health",
      composeOrSpecSnippet: "app = FastAPI(\n    title=\"Artemis Unified Domain Gateway\",\n    version=\"0.3.0\",\n    lifespan=lifespan,\n    dependencies=[Depends(authenticate_user)],\n)\n# Mounts auth, analytics, ai, ingestion, graph, pipeline, project, discovery",
      detailedRole: "Central hexagonal transport layer hosting all 8 domain facades (auth, ingestion, analytics, graph, ai, pipeline, project, discovery). Enforces JWT authentication, propagates caller identity via ContextVar for zero-trust KDG confinement, and coordinates across all Docker bridge services."
    },
    {
      id: "dep_duckdb_host",
      zone: "host-native",
      zoneLabel: "Zone 2: Host Linux VM Native Runtime",
      name: "Embedded DuckDB OLAP Engine",
      containerName: "In-Process C++ Extension (Zero Daemon)",
      imageOrRuntime: "DuckDB C++ Vectorized Engine + httpfs",
      ports: "In-Process Memory -> S3 HTTP :9000",
      networkPlane: "In-Process (FastAPI / CLI) -> MinIO :9000",
      ramProfile: "150 MB Idle / 850 MB (1M-Row Scan)",
      volumesAndMounts: "In-memory columnar buffers; reads s3://telemetry/**/*.parquet",
      restartPolicy: "In-Process Library (Zero Daemon Overhead)",
      securityPosture: "AST/Keyword Read-Only SQL Guardrail + S3 Project Prefix Confinement",
      badge: "C++ EMBEDDED",
      badgeClass: "badge-purple",
      svgX: 800,
      svgY: 196,
      svgW: 250,
      svgH: 52,
      svgSub: "In-Process C++ • httpfs S3 Pushdown",
      envVars: [
        "MINIO_ENDPOINT=localhost:9000",
        "MINIO_ACCESS_KEY=minioadmin",
        "MINIO_SECRET_KEY=minioadmin",
        "MINIO_USE_SSL=false"
      ],
      configFiles: [
        "src/services/analytics/duckdb_client.py",
        "src/domains/analytics/operations/project_query.py",
        "src/domains/ai/operations/guardrails.py"
      ],
      healthAndOpsCmd: "$ make query-analytics\n$ artemis query --sql \"SELECT metric_name, COUNT(*) FROM read_parquet('s3://telemetry/**/*.parquet') GROUP BY 1\"",
      composeOrSpecSnippet: "INSTALL httpfs; LOAD httpfs;\nSET s3_endpoint='localhost:9000';\nSET s3_url_style='path';\n-- Enforces s3://telemetry/projects/{id}/* prefix confinement for project queries",
      detailedRole: "Replaces an 8 GB Apache Spark/Trino JVM cluster with an embedded C++ SIMD-vectorized OLAP engine. Executes sub-second SQL aggregations directly over MinIO S3 Parquet files using predicate pushdown while enforcing strict project-scoped URI confinement."
    },
    {
      id: "dep_mosquitto",
      zone: "docker-net",
      zoneLabel: "Zone 3: Docker Bridge Network (artemis-net)",
      name: "Eclipse Mosquitto MQTT Broker",
      containerName: "artemis-mosquitto",
      imageOrRuntime: "eclipse-mosquitto:2 (ANSI C)",
      ports: "Host :1883 -> Container :1883 (MQTT TCP)",
      networkPlane: "Docker Bridge: artemis-net",
      ramProfile: "18 MB Idle / 30 MB Burst",
      volumesAndMounts: "./src/config/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro\nmosquitto_data:/mosquitto/data\nmosquitto_log:/mosquitto/log",
      restartPolicy: "unless-stopped",
      securityPosture: "Read-only config mount; isolated persistent data & log volumes",
      badge: "C CONTAINER",
      badgeClass: "badge-emerald",
      svgX: 140,
      svgY: 342,
      svgW: 210,
      svgH: 52,
      svgSub: "artemis-mosquitto • :1883 • 18 MB",
      envVars: [
        "MQTT_BROKER_PORT=1883",
        "MQTT_TOPIC_PREFIX=telemetry"
      ],
      configFiles: [
        "docker-compose.yml (services.mosquitto)",
        "src/config/mosquitto.conf"
      ],
      healthAndOpsCmd: "$ docker compose ps mosquitto\n$ docker logs artemis-mosquitto --tail 20",
      composeOrSpecSnippet: "mosquitto:\n  image: eclipse-mosquitto:2\n  container_name: artemis-mosquitto\n  restart: unless-stopped\n  ports: [\"1883:1883\"]\n  volumes:\n    - ./src/config/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro\n    - mosquitto_data:/mosquitto/data",
      detailedRole: "Ultra-lightweight ANSI C MQTT message broker replacing Apache Kafka + ZooKeeper (4.5 GB RAM). Handles 1,000+ msg/sec telemetry ingestion on topic telemetry/# with durable disk persistence in mosquitto_data."
    },
    {
      id: "dep_traefik",
      zone: "docker-net",
      zoneLabel: "Zone 3: Docker Bridge Network (artemis-net)",
      name: "Traefik v3 Edge Reverse Proxy",
      containerName: "artemis-traefik",
      imageOrRuntime: "traefik:v3.0 (Go Native)",
      ports: ":80->80 (HTTP), :443->443 (HTTPS), :8088->8080 (UI)",
      networkPlane: "Docker Bridge: artemis-net",
      ramProfile: "45 MB Idle / 65 MB Active",
      volumesAndMounts: "/var/run/docker.sock:/var/run/docker.sock:ro\n./src/config/traefik.yml:/etc/traefik/traefik.yml:ro\n./src/config/auth.yml:/etc/traefik/dynamic/auth.yml:ro",
      restartPolicy: "unless-stopped",
      securityPosture: "exposedByDefault: false; read-only Docker socket & dynamic auth middleware",
      badge: "GO CONTAINER",
      badgeClass: "badge-emerald",
      svgX: 375,
      svgY: 342,
      svgW: 210,
      svgH: 52,
      svgSub: "artemis-traefik • :80/:443/:8088",
      envVars: [
        "TRAEFIK_HTTP_PORT=80",
        "TRAEFIK_HTTPS_PORT=443",
        "TRAEFIK_DASHBOARD_PORT=8088"
      ],
      configFiles: [
        "docker-compose.yml (services.traefik)",
        "src/config/traefik.yml",
        "src/config/auth.yml"
      ],
      healthAndOpsCmd: "$ docker compose ps traefik\n$ curl -I http://127.0.0.1:8088/dashboard/",
      composeOrSpecSnippet: "traefik:\n  image: traefik:v3.0\n  container_name: artemis-traefik\n  ports: [\"80:80\", \"443:443\", \"8088:8080\"]\n  volumes:\n    - /var/run/docker.sock:/var/run/docker.sock:ro\n    - ./src/config/traefik.yml:/etc/traefik/traefik.yml:ro",
      detailedRole: "Cloud-native Go reverse proxy and edge ingress router replacing heavy JVM gateways (Kong/Keycloak). Dynamically watches Docker labels and file-based middleware (auth.yml) with under 50 MB RAM."
    },
    {
      id: "dep_redis",
      zone: "docker-net",
      zoneLabel: "Zone 3: Docker Bridge Network (artemis-net)",
      name: "Redis 7 Semantic Cache & Rate Limiter",
      containerName: "artemis-redis",
      imageOrRuntime: "redis:7-alpine (ANSI C)",
      ports: "Host :6379 -> Container :6379 (RESP TCP)",
      networkPlane: "Docker Bridge: artemis-net",
      ramProfile: "35 MB Idle / 60 MB Active",
      volumesAndMounts: "redis_data:/data",
      restartPolicy: "unless-stopped",
      securityPosture: "Per-analyst 60 req/min sliding window rate limiter + SHA-256 prompt keys",
      badge: "C CONTAINER",
      badgeClass: "badge-emerald",
      svgX: 610,
      svgY: 342,
      svgW: 210,
      svgH: 52,
      svgSub: "artemis-redis • :6379 • 35 MB",
      envVars: [
        "REDIS_HOST=localhost",
        "REDIS_PORT=6379",
        "REDIS_DB=0"
      ],
      configFiles: [
        "docker-compose.yml (services.redis)",
        "src/services/ai/cache.py"
      ],
      healthAndOpsCmd: "$ docker exec artemis-redis redis-cli ping\n$ docker compose ps redis",
      composeOrSpecSnippet: "redis:\n  image: redis:7-alpine\n  container_name: artemis-redis\n  restart: unless-stopped\n  ports: [\"6379:6379\"]\n  volumes:\n    - redis_data:/data",
      detailedRole: "Provides sub-millisecond (< 3ms) SHA-256 semantic prompt caching (artemis:ai:query:<sha256> with 1-hour TTL) to avoid redundant Gemini API calls, alongside per-user rate limiting (60 requests/min)."
    },
    {
      id: "dep_memgraph",
      zone: "docker-net",
      zoneLabel: "Zone 3: Docker Bridge Network (artemis-net)",
      name: "Memgraph Property Graph & KDG",
      containerName: "artemis-memgraph",
      imageOrRuntime: "memgraph/memgraph:latest (C++ Native)",
      ports: "Host :7687 -> Container :7687 (Bolt v4)",
      networkPlane: "Docker Bridge: artemis-net",
      ramProfile: "420 MB Idle / 750 MB Active",
      volumesAndMounts: "memgraph_data:/var/lib/memgraph",
      restartPolicy: "unless-stopped",
      securityPosture: "Zero-trust $member_projects Cypher parameter filtering + Read-Only AI Cypher guardrail",
      badge: "C++ CONTAINER",
      badgeClass: "badge-emerald",
      svgX: 845,
      svgY: 342,
      svgW: 210,
      svgH: 52,
      svgSub: "artemis-memgraph • :7687 • 420 MB",
      envVars: [
        "MEMGRAPH_HOST=localhost",
        "MEMGRAPH_PORT=7687",
        "MEMGRAPH_USER=",
        "MEMGRAPH_PASSWORD="
      ],
      configFiles: [
        "docker-compose.yml (services.memgraph)",
        "src/services/graph/memgraph_client.py",
        "src/domains/discovery/operations/kdg_graph_store.py"
      ],
      healthAndOpsCmd: "$ make seed-graph\n$ artemis discover entity --value ACCT-99812 --fuzzy\n$ docker compose ps memgraph",
      composeOrSpecSnippet: "memgraph:\n  image: memgraph/memgraph:latest\n  container_name: artemis-memgraph\n  restart: unless-stopped\n  ports: [\"7687:7687\"]\n  volumes:\n    - memgraph_data:/var/lib/memgraph",
      detailedRole: "In-memory C++ openCypher graph database replacing Neo4j JVM (6.5 GB). Hosts both threat intelligence entities (IP_ADDRESS, DOMAIN, THREAT_ACTOR, ANOMALY_EVENT) and the 6-node Universal Knowledge Discovery Graph (Workspace, DataResource, DataAttribute, GenericEntity, SemanticTaxonomy, PipelineExecution)."
    },
    {
      id: "dep_minio",
      zone: "docker-net",
      zoneLabel: "Zone 3: Docker Bridge Network (artemis-net)",
      name: "MinIO S3 Object Lakehouse",
      containerName: "artemis-minio",
      imageOrRuntime: "minio/minio:latest (Go Native)",
      ports: ":9000->9000 (S3 API), :9001->9001 (Web Console)",
      networkPlane: "Docker Bridge: artemis-net",
      ramProfile: "280 MB Idle / 520 MB Active",
      volumesAndMounts: "minio_data:/data",
      restartPolicy: "unless-stopped",
      securityPosture: "S3 IAM credentials + ProjectQueryExecutor URI prefix confinement (s3://telemetry/projects/{id}/*)",
      badge: "GO CONTAINER",
      badgeClass: "badge-emerald",
      svgX: 140,
      svgY: 438,
      svgW: 210,
      svgH: 52,
      svgSub: "artemis-minio • :9000/:9001 • 280 MB",
      envVars: [
        "MINIO_ENDPOINT=localhost:9000",
        "MINIO_ROOT_USER=minioadmin",
        "MINIO_ROOT_PASSWORD=minioadmin",
        "MINIO_BUCKET=telemetry"
      ],
      configFiles: [
        "docker-compose.yml (services.minio)",
        "src/services/ingestion/minio_writer.py",
        "src/domains/project/operations/scoped_ingestion.py"
      ],
      healthAndOpsCmd: "$ curl -I http://127.0.0.1:9000/minio/health/live\n# Console UI available at http://127.0.0.1:9001",
      composeOrSpecSnippet: "minio:\n  image: minio/minio:latest\n  container_name: artemis-minio\n  command: server /data --console-address \":9001\"\n  ports: [\"9000:9000\", \"9001:9001\"]\n  volumes:\n    - minio_data:/data",
      detailedRole: "High-performance S3-compatible object lakehouse replacing Hadoop HDFS (6.0 GB). Stores Snappy-compressed Apache Parquet files partitioned by date (s3://telemetry/year=YYYY/...) and multi-tenant Medallion tiers (s3://telemetry/projects/{id}/{bronze|silver|gold}/...)."
    },
    {
      id: "dep_postgres",
      zone: "docker-net",
      zoneLabel: "Zone 3: Docker Bridge Network (artemis-net)",
      name: "PostgreSQL 16 Relational State & Audit",
      containerName: "artemis-postgres",
      imageOrRuntime: "postgres:16-alpine (ANSI C)",
      ports: "Host :5433 -> Container :5432 (PG Wire)",
      networkPlane: "Docker Bridge: artemis-net",
      ramProfile: "180 MB Idle / 310 MB Active",
      volumesAndMounts: "postgres_data:/var/lib/postgresql/data\n./src/config/postgres_init.sql:/docker-entrypoint-initdb.d/init.sql:ro",
      restartPolicy: "unless-stopped",
      securityPosture: "Parameterized SQLAlchemy async queries; foreign-key cascade isolation; immutable AI audit log",
      badge: "C CONTAINER",
      badgeClass: "badge-emerald",
      svgX: 375,
      svgY: 438,
      svgW: 210,
      svgH: 52,
      svgSub: "artemis-postgres • :5433->5432 • 180 MB",
      envVars: [
        "POSTGRES_HOST=localhost",
        "POSTGRES_PORT=5433",
        "POSTGRES_DB=artemis",
        "POSTGRES_USER=artemis",
        "POSTGRES_PASSWORD=artemis_secure_password"
      ],
      configFiles: [
        "docker-compose.yml (services.postgres)",
        "src/config/postgres_init.sql",
        "src/database/engine.py"
      ],
      healthAndOpsCmd: "$ docker exec artemis-postgres pg_isready -U artemis\n$ docker exec -it artemis-postgres psql -U artemis -d artemis -c \"\\dt\"",
      composeOrSpecSnippet: "postgres:\n  image: postgres:16-alpine\n  container_name: artemis-postgres\n  ports: [\"5433:5432\"]\n  volumes:\n    - postgres_data:/var/lib/postgresql/data\n    - ./src/config/postgres_init.sql:/docker-entrypoint-initdb.d/init.sql:ro",
      detailedRole: "Relational source of truth initialized via postgres_init.sql with 9 core schema tables (pipelines, pipeline_runs, ai_queries, projects, project_pipelines, project_pipeline_runs, project_datasets, project_members, kdg_index_jobs) plus Temporal workflow persistence."
    },
    {
      id: "dep_temporal",
      zone: "docker-net",
      zoneLabel: "Zone 3: Docker Bridge Network (artemis-net)",
      name: "Temporal Workflow Engine Server",
      containerName: "artemis-temporal",
      imageOrRuntime: "temporalio/auto-setup:1.24 (Go Native)",
      ports: "Host :7233 -> Container :7233 (gRPC)",
      networkPlane: "Docker Bridge: artemis-net",
      ramProfile: "310 MB Idle / 480 MB Active",
      volumesAndMounts: "Stateless container persisted in artemis-postgres (temporal & temporal_visibility DBs)",
      restartPolicy: "unless-stopped (depends_on: postgres)",
      securityPosture: "Internal bridge DB authentication; deterministic workflow state machine replay",
      badge: "GO CONTAINER",
      badgeClass: "badge-emerald",
      svgX: 610,
      svgY: 438,
      svgW: 210,
      svgH: 52,
      svgSub: "artemis-temporal • gRPC :7233",
      envVars: [
        "DB=postgresql",
        "DB_PORT=5432",
        "POSTGRES_SEEDS=postgres",
        "TEMPORAL_HOST=localhost",
        "TEMPORAL_PORT=7233"
      ],
      configFiles: [
        "docker-compose.yml (services.temporal)",
        "src/base/temporal.py",
        "src/domains/discovery/operations/enrichment_workflow.py"
      ],
      healthAndOpsCmd: "$ docker compose ps temporal\n$ docker logs artemis-temporal --tail 25",
      composeOrSpecSnippet: "temporal:\n  image: temporalio/auto-setup:1.24\n  container_name: artemis-temporal\n  ports: [\"7233:7233\"]\n  environment:\n    - DB=postgresql\n    - POSTGRES_SEEDS=postgres\n  depends_on: [postgres]",
      detailedRole: "Go-native durable workflow orchestrator replacing Apache Airflow + Celery (1.8 GB). Coordinates multi-step retries and state transitions for FlushBufferWorkflow, OsintImportWorkflow, and KDGEnrichmentWorkflow."
    },
    {
      id: "dep_temporal_ui",
      zone: "docker-net",
      zoneLabel: "Zone 3: Docker Bridge Network (artemis-net)",
      name: "Temporal Web Control Dashboard",
      containerName: "artemis-temporal-ui",
      imageOrRuntime: "temporalio/ui:latest (Go / Web UI)",
      ports: "Host :8233 -> Container :8080 (HTTP)",
      networkPlane: "Docker Bridge: artemis-net",
      ramProfile: "70 MB Idle / 95 MB Active",
      volumesAndMounts: "Stateless UI container connected to temporal:7233 over artemis-net",
      restartPolicy: "unless-stopped (depends_on: temporal)",
      securityPosture: "Bound to internal Temporal gRPC server; inspectable at localhost:8233",
      badge: "WEB DASHBOARD",
      badgeClass: "badge-emerald",
      svgX: 845,
      svgY: 438,
      svgW: 210,
      svgH: 52,
      svgSub: "artemis-temporal-ui • :8233->8080",
      envVars: [
        "TEMPORAL_ADDRESS=temporal:7233"
      ],
      configFiles: [
        "docker-compose.yml (services.temporal-ui)"
      ],
      healthAndOpsCmd: "$ curl -I http://127.0.0.1:8233\n# Open http://localhost:8233 to inspect workflow histories",
      composeOrSpecSnippet: "temporal-ui:\n  image: temporalio/ui:latest\n  container_name: artemis-temporal-ui\n  ports: [\"8233:8080\"]\n  environment:\n    - TEMPORAL_ADDRESS=temporal:7233\n  depends_on: [temporal]",
      detailedRole: "Provides visual inspection of workflow execution histories, task queues, retry attempts, and activity payloads for ingestion flushes, OSINT imports, and KDG Phase 2 semantic enrichment jobs."
    },
    {
      id: "dep_sandbox_runner",
      zone: "airgap-sandbox",
      zoneLabel: "Zone 4: Air-Gapped Ephemeral Docker Sandbox",
      name: "Ephemeral Medallion Pipeline Sandbox",
      containerName: "artemis-pipeline-runner:latest (Ephemeral)",
      imageOrRuntime: "python:3.12-slim (docker/runner/Dockerfile)",
      ports: "NONE (network_mode=\"none\" — 100% Air-Gapped)",
      networkPlane: "Air-Gapped Namespace (Zero Network Interfaces)",
      ramProfile: "0 MB Idle / Hard-Capped 2048 MB (2g) & 2.0 CPUs",
      volumesAndMounts: "/tmp/artemis/runs/{run_id}/input:/workspace/input:ro\n/tmp/artemis/runs/{run_id}/script:/workspace/script:ro\n/tmp/artemis/runs/{run_id}/output:/workspace/output:rw",
      restartPolicy: "Ephemeral One-Shot (Auto-Removed after 300s max)",
      securityPosture: "AST pre-validation (ast.parse) + network_mode='none' + rootless UID 10001 + read-only input/script mounts",
      badge: "AIR-GAPPED SANDBOX",
      badgeClass: "badge-amber",
      svgX: 300,
      svgY: 562,
      svgW: 480,
      svgH: 48,
      svgSub: "artemis-pipeline-runner:latest • network=none • 2GB RAM • 2.0 CPU • UID 10001",
      envVars: [
        "DOCKER_RUNNER_IMAGE=artemis-pipeline-runner:latest",
        "DOCKER_MEMORY_LIMIT=2g",
        "DOCKER_CPU_LIMIT=2.0",
        "DOCKER_RUN_TIMEOUT=300",
        "PIPELINE_WORKSPACE_DIR=/tmp/artemis/runs"
      ],
      configFiles: [
        "docker/runner/Dockerfile",
        "docker/runner/requirements.txt",
        "src/domains/pipeline/operations/docker_runner.py",
        "src/domains/pipeline/operations/script_validator.py"
      ],
      healthAndOpsCmd: "$ artemis project pipeline run --project proj-alpha --name clean_orders --target-dataset orders_silver\n$ docker images artemis-pipeline-runner",
      composeOrSpecSnippet: "container = self.client.containers.run(\n    image=\"artemis-pipeline-runner:latest\",\n    network_mode=\"none\",       # Complete network isolation\n    mem_limit=\"2g\",            # Hard 2 GB memory ceiling\n    nano_cpus=2_000_000_000,   # 2.0 CPU cores max\n    user=\"artemis\",            # Rootless UID 10001\n    volumes={\n        input_dir:  {\"bind\": \"/workspace/input\",  \"mode\": \"ro\"},\n        script_dir: {\"bind\": \"/workspace/script\", \"mode\": \"ro\"},\n        output_dir: {\"bind\": \"/workspace/output\", \"mode\": \"rw\"},\n    }\n)",
      detailedRole: "Executes untrusted user Python data transformation scripts (BRONZE -> SILVER -> GOLD) in a completely air-gapped container with zero network access. Host DockerPipelineRunner stages input Parquet datasets before execution and ingests output Parquet files into MinIO and Memgraph KDG lineage afterward."
    }
  ];

  var DEPLOYMENT_LINKS = [
    { from: "dep_cli_sensors", to: "dep_mosquitto", label: "MQTT :1883" },
    { from: "dep_cli_sensors", to: "dep_traefik", label: "HTTP :80/:443" },
    { from: "dep_cli_sensors", to: "dep_fastapi_host", label: "REST :8000 / CLI" },
    { from: "dep_traefik", to: "dep_fastapi_host", label: "Proxy :80->:8000" },
    { from: "dep_mosquitto", to: "dep_buffer_worker", label: "Sub :1883" },
    { from: "dep_buffer_worker", to: "dep_minio", label: "Parquet :9000" },
    { from: "dep_buffer_worker", to: "dep_postgres", label: "Run Log :5433" },
    { from: "dep_fastapi_host", to: "dep_gemini_cloud", label: "HTTPS :443 (6 Tools)" },
    { from: "dep_fastapi_host", to: "dep_duckdb_host", label: "In-Process C++" },
    { from: "dep_duckdb_host", to: "dep_minio", label: "httpfs S3 :9000" },
    { from: "dep_fastapi_host", to: "dep_minio", label: "S3 API :9000" },
    { from: "dep_fastapi_host", to: "dep_postgres", label: "AsyncPG :5433" },
    { from: "dep_fastapi_host", to: "dep_redis", label: "RESP :6379" },
    { from: "dep_fastapi_host", to: "dep_memgraph", label: "Bolt :7687 (KDG)" },
    { from: "dep_fastapi_host", to: "dep_temporal", label: "gRPC :7233" },
    { from: "dep_temporal", to: "dep_postgres", label: "SQL :5432 (Internal)" },
    { from: "dep_temporal_ui", to: "dep_temporal", label: "gRPC :7233" },
    { from: "dep_fastapi_host", to: "dep_sandbox_runner", label: "Docker SDK + Bind Mounts" }
  ];

  var selectedDeployId = "dep_fastapi_host";
  var activeDeployZone = "ALL";

  function renderDeploymentDiagram() {
    var svg = document.getElementById("deployment-svg");
    if (!svg) return;
    svg.replaceChildren();

    var bg = svgEl("rect", { x: 0, y: 0, width: 980, height: 620, fill: "#050811" });
    svg.appendChild(bg);

    var zones = [
      {
        id: "external-edge",
        x: 16,
        y: 12,
        w: 948,
        h: 96,
        stroke: "#38bdf8",
        fill: "rgba(56, 189, 248, 0.04)",
        title: "ZONE 1: EXTERNAL CLIENTS, EDGE MQTT PUBLISHERS & CLOUD INFERENCE BOUNDARY"
      },
      {
        id: "host-native",
        x: 16,
        y: 122,
        w: 948,
        h: 118,
        stroke: "#a855f7",
        fill: "rgba(168, 85, 247, 0.04)",
        title: "ZONE 2: HOST LINUX VM NATIVE PROCESS SPACE (Python 3.12 / Embedded C++ / POSIX Disk Buffer)"
      },
      {
        id: "docker-net",
        x: 16,
        y: 254,
        w: 948,
        h: 232,
        stroke: "#10b981",
        fill: "rgba(16, 185, 129, 0.04)",
        title: "ZONE 3: DOCKER COMPOSE BRIDGE NETWORK (artemis-net • 8 Persistent Zero-JVM Containers)"
      },
      {
        id: "airgap-sandbox",
        x: 16,
        y: 500,
        w: 948,
        h: 106,
        stroke: "#f59e0b",
        fill: "rgba(245, 158, 11, 0.04)",
        title: "ZONE 4: AIR-GAPPED EPHEMERAL SANDBOX (network_mode=\"none\") & PERSISTENT DOCKER VOLUMES"
      }
    ];

    zones.forEach(function (z) {
      var isDimmed = activeDeployZone !== "ALL" && activeDeployZone !== z.id;
      var zRect = svgEl("rect", {
        x: z.x,
        y: z.y,
        width: z.w,
        height: z.h,
        rx: 10,
        fill: z.fill,
        stroke: z.stroke,
        "stroke-width": isDimmed ? "1" : "1.6",
        "stroke-dasharray": "6,4",
        opacity: isDimmed ? "0.35" : "0.95"
      });
      svg.appendChild(zRect);

      var zText = svgEl("text", {
        x: z.x + 14,
        y: z.y + 20,
        fill: z.stroke,
        "font-size": "10.5",
        "font-weight": "700",
        "font-family": "JetBrains Mono, monospace",
        opacity: isDimmed ? "0.4" : "1"
      });
      zText.textContent = z.title;
      svg.appendChild(zText);
    });

    var volBox = svgEl("rect", {
      x: 565,
      y: 534,
      width: 380,
      height: 56,
      rx: 8,
      fill: "#0f172a",
      stroke: "#334155",
      "stroke-width": "1.5"
    });
    svg.appendChild(volBox);

    var volTitle = svgEl("text", {
      x: 755,
      y: 554,
      fill: "#10b981",
      "font-size": "10.5",
      "font-weight": "700",
      "text-anchor": "middle",
      "font-family": "JetBrains Mono, monospace"
    });
    volTitle.textContent = "6 NAMED DOCKER VOLUMES + 2 HOST MOUNTS";
    svg.appendChild(volTitle);

    var volSub = svgEl("text", {
      x: 755,
      y: 574,
      fill: "#94a3b8",
      "font-size": "9.8",
      "text-anchor": "middle",
      "font-family": "JetBrains Mono, monospace"
    });
    volSub.textContent = "minio_data • postgres_data • memgraph_data • redis_data • mosquitto_*";
    svg.appendChild(volSub);

    var unitMap = {};
    DEPLOYMENT_UNITS.forEach(function (u) {
      unitMap[u.id] = u;
    });

    var activeLinks = [];
    DEPLOYMENT_LINKS.forEach(function (lnk) {
      var uFrom = unitMap[lnk.from];
      var uTo = unitMap[lnk.to];
      if (!uFrom || !uTo) return;
      var isHighlighted = lnk.from === selectedDeployId || lnk.to === selectedDeployId;
      if (isHighlighted) {
        activeLinks.push(lnk);
        return;
      }
      var line = svgEl("line", {
        x1: uFrom.svgX,
        y1: uFrom.svgY,
        x2: uTo.svgX,
        y2: uTo.svgY,
        stroke: "#334155",
        "stroke-width": "1.2",
        "stroke-dasharray": "4,4",
        opacity: "0.55"
      });
      svg.appendChild(line);
    });

    activeLinks.forEach(function (lnk) {
      var uFrom = unitMap[lnk.from];
      var uTo = unitMap[lnk.to];
      var line = svgEl("line", {
        x1: uFrom.svgX,
        y1: uFrom.svgY,
        x2: uTo.svgX,
        y2: uTo.svgY,
        stroke: "#f43f5e",
        "stroke-width": "2.4",
        "stroke-dasharray": "6,3"
      });
      svg.appendChild(line);
    });

    DEPLOYMENT_UNITS.forEach(function (u) {
      var isSelected = u.id === selectedDeployId;
      var isConnected = activeLinks.some(function (lnk) {
        return lnk.from === u.id || lnk.to === u.id;
      });
      var isZoneMatch = activeDeployZone === "ALL" || activeDeployZone === u.zone;

      var strokeColor = "#334155";
      if (u.zone === "external-edge") strokeColor = "#38bdf8";
      if (u.zone === "host-native") strokeColor = "#a855f7";
      if (u.zone === "docker-net") strokeColor = "#10b981";
      if (u.zone === "airgap-sandbox") strokeColor = "#f59e0b";
      if (isConnected) strokeColor = "#38bdf8";
      if (isSelected) strokeColor = "#f43f5e";

      var g = svgEl("g", {
        cursor: "pointer",
        opacity: isZoneMatch || isSelected ? "1" : "0.35"
      });

      var rect = svgEl("rect", {
        x: u.svgX - u.svgW / 2,
        y: u.svgY - u.svgH / 2,
        width: u.svgW,
        height: u.svgH,
        rx: 8,
        fill: isSelected ? "#213052" : "#131c31",
        stroke: strokeColor,
        "stroke-width": isSelected ? "2.8" : (isConnected ? "2" : "1.5")
      });
      g.appendChild(rect);

      var title = svgEl("text", {
        x: u.svgX,
        y: u.svgY - 4,
        fill: "#f8fafc",
        "font-size": "11.5",
        "font-weight": "700",
        "text-anchor": "middle",
        "font-family": "Inter, sans-serif"
      });
      title.textContent = u.name;
      g.appendChild(title);

      var sub = svgEl("text", {
        x: u.svgX,
        y: u.svgY + 13,
        fill: isSelected ? "#38bdf8" : "#94a3b8",
        "font-size": "9.8",
        "font-weight": "600",
        "text-anchor": "middle",
        "font-family": "JetBrains Mono, monospace"
      });
      sub.textContent = u.svgSub;
      g.appendChild(sub);

      g.addEventListener("click", function () {
        selectDeploymentUnit(u.id);
      });

      svg.appendChild(g);
    });

    activeLinks.forEach(function (lnk) {
      var uFrom = unitMap[lnk.from];
      var uTo = unitMap[lnk.to];
      var midX = (uFrom.svgX + uTo.svgX) / 2;
      var midY = (uFrom.svgY + uTo.svgY) / 2;
      var labelW = Math.max(88, lnk.label.length * 6.5 + 14);

      var pill = svgEl("rect", {
        x: midX - labelW / 2,
        y: midY - 9,
        width: labelW,
        height: 18,
        rx: 5,
        fill: "#070b14",
        stroke: "#f43f5e",
        "stroke-width": "1.3"
      });
      var txt = svgEl("text", {
        x: midX,
        y: midY + 3.5,
        fill: "#f8fafc",
        "font-size": "9.2",
        "font-weight": "700",
        "text-anchor": "middle",
        "font-family": "JetBrains Mono, monospace"
      });
      txt.textContent = lnk.label;
      svg.appendChild(pill);
      svg.appendChild(txt);
    });
  }

  function renderDeploymentInspector(unit) {
    var titleEl = document.getElementById("deploy-inspector-title");
    var badgeEl = document.getElementById("deploy-inspector-badge");
    var bodyEl = document.getElementById("deploy-inspector-body");
    if (!titleEl || !badgeEl || !bodyEl) return;

    titleEl.textContent = unit.name;
    badgeEl.textContent = unit.badge;
    badgeEl.className = "badge " + unit.badgeClass;
    bodyEl.replaceChildren();

    var roleP = el("p", "inspector-text", unit.detailedRole);
    bodyEl.appendChild(roleP);

    var kvGrid = el("div", "kv-list");
    var specs = [
      ["Container / Process", unit.containerName],
      ["Image / Runtime", unit.imageOrRuntime],
      ["Ports & Protocol", unit.ports],
      ["Network Plane", unit.networkPlane],
      ["Memory Footprint", unit.ramProfile],
      ["Restart / Lifecycle", unit.restartPolicy]
    ];
    specs.forEach(function (pair) {
      var item = el("div", "kv-item");
      item.appendChild(el("div", "kv-key", pair[0]));
      item.appendChild(el("div", "kv-val", pair[1]));
      kvGrid.appendChild(item);
    });
    bodyEl.appendChild(kvGrid);

    var secSec = el("div", "inspector-section");
    secSec.appendChild(el("div", "inspector-label", "Security Hardening & Isolation Boundary"));
    secSec.appendChild(el("div", "code-block", unit.securityPosture));
    bodyEl.appendChild(secSec);

    var volSec = el("div", "inspector-section");
    volSec.appendChild(el("div", "inspector-label", "Persistent Volumes & Host Bind Mounts"));
    volSec.appendChild(el("div", "code-block", unit.volumesAndMounts));
    bodyEl.appendChild(volSec);

    var envSec = el("div", "inspector-section");
    envSec.appendChild(el("div", "inspector-label", "Environment Variables (.env / Compose) & Config Files"));
    var envText = unit.envVars.join("\n") + "\n\n# Repository Files:\n" + unit.configFiles.join("\n");
    envSec.appendChild(el("div", "code-block", envText));
    bodyEl.appendChild(envSec);

    var composeSec = el("div", "inspector-section");
    composeSec.appendChild(el("div", "inspector-label", "Docker Compose / Runtime Definition"));
    composeSec.appendChild(el("div", "code-block", unit.composeOrSpecSnippet));
    bodyEl.appendChild(composeSec);

    var opsSec = el("div", "inspector-section");
    opsSec.appendChild(el("div", "inspector-label", "Healthcheck & Operational Commands"));
    opsSec.appendChild(el("div", "code-block", unit.healthAndOpsCmd));
    bodyEl.appendChild(opsSec);
  }

  function renderDeploymentCards() {
    var container = document.getElementById("deployment-cards-container");
    var searchInput = document.getElementById("deploy-search-input");
    var zoneSelect = document.getElementById("deploy-zone-select");
    if (!container) return;

    var q = searchInput ? searchInput.value.trim().toLowerCase() : "";
    var zFilter = zoneSelect ? zoneSelect.value : "ALL";

    container.replaceChildren();

    DEPLOYMENT_UNITS.filter(function (u) {
      var matchesZone = zFilter === "ALL" || u.zone === zFilter;
      var haystack = [
        u.name,
        u.containerName,
        u.imageOrRuntime,
        u.ports,
        u.networkPlane,
        u.volumesAndMounts,
        u.securityPosture,
        u.detailedRole,
        u.envVars.join(" ")
      ].join(" ").toLowerCase();
      var matchesQ = !q || haystack.indexOf(q) !== -1;
      return matchesZone && matchesQ;
    }).forEach(function (u) {
      var card = el("div", "deploy-spec-card" + (u.id === selectedDeployId ? " selected" : ""));

      var header = el("div", "deploy-spec-header");
      var titleGroup = el("div");
      titleGroup.appendChild(el("div", "deploy-spec-name", u.name));
      titleGroup.appendChild(el("div", "deploy-spec-sub", u.containerName + " • " + u.imageOrRuntime));
      header.appendChild(titleGroup);
      header.appendChild(el("span", "badge " + u.badgeClass, u.badge));
      card.appendChild(header);

      card.appendChild(el("p", "step-desc", u.detailedRole));

      var kv = el("div", "kv-list");
      [
        ["Ports", u.ports],
        ["RAM Footprint", u.ramProfile],
        ["Network Plane", u.networkPlane],
        ["Lifecycle", u.restartPolicy]
      ].forEach(function (pair) {
        var item = el("div", "kv-item");
        item.appendChild(el("div", "kv-key", pair[0]));
        item.appendChild(el("div", "kv-val", pair[1]));
        kv.appendChild(item);
      });
      card.appendChild(kv);

      var volLabel = el("div", "inspector-label", "Volumes, Mounts & Security Posture");
      card.appendChild(volLabel);
      card.appendChild(el("div", "code-block", "Mounts: " + u.volumesAndMounts.replace(/\n/g, " | ") + "\nSecurity: " + u.securityPosture));

      var tagRow = el("div", "deploy-tag-list");
      u.envVars.forEach(function (ev) {
        tagRow.appendChild(el("span", "deploy-tag", ev));
      });
      card.appendChild(tagRow);

      var actionRow = el("div", "player-controls");
      var focusBtn = el("button", "btn" + (u.id === selectedDeployId ? " btn-primary" : ""), u.id === selectedDeployId ? "Selected in Diagram" : "Inspect in Deployment Diagram");
      focusBtn.setAttribute("type", "button");
      focusBtn.addEventListener("click", function () {
        selectDeploymentUnit(u.id);
        var stage = document.getElementById("deployment-svg");
        if (stage && stage.scrollIntoView) {
          stage.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      });
      actionRow.appendChild(focusBtn);
      card.appendChild(actionRow);

      container.appendChild(card);
    });
  }

  function renderDeploymentMatrix() {
    var tbody = document.getElementById("deployment-matrix-body");
    if (!tbody) return;
    tbody.replaceChildren();

    DEPLOYMENT_UNITS.forEach(function (u) {
      var tr = el("tr");
      tr.addEventListener("click", function () {
        selectDeploymentUnit(u.id);
      });

      var tdName = el("td");
      tdName.appendChild(el("strong", "", u.name));
      tr.appendChild(tdName);

      tr.appendChild(el("td", "arch-node-meta", u.containerName));
      tr.appendChild(el("td", "arch-node-meta", u.imageOrRuntime));
      tr.appendChild(el("td", "arch-node-meta", u.ports));

      var tdNet = el("td");
      tdNet.appendChild(el("span", "badge " + u.badgeClass, u.networkPlane));
      tr.appendChild(tdNet);

      tr.appendChild(el("td", "arch-node-meta", u.volumesAndMounts.replace(/\n/g, ", ")));
      tr.appendChild(el("td", "arch-node-meta", u.ramProfile));
      tr.appendChild(el("td", "", u.securityPosture));

      tbody.appendChild(tr);
    });
  }

  function selectDeploymentUnit(id) {
    selectedDeployId = id;
    var found = DEPLOYMENT_UNITS.find(function (u) {
      return u.id === id;
    }) || DEPLOYMENT_UNITS[0];
    renderDeploymentDiagram();
    renderDeploymentInspector(found);
    renderDeploymentCards();
  }

  function initFilters() {
    var zoneBtns = [
      { id: "deploy-zone-all", zone: "ALL" },
      { id: "deploy-zone-docker", zone: "docker-net" },
      { id: "deploy-zone-host", zone: "host-native" },
      { id: "deploy-zone-sandbox", zone: "airgap-sandbox" },
      { id: "deploy-zone-external", zone: "external-edge" }
    ];
    zoneBtns.forEach(function (zb) {
      var elBtn = document.getElementById(zb.id);
      if (elBtn) {
        elBtn.addEventListener("click", function () {
          activeDeployZone = zb.zone;
          zoneBtns.forEach(function (other) {
            var b = document.getElementById(other.id);
            if (b) b.classList.toggle("btn-primary", other.id === zb.id);
          });
          var zoneSelect = document.getElementById("deploy-zone-select");
          if (zoneSelect) zoneSelect.value = zb.zone;
          renderDeploymentDiagram();
          renderDeploymentCards();
        });
      }
    });

    var deploySearch = document.getElementById("deploy-search-input");
    var deployZoneSelect = document.getElementById("deploy-zone-select");
    if (deploySearch) {
      deploySearch.addEventListener("input", renderDeploymentCards);
    }
    if (deployZoneSelect) {
      deployZoneSelect.addEventListener("change", function () {
        activeDeployZone = deployZoneSelect.value;
        renderDeploymentDiagram();
        renderDeploymentCards();
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    initFilters();
    selectDeploymentUnit(selectedDeployId);
    renderDeploymentMatrix();
  });
})();

