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

  var COMPONENTS = [
    {
      id: "traefik",
      layer: "ingress",
      name: "Traefik v3 Gateway",
      shortMeta: "Go • :80/:443/:8088 • 45 MB",
      badge: "EDGE ROUTER",
      badgeClass: "badge-blue",
      language: "Go (traefik:v3.0)",
      ramMb: 45,
      replacedTool: "Keycloak / Kong (1.8 GB)",
      port: "80 / 443 / 8088",
      files: ["src/config/traefik.yml", "src/config/auth.yml", "docker-compose.yml"],
      connectedTo: ["fastapi", "minio", "temporal"],
      summary: "Dynamic edge reverse proxy handling HTTP/HTTPS ingress, rate limiting, and routing to internal platform services with under 50 MB RAM.",
      cliOrApi: "HTTP Ingress :80 / Dashboard :8088",
      codeSnippet: "# src/config/traefik.yml\nentryPoints:\n  web:\n    address: \":80\"\n  websecure:\n    address: \":443\"\nproviders:\n  docker:\n    exposedByDefault: false\n  file:\n    directory: /etc/traefik/dynamic"
    },
    {
      id: "fastapi",
      layer: "ingress",
      name: "FastAPI Unified Gateway",
      shortMeta: "Python 3.12 • :8000 • 34 Routes",
      badge: "REST GATEWAY",
      badgeClass: "badge-blue",
      language: "Python 3.12 / Uvicorn",
      ramMb: 110,
      replacedTool: "Spring Cloud Gateway (1.2 GB)",
      port: "8000",
      files: ["src/api.py", "src/security/middleware.py", "src/security/jwt.py"],
      connectedTo: ["dom_auth", "dom_ingestion", "dom_analytics", "dom_graph", "dom_ai", "dom_pipeline", "dom_project", "dom_discovery"],
      summary: "Unified hexagonal transport gateway mounting 9 domain routers (34 endpoints), enforcing JWT Bearer authentication, ContextVar user propagation, and optional Langfuse OpenTelemetry tracing.",
      cliOrApi: "make api -> uvicorn src.api:app --port 8000",
      codeSnippet: "app = FastAPI(\n    title=\"Artemis Unified Domain Gateway\",\n    version=\"0.3.0\",\n    lifespan=lifespan,\n    dependencies=[Depends(authenticate_user)],\n)\n# Mounts auth, analytics, ai, ingestion, graph, pipeline, project, discovery"
    },
    {
      id: "cli",
      layer: "ingress",
      name: "Unified CLI (artemis)",
      shortMeta: "Click CLI • Direct & Token Auth",
      badge: "OPERATOR CLI",
      badgeClass: "badge-emerald",
      language: "Python 3.12 (Click + Tabulate)",
      ramMb: 35,
      replacedTool: "Disparate JVM Admin CLIs",
      port: "In-Process / Local Socket",
      files: ["src/cli/main.py", "src/cli/commands/ask.py", "src/cli/commands/project.py", "src/cli/commands/discover.py"],
      connectedTo: ["dom_auth", "dom_ingestion", "dom_analytics", "dom_ai", "dom_pipeline", "dom_project", "dom_discovery"],
      summary: "Single operator command-line entrypoint supporting human-readable tables and --json machine output across status, login, whoami, query, ask, pipeline, project, and discover command groups.",
      cliOrApi: "artemis [status|login|whoami|query|ask|pipeline|project|discover]",
      codeSnippet: "$ artemis login -u admin -p admin\n$ artemis status --json\n$ artemis ask \"Which projects reference account ACCT-99812?\"\n$ artemis discover entity --value ACCT-99812 --fuzzy"
    },
    {
      id: "dom_auth",
      layer: "domains",
      name: "1. Auth Domain",
      shortMeta: "AuthFacade • JWT & Passlib",
      badge: "DOMAIN 01",
      badgeClass: "badge-purple",
      language: "Python 3.12 (PyJWT + bcrypt)",
      ramMb: 15,
      replacedTool: "External OAuth/JVM IAM",
      port: "/api/v1/auth/*",
      files: ["src/domains/auth/facade/auth.py", "src/domains/auth/api/router.py", "src/security/jwt.py"],
      connectedTo: ["postgres", "fastapi", "cli"],
      summary: "Manages operator authentication, credential verification, and HS256 JWT token generation cached at ~/.artemis/token with 0600 permissions.",
      cliOrApi: "POST /api/v1/auth/token | artemis login | artemis whoami",
      codeSnippet: "class AuthFacade(DomainFacade):\n    async def authenticate(self, req: TokenRequestContract) -> TokenResponseContract:\n        # Validates user credentials and issues signed JWT Bearer token"
    },
    {
      id: "dom_ingestion",
      layer: "domains",
      name: "2. Ingestion Domain",
      shortMeta: "IngestionFacade • MQTT & Flush",
      badge: "DOMAIN 02",
      badgeClass: "badge-purple",
      language: "Python 3.12 + PyArrow",
      ramMb: 45,
      replacedTool: "Kafka Connect / Gobblin",
      port: "/api/v1/ingestion/*",
      files: ["src/domains/ingestion/facade/ingestion.py", "src/domains/ingestion/operations/flush.py", "src/services/ingestion/mqtt_listener.py"],
      connectedTo: ["mosquitto", "disk_buffer", "minio", "postgres", "temporal"],
      summary: "Handles high-rate MQTT sensor event validation, POSIX atomic disk buffering, crash-resilient file rotation, and Snappy Parquet compaction into MinIO.",
      cliOrApi: "POST /api/v1/ingestion/flush | artemis pipeline run mqtt_to_minio",
      codeSnippet: "# Atomic zero-downtime buffer rotation\nprocessing_file = buffer_dir / f\"events.processing.{timestamp}.jsonl\"\nbuffer_file.rename(processing_file)\nobject_key = writer.write_batch(valid_events)"
    },
    {
      id: "dom_analytics",
      layer: "domains",
      name: "3. Analytics Domain",
      shortMeta: "AnalyticsFacade • DuckDB SQL",
      badge: "DOMAIN 03",
      badgeClass: "badge-purple",
      language: "Python 3.12 + DuckDB C++",
      ramMb: 120,
      replacedTool: "Apache Spark SQL / Trino",
      port: "/api/v1/analytics/*",
      files: ["src/domains/analytics/facade/analytics.py", "src/domains/analytics/operations/project_query.py", "src/services/analytics/duckdb_client.py"],
      connectedTo: ["duckdb", "minio"],
      summary: "Executes sub-second vectorized analytical SQL over MinIO Parquet lakes and enforces strict S3 prefix confinement (s3://telemetry/projects/{id}/*) for project queries.",
      cliOrApi: "POST /api/v1/analytics/query | artemis query --sql \"...\"",
      codeSnippet: "# ProjectQueryExecutor S3 prefix confinement guardrail\nexpected_prefix = f\"s3://telemetry/projects/{project_id}/\"\nif not uri.startswith(expected_prefix):\n    raise PermissionError(f\"Cross-project S3 access denied: {uri}\")"
    },
    {
      id: "dom_graph",
      layer: "domains",
      name: "4. Graph Domain",
      shortMeta: "GraphFacade • OSINT & Bolt",
      badge: "DOMAIN 04",
      badgeClass: "badge-purple",
      language: "Python 3.12 + Bolt Driver",
      ramMb: 30,
      replacedTool: "OpenCTI Workers (JVM/Node)",
      port: "/api/v1/graph/*",
      files: ["src/domains/graph/facade/graph.py", "src/domains/graph/operations/import_osint.py", "src/services/graph/osint_importer.py"],
      connectedTo: ["memgraph", "temporal"],
      summary: "Manages property graph nodes, edges, and SpiderFoot reconnaissance JSON imports using idempotent openCypher MERGE statements.",
      cliOrApi: "POST /api/v1/graph/import-osint | GET /api/v1/graph/related",
      codeSnippet: "MERGE (n:IP_ADDRESS {name: $name})\nON CREATE SET n.confidence = $confidence, n.created_at = timestamp()\nON MATCH SET n.confidence = $confidence"
    },
    {
      id: "dom_ai",
      layer: "domains",
      name: "5. AI Domain",
      shortMeta: "AIFacade • ADK + 6-Tool Loop",
      badge: "DOMAIN 05",
      badgeClass: "badge-purple",
      language: "Python 3.12 + google-genai",
      ramMb: 35,
      replacedTool: "LangChain + Local vLLM",
      port: "/api/v1/ai/ask",
      files: ["src/domains/ai/facade/ai.py", "src/domains/ai/operations/dynamic_loop.py", "src/domains/ai/operations/tools.py", "src/domains/ai/operations/guardrails.py"],
      connectedTo: ["adk_loop", "gemini", "duckdb", "memgraph", "redis", "postgres"],
      summary: "Orchestrates PlannerAgent, GuardianCriticAgent, and DynamicAgentLoop with 6 read-only tools across DuckDB, Memgraph, and KDG, backed by Redis semantic caching and PostgreSQL audit logs.",
      cliOrApi: "POST /api/v1/ai/ask | artemis ask \"<question>\"",
      codeSnippet: "tool_map = {\n    \"query_analytics\": self.tools.query_analytics,\n    \"query_graph\": self.tools.query_graph,\n    \"get_schema_info\": self.tools.get_schema_info,\n    \"discover_workspace_schema\": self.tools.discover_workspace_schema,\n    \"find_cross_project_entities\": self.tools.find_cross_project_entities,\n    \"get_data_lineage\": self.tools.get_data_lineage,\n}"
    },
    {
      id: "dom_pipeline",
      layer: "domains",
      name: "6. Pipeline Domain",
      shortMeta: "PipelineFacade • AST & Sandbox",
      badge: "DOMAIN 06",
      badgeClass: "badge-purple",
      language: "Python 3.12 + Docker SDK",
      ramMb: 40,
      replacedTool: "Apache Airflow + Spark Submit",
      port: "/api/v1/projects/{id}/pipelines/*",
      files: ["src/domains/pipeline/facade/pipeline.py", "src/domains/pipeline/operations/script_validator.py", "src/domains/pipeline/operations/docker_runner.py"],
      connectedTo: ["docker_sandbox", "minio", "postgres", "memgraph"],
      summary: "Validates user Python transformation scripts via ast.parse(), manages immutable pipeline versions, executes scripts inside rootless network-isolated Docker containers, and records KDG lineage.",
      cliOrApi: "artemis project pipeline [create|list|get|update|delete|run|runs]",
      codeSnippet: "# Ephemeral rootless container execution\ncontainer = self.client.containers.run(\n    image=docker_image,\n    network_mode=\"none\",\n    mem_limit=\"2g\",\n    nano_cpus=2_000_000_000,\n    user=\"artemis\",\n    volumes={input_dir: {\"bind\": \"/workspace/input\", \"mode\": \"ro\"}, ...}\n)"
    },
    {
      id: "dom_project",
      layer: "domains",
      name: "7. Project Domain",
      shortMeta: "ProjectFacade • Medallion & RBAC",
      badge: "DOMAIN 07",
      badgeClass: "badge-purple",
      language: "Python 3.12",
      ramMb: 30,
      replacedTool: "Databricks Workspaces / Ranger",
      port: "/api/v1/projects/*",
      files: ["src/domains/project/facade/project.py", "src/domains/project/operations/scoped_ingestion.py", "src/domains/project/operations/membership.py"],
      connectedTo: ["minio", "postgres", "memgraph", "dom_discovery"],
      summary: "Manages isolated multi-tier workspaces (BRONZE, SILVER, GOLD), project membership RBAC (owner, member), and heterogeneous tabular/text/graph ingestion.",
      cliOrApi: "artemis project [create|list|info|delete|ingest|ingest-graph|query|members]",
      codeSnippet: "# S3 Medallion path partitioning\ns3_key = f\"projects/{project_id}/{tier.lower()}/{dataset_name}/year={now:%Y}/month={now:%m}/day={now:%d}/part_{ts}.parquet\""
    },
    {
      id: "dom_discovery",
      layer: "domains",
      name: "8. Discovery Domain (KDG)",
      shortMeta: "DiscoveryFacade • KDG & Lineage",
      badge: "DOMAIN 08",
      badgeClass: "badge-purple",
      language: "Python 3.12 + Rapidfuzz",
      ramMb: 45,
      replacedTool: "Apache Atlas / DataHub (JVM)",
      port: "/api/v1/discovery/*",
      files: ["src/domains/discovery/facade/discovery.py", "src/domains/discovery/operations/structural_indexer.py", "src/domains/discovery/operations/entity_resolution.py", "src/domains/discovery/operations/kdg_graph_store.py"],
      connectedTo: ["memgraph", "postgres", "temporal"],
      summary: "Universal Domain-Agnostic Knowledge Discovery Graph providing 2-phase indexing, 9 regex pattern classifiers, Rapidfuzz + DSU cross-project entity resolution, and zero-trust member-scoped lineage.",
      cliOrApi: "artemis discover [entity|lineage|jobs|reindex] | artemis project discover <id>",
      codeSnippet: "# Zero-trust Cypher membership parameter filtering\nMATCH (w:Workspace)-[:OWNS]->(r:DataResource)-[:CONTAINS_ENTITY]->(e:GenericEntity)\nWHERE w.project_id IN $member_projects AND toLower(e.value) = toLower($value)"
    },
    {
      id: "temporal",
      layer: "orchestration",
      name: "Temporal Workflow Engine",
      shortMeta: "Go Server • :7233 / UI :8233",
      badge: "ORCHESTRATOR",
      badgeClass: "badge-amber",
      language: "Go (temporalio/auto-setup:1.24)",
      ramMb: 380,
      replacedTool: "Apache Airflow + Celery (1.8 GB)",
      port: "7233 (gRPC) / 8233 (UI)",
      files: ["src/base/temporal.py", "src/domains/ingestion/operations/flush.py", "src/domains/discovery/operations/enrichment_workflow.py"],
      connectedTo: ["postgres", "dom_ingestion", "dom_graph", "dom_discovery"],
      summary: "Durable workflow orchestration coordinating FlushBufferWorkflow, OsintImportWorkflow, and asynchronous KDGEnrichmentWorkflow activities.",
      cliOrApi: "Temporal gRPC :7233 | Temporal Web UI :8233",
      codeSnippet: "# Durable workflows registered across domains\n- FlushBufferWorkflow (Rotate -> ConvertParquet -> UploadMinIO)\n- OsintImportWorkflow (ParseSpiderfoot -> ImportMemgraph)\n- KDGEnrichmentWorkflow (TaxonomyMap -> TextNER -> EntityResolution)"
    },
    {
      id: "adk_loop",
      layer: "orchestration",
      name: "ADK + DynamicAgentLoop",
      shortMeta: "Planner -> Critic -> 6 Tools",
      badge: "AI REASONING",
      badgeClass: "badge-amber",
      language: "Python 3.12 + Google ADK",
      ramMb: 25,
      replacedTool: "Heavy Multi-Container Agent Frameworks",
      port: "In-Process Async Loop",
      files: ["src/domains/ai/operations/ai_agents.py", "src/domains/ai/operations/dynamic_loop.py", "src/domains/ai/operations/guardrails.py"],
      connectedTo: ["dom_ai", "gemini", "duckdb", "memgraph"],
      summary: "Executes PlannerAgent and GuardianCriticAgent followed by up to 5 turns of autonomous function calling with AST read-only SQL/Cypher guardrails.",
      cliOrApi: "Invoked automatically via AIFacade.ask()",
      codeSnippet: "# Read-only guardrails enforce zero mutation risk\nvalidate_read_only_sql(sql_query)     # Blocks DROP, DELETE, INSERT, COPY...\nvalidate_read_only_cypher(cypher)     # Blocks CREATE, MERGE, SET, DELETE..."
    },
    {
      id: "docker_sandbox",
      layer: "orchestration",
      name: "Ephemeral Docker Sandbox",
      shortMeta: "network=none • 2GB • UID 10001",
      badge: "SANDBOX",
      badgeClass: "badge-amber",
      language: "Docker Engine + Python 3.12 Slim",
      ramMb: 0,
      replacedTool: "Kubernetes Pod Operator / YARN",
      port: "None (network_mode='none')",
      files: ["docker/pipeline-runner/Dockerfile", "src/domains/pipeline/operations/docker_runner.py"],
      connectedTo: ["dom_pipeline", "minio"],
      summary: "Runs untrusted user transformation scripts inside an ephemeral rootless container with zero network access, 2 GB memory cap, 2.0 CPU limit, and 300s timeout.",
      cliOrApi: "artemis project pipeline run --project <id> --name <pipe> ...",
      codeSnippet: "FROM python:3.12-slim\nRUN groupadd -g 10001 artemis && useradd -u 10001 -g artemis -m artemis\nUSER artemis:artemis\nWORKDIR /workspace"
    },
    {
      id: "fail_fast",
      layer: "orchestration",
      name: "Fail-Fast & Pytest Harness",
      shortMeta: "Feature 006 • Zero Prod Mocks",
      badge: "CLEAN ARCH",
      badgeClass: "badge-rose",
      language: "Python 3.12 (src/core/exceptions.py)",
      ramMb: 0,
      replacedTool: "Embedded Prod Mock Flags",
      port: "N/A",
      files: ["src/core/exceptions.py", "tests/conftest.py", "tests/fixtures/mocks/"],
      connectedTo: ["dom_ai", "dom_graph", "dom_pipeline", "dom_discovery"],
      summary: "Guarantees 0% test simulation code inside src/. Production fails fast with ConfigurationError, ConnectionError, or ServiceUnavailableError; tests inject 6 reusable mocks from tests/fixtures/mocks/.",
      cliOrApi: "make test -> 162/162 offline tests passing",
      codeSnippet: "class ArtemisError(Exception): ...\nclass ConfigurationError(ArtemisError): ...\nclass ConnectionError(ArtemisError): ...\nclass ServiceUnavailableError(ArtemisError): ..."
    },
    {
      id: "mosquitto",
      layer: "infra",
      name: "Eclipse Mosquitto",
      shortMeta: "C Broker • :1883 • 18 MB RAM",
      badge: "C NATIVE",
      badgeClass: "badge-emerald",
      language: "ANSI C (eclipse-mosquitto:2)",
      ramMb: 18,
      replacedTool: "Apache Kafka + ZooKeeper (4.5 GB)",
      port: "1883",
      files: ["src/config/mosquitto.conf", "src/services/ingestion/mqtt_listener.py", "tools/simulate_telemetry.py"],
      connectedTo: ["disk_buffer", "dom_ingestion"],
      summary: "Ultra-lightweight C MQTT broker handling 1,000+ telemetry events/sec on topic telemetry/# with < 20 MB idle RAM.",
      cliOrApi: "make simulate-telemetry (tools/simulate_telemetry.py)",
      codeSnippet: "# src/config/mosquitto.conf\nlistener 1883\nallow_anonymous true\npersistence true\npersistence_location /mosquitto/data/"
    },
    {
      id: "disk_buffer",
      layer: "infra",
      name: "POSIX Local Disk Buffer",
      shortMeta: "O_APPEND + Atomic rename()",
      badge: "FILESYSTEM",
      badgeClass: "badge-emerald",
      language: "Linux VFS / POSIX JSONL",
      ramMb: 5,
      replacedTool: "Redpanda / NATS Memory Streams",
      port: "/tmp/artemis/buffer/events.jsonl",
      files: ["src/services/ingestion/mqtt_listener.py", "src/pipelines/mqtt_to_minio.py"],
      connectedTo: ["mosquitto", "minio", "dom_ingestion"],
      summary: "Decouples high-frequency MQTT ingestion from S3 batch writes using lock-free O_APPEND writes and atomic POSIX os.rename() rotation with automatic crash recovery.",
      cliOrApi: "/tmp/artemis/buffer/events.jsonl",
      codeSnippet: "# Crash recovery on startup\nfor leftover in buffer_dir.glob(\"events.processing.*.jsonl\"):\n    # Restores interrupted batch lines before rotating current buffer"
    },
    {
      id: "minio",
      layer: "infra",
      name: "MinIO S3 Lakehouse",
      shortMeta: "Go • :9000/:9001 • 280 MB RAM",
      badge: "GO NATIVE",
      badgeClass: "badge-emerald",
      language: "Go (minio/minio:latest)",
      ramMb: 280,
      replacedTool: "Hadoop HDFS NameNode/DataNode (6.0 GB)",
      port: "9000 (S3 API) / 9001 (Console)",
      files: ["src/services/ingestion/minio_writer.py", "src/domains/project/operations/scoped_ingestion.py"],
      connectedTo: ["duckdb", "dom_ingestion", "dom_project", "dom_pipeline"],
      summary: "High-performance S3-compatible object lake storing Snappy-compressed Apache Parquet files partitioned by date and Medallion project tier (BRONZE, SILVER, GOLD).",
      cliOrApi: "s3://telemetry/year=YYYY/... & s3://telemetry/projects/{id}/{tier}/...",
      codeSnippet: "PARQUET_SCHEMA = pa.schema([\n    (\"event_id\", pa.string()),\n    (\"timestamp\", pa.timestamp(\"us\", tz=\"UTC\")),\n    (\"device_id\", pa.string()),\n    (\"metric_name\", pa.string()),\n    (\"value\", pa.float64()),\n])"
    },
    {
      id: "duckdb",
      layer: "infra",
      name: "DuckDB Vectorized Engine",
      shortMeta: "C++ Embedded • httpfs S3 • 150 MB",
      badge: "C++ NATIVE",
      badgeClass: "badge-emerald",
      language: "C++ (Embedded Python Extension)",
      ramMb: 150,
      replacedTool: "Apache Spark / Trino Cluster (8.0 GB)",
      port: "In-Process (Zero Daemon Overhead)",
      files: ["src/services/analytics/duckdb_client.py", "src/domains/analytics/operations/project_query.py"],
      connectedTo: ["minio", "dom_analytics", "dom_ai"],
      summary: "Embedded columnar C++ OLAP engine executing SIMD-vectorized SQL queries directly over MinIO S3 Parquet files via the httpfs extension in milliseconds.",
      cliOrApi: "artemis query --sql \"SELECT ... FROM read_parquet('s3://telemetry/**/*.parquet')\"",
      codeSnippet: "INSTALL httpfs; LOAD httpfs;\nSET s3_endpoint='localhost:9000';\nSET s3_url_style='path';\nSET s3_use_ssl=false;\nSELECT metric_name, AVG(value) FROM read_parquet('s3://telemetry/**/*.parquet') GROUP BY 1;"
    },
    {
      id: "memgraph",
      layer: "infra",
      name: "Memgraph Graph + KDG",
      shortMeta: "C++ Bolt • :7687 • 420 MB RAM",
      badge: "C++ NATIVE",
      badgeClass: "badge-emerald",
      language: "C++ (memgraph/memgraph:latest)",
      ramMb: 420,
      replacedTool: "Neo4j JVM + OpenSearch (6.5 GB)",
      port: "7687 (Bolt)",
      files: ["src/services/graph/memgraph_client.py", "src/domains/discovery/operations/kdg_graph_store.py"],
      connectedTo: ["dom_graph", "dom_discovery", "dom_ai", "dom_project"],
      summary: "In-memory C++ openCypher property graph hosting both threat intelligence entities (OSINT/anomalies) and the Universal Knowledge Discovery Graph (Workspace, DataResource, DataAttribute, GenericEntity, SemanticTaxonomy, PipelineExecution).",
      cliOrApi: "bolt://localhost:7687 | make seed-graph | artemis discover ...",
      codeSnippet: "# Fast TCP socket pre-check before Bolt driver execution\nsock.connect((self.host, int(self.port)))\n# Raises ConnectionError immediately if Memgraph is down"
    },
    {
      id: "postgres",
      layer: "infra",
      name: "PostgreSQL 16 Metadata & Audit",
      shortMeta: "C RDBMS • :5433 • 180 MB RAM",
      badge: "C NATIVE",
      badgeClass: "badge-emerald",
      language: "C (postgres:16-alpine)",
      ramMb: 180,
      replacedTool: "Cassandra / Hive Metastore (3.5 GB)",
      port: "5433 -> 5432",
      files: ["src/config/postgres_init.sql", "src/database/engine.py", "src/services/ai/audit_logger.py"],
      connectedTo: ["dom_auth", "dom_project", "dom_pipeline", "dom_discovery", "dom_ai", "temporal"],
      summary: "Stores relational catalog tables: pipelines, pipeline_runs, ai_queries, projects, project_pipelines, project_pipeline_runs, project_datasets, project_members, and kdg_index_jobs.",
      cliOrApi: "PostgreSQL :5433 (8 Core Schema Tables)",
      codeSnippet: "-- 8 Core Tables in src/config/postgres_init.sql\npipelines, pipeline_runs, ai_queries,\nprojects, project_pipelines, project_pipeline_runs,\nproject_datasets, project_members, kdg_index_jobs"
    },
    {
      id: "redis",
      layer: "infra",
      name: "Redis 7 Semantic Cache",
      shortMeta: "C In-Memory • :6379 • 35 MB RAM",
      badge: "C NATIVE",
      badgeClass: "badge-emerald",
      language: "ANSI C (redis:7-alpine)",
      ramMb: 35,
      replacedTool: "Hazelcast / Ignite JVM (1.5 GB)",
      port: "6379",
      files: ["src/services/ai/cache.py"],
      connectedTo: ["dom_ai"],
      summary: "Provides sub-millisecond SHA-256 semantic prompt caching (1-hour TTL) and 60 req/min sliding-window rate limiting per analyst.",
      cliOrApi: "Redis :6379 (artemis:ai:query:<sha256>)",
      codeSnippet: "key = f\"artemis:ai:query:{hashlib.sha256(normalized.encode()).hexdigest()}\"\n# Returns cached AI synthesis in < 3ms on cache hit"
    },
    {
      id: "gemini",
      layer: "infra",
      name: "Google AI Studio API",
      shortMeta: "gemini-2.5-flash-lite • 0 MB Local GPU",
      badge: "CLOUD LLM",
      badgeClass: "badge-blue",
      language: "Cloud API (google-genai SDK)",
      ramMb: 15,
      replacedTool: "Local Ollama / vLLM 8B-24B (14.0 GB)",
      port: "HTTPS (443)",
      files: ["src/domains/ai/operations/dynamic_loop.py", "src/services/ai/genai_service.py"],
      connectedTo: ["dom_ai", "adk_loop"],
      summary: "Offloads heavy LLM token synthesis and multi-turn function calling to gemini-2.5-flash-lite, preserving 100% of local VM CPU and RAM for lakehouse and graph engines.",
      cliOrApi: "GOOGLE_AI_STUDIO_API_KEY in .env",
      codeSnippet: "response = self._client.models.generate_content(\n    model=\"gemini-2.5-flash-lite\",\n    contents=contents,\n    config=config, # 6 tools + temperature=0.1\n)"
    }
  ];

  var WORKLOADS = [
    { id: "base", name: "Base Platform Idle (All Containers Up)", artemisMb: 2850, jvmMb: 28500, active: true, locked: true },
    { id: "mqtt_burst", name: "10,000 evt/s MQTT Burst + Parquet Flush", artemisMb: 450, jvmMb: 3200, active: false, locked: false },
    { id: "duckdb_olap", name: "1M-Row Vectorized Parquet Aggregation", artemisMb: 850, jvmMb: 4500, active: false, locked: false },
    { id: "docker_sandbox", name: "Ephemeral Docker Sandbox Pipeline Run", artemisMb: 2048, jvmMb: 3500, active: false, locked: false },
    { id: "kdg_index", name: "KDG Phase 1+2 Indexing & Entity Resolution", artemisMb: 380, jvmMb: 2800, active: false, locked: false },
    { id: "ai_rag", name: "Concurrent Analyst AI Multi-Tool Queries", artemisMb: 90, jvmMb: 12000, active: false, locked: false }
  ];

  var RAM_TABLE_ROWS = [
    ["Ingestion Bus", "Eclipse Mosquitto (C)", "18 MB", "Apache Kafka + ZooKeeper (JVM)", "4,500 MB"],
    ["Object Lakehouse", "MinIO S3 (Go)", "280 MB", "Hadoop HDFS Name/DataNode (JVM)", "6,000 MB"],
    ["Columnar OLAP", "DuckDB Embedded (C++)", "150 MB", "Apache Spark / Trino Cluster (JVM)", "8,000 MB"],
    ["Knowledge Graph & KDG", "Memgraph Bolt (C++)", "420 MB", "Neo4j + OpenCTI + Elastic (JVM)", "6,500 MB"],
    ["Workflow Orchestration", "Temporal Server (Go)", "380 MB", "Apache Airflow + Celery Workers", "1,800 MB"],
    ["Edge Proxy & Auth", "Traefik v3 + FastAPI", "155 MB", "Keycloak + Kong Gateway (JVM)", "1,800 MB"],
    ["State & Semantic Cache", "PostgreSQL 16 + Redis 7 (C)", "215 MB", "Cassandra + Hazelcast (JVM)", "3,500 MB"],
    ["Generative AI & RAG", "Google AI Studio API Client", "15 MB", "Local Ollama / vLLM (CPU/RAM)", "12,000 MB"]
  ];

  var API_CATALOG = [
    ["System", "GET /health", "artemis status", "Public", "Gateway health & version (0.3.0)"],
    ["auth", "POST /api/v1/auth/token", "artemis login / whoami", "Public (Issues JWT)", "TokenResponseContract (~/.artemis/token)"],
    ["ingestion", "POST /api/v1/ingestion/event", "tools/simulate_telemetry.py", "JWT Bearer", "Append validated TelemetryEvent to disk buffer"],
    ["ingestion", "POST /api/v1/ingestion/flush", "artemis pipeline run mqtt_to_minio", "JWT Bearer", "Atomic buffer rotation & Snappy Parquet upload"],
    ["analytics", "POST /api/v1/analytics/query", "artemis query --sql \"...\"", "JWT + Read-Only SQL", "QueryResultContract over s3://telemetry/**"],
    ["graph", "POST /api/v1/graph/node", "make seed-graph", "JWT Bearer", "Upsert entity node into Memgraph"],
    ["graph", "POST /api/v1/graph/edge", "make seed-graph", "JWT Bearer", "Upsert directed relationship edge"],
    ["graph", "POST /api/v1/graph/import-osint", "OsintImporter", "JWT Bearer", "OsintImportResultContract (SpiderFoot JSON)"],
    ["graph", "GET /api/v1/graph/related", "artemis ask (context)", "JWT Bearer", "RelatedEntitiesResultContract (1-hop traversal)"],
    ["ai", "POST /api/v1/ai/ask", "artemis ask \"<prompt>\"", "JWT + 60 req/m + Read-Only", "AIQueryResponseContract (6-tool DynamicAgentLoop)"],
    ["pipeline", "POST /api/v1/pipeline/run", "artemis pipeline run <name>", "JWT Bearer", "Execute named system batch pipeline"],
    ["project", "POST /api/v1/projects", "artemis project create", "JWT Bearer (Creator=Owner)", "ProjectResponseContract + owner membership"],
    ["project", "GET /api/v1/projects", "artemis project list", "JWT Bearer", "List[ProjectResponseContract]"],
    ["project", "GET /api/v1/projects/{project_id}", "artemis project info", "JWT Bearer", "ProjectResponseContract metadata"],
    ["project", "DELETE /api/v1/projects/{project_id}", "artemis project delete", "JWT Bearer", "Cascade delete project workspace"],
    ["project", "POST /api/v1/projects/{project_id}/ingest/tabular", "artemis project ingest", "JWT Bearer", "TabularIngestResponseContract + KDG Phase 1 index"],
    ["project", "POST /api/v1/projects/{project_id}/ingest/graph", "artemis project ingest-graph", "JWT Bearer", "GraphIngestResponseContract + project_id tag"],
    ["project", "GET /api/v1/projects/{project_id}/datasets", "artemis project info", "JWT Bearer", "List[ProjectDatasetContract] across tiers"],
    ["project", "POST /api/v1/projects/{project_id}/query", "artemis project query", "JWT + S3 Prefix Confinement", "Scoped DuckDB SQL on s3://telemetry/projects/{id}/*"],
    ["project", "GET /api/v1/projects/{project_id}/runs", "artemis project pipeline runs", "JWT Bearer", "List historical project pipeline runs"],
    ["project", "GET /api/v1/projects/{project_id}/members", "artemis project members list", "JWT + Project Member", "List[MemberContract] (owner / member)"],
    ["project", "POST /api/v1/projects/{project_id}/members", "artemis project members add", "JWT + Project Owner/Admin", "Grant or update project role"],
    ["project", "DELETE /api/v1/projects/{project_id}/members/{uid}", "artemis project members remove", "JWT + Owner (Last-Owner Guard)", "Revoke member access (204 No Content)"],
    ["pipeline", "POST /api/v1/projects/{project_id}/pipelines", "artemis project pipeline create", "JWT + AST Script Validator", "PipelineResponseContract (ast.parse verified)"],
    ["pipeline", "GET /api/v1/projects/{project_id}/pipelines", "artemis project pipeline list", "JWT Bearer", "List[PipelineResponseContract]"],
    ["pipeline", "GET /api/v1/projects/{project_id}/pipelines/{id}", "artemis project pipeline get", "JWT Bearer", "PipelineResponseContract definition"],
    ["pipeline", "PUT /api/v1/projects/{project_id}/pipelines/{id}", "artemis project pipeline update", "JWT + AST Script Validator", "Atomically increments pipeline version"],
    ["pipeline", "DELETE /api/v1/projects/{project_id}/pipelines/{id}", "artemis project pipeline delete", "JWT Bearer", "Delete project pipeline definition"],
    ["pipeline", "POST /api/v1/projects/{project_id}/pipelines/{id}/run", "artemis project pipeline run", "JWT + Docker Sandbox (net=none)", "PipelineRunResponseContract + KDG lineage"],
    ["pipeline", "GET /api/v1/projects/{project_id}/pipelines/{id}/runs", "artemis project pipeline runs", "JWT Bearer", "List[PipelineRunResponseContract]"],
    ["discovery", "GET /api/v1/discovery/workspace/{project_id}", "artemis project discover <id>", "JWT + Project Member Confinement", "WorkspaceKnowledgeContract (datasets, attributes, entities)"],
    ["discovery", "GET /api/v1/discovery/cross-project", "artemis discover entity", "JWT + Member Projects Filter", "EntityCorrelationContract (exact & Rapidfuzz SAME_AS)"],
    ["discovery", "GET /api/v1/discovery/lineage/{proj}/{dataset}", "artemis discover lineage", "JWT + Project Member Confinement", "LineageContract (DERIVED_FROM & PRODUCED DAG)"],
    ["discovery", "POST /api/v1/discovery/reindex/{project_id}", "artemis discover reindex", "JWT + Project Owner/Admin", "IndexJobContract (202 Accepted)"],
    ["discovery", "GET /api/v1/discovery/jobs/{project_id}", "artemis discover jobs", "JWT + Project Member Confinement", "List[IndexJobContract] (structural / enrichment)"]
  ];

  var DOCS_LIST = [
    {
      title: "Microservice Domain Architecture",
      path: "architecture/microservice_domain_architecture.md",
      spec: "Features 002, 005, 006",
      desc: "8 core hexagonal domains, 34 FastAPI routes, Temporal workflows, Google ADK agent pipeline, and fail-fast exception boundaries."
    },
    {
      title: "Universal Knowledge Discovery Graph (KDG)",
      path: "architecture/knowledge_discovery_graph_guide.md",
      spec: "Feature 005",
      desc: "6 KDG node types in Memgraph, 2-phase indexing, 9 regex classifiers, Rapidfuzz + DSU entity resolution, and zero-trust membership confinement."
    },
    {
      title: "Project Data Pipelines & Medallion Sandbox",
      path: "architecture/project_data_pipelines.md",
      spec: "Feature 004",
      desc: "BRONZE/SILVER/GOLD lakehouse partitioning, Python AST script validation, rootless network-isolated Docker runner, and S3 query confinement."
    },
    {
      title: "Data Ingestion Architecture & Operations",
      path: "architecture/data_ingestion_guide.md",
      spec: "Features 001, 004, 005",
      desc: "High-frequency MQTT telemetry buffering, atomic rotation, Snappy Parquet compaction, SpiderFoot OSINT imports, and project ingestion."
    },
    {
      title: "Autonomous AI RAG & 6-Tool Loop (artemis ask)",
      path: "architecture/ai_rag_scenario.md",
      spec: "Features 003, 005",
      desc: "Multi-turn Gemini Function Calling across DuckDB, Memgraph, and KDG with read-only SQL/Cypher guardrails, Redis cache, and audit trail."
    },
    {
      title: "Google AI Studio Integration & Fail-Fast Design",
      path: "architecture/google_ai_studio_integration.md",
      spec: "Features 001, 006",
      desc: "Why LLM inference is offloaded to gemini-2.5-flash-lite, fail-fast ConfigurationError/ServiceUnavailableError, and offline test doubles."
    },
    {
      title: "Clean Production Architecture & Testing Harness",
      path: "architecture/clean_architecture_and_testing.md",
      spec: "Feature 006",
      desc: "Zero production mocks in src/, typed exception hierarchy in src/core/exceptions.py, and 6 reusable test doubles in tests/fixtures/mocks/."
    },
    {
      title: "Foundational KDG Research & Ontology Brief",
      path: "architecture/ideas/knowledge_discovery_graph.md",
      spec: "Research Brief",
      desc: "Architectural comparison of static metadata catalogs vs. active semantic knowledge discovery graphs across arbitrary data types."
    }
  ];

  var selectedId = "dom_discovery";
  var activeLayerFilter = "ALL";

  function renderTopologyDiagram(selectedComp) {
    var svg = document.getElementById("topology-svg");
    if (!svg) return;
    svg.replaceChildren();

    var bg = svgEl("rect", { x: 0, y: 0, width: 860, height: 250, fill: "#050811" });
    svg.appendChild(bg);

    // Draw selected component in center and connected nodes on left/right
    var centerX = 430;
    var centerY = 125;

    var connectedIds = selectedComp.connectedTo || [];
    var connectedComps = COMPONENTS.filter(function (c) {
      return connectedIds.indexOf(c.id) !== -1 || (c.connectedTo && c.connectedTo.indexOf(selectedComp.id) !== -1);
    });

    // Deduplicate
    var uniqueConnected = [];
    var seen = {};
    connectedComps.forEach(function (c) {
      if (c.id !== selectedComp.id && !seen[c.id]) {
        seen[c.id] = true;
        uniqueConnected.push(c);
      }
    });

    var leftNodes = [];
    var rightNodes = [];
    uniqueConnected.forEach(function (c, idx) {
      if (idx % 2 === 0) {
        leftNodes.push(c);
      } else {
        rightNodes.push(c);
      }
    });

    function drawGroup(nodes, xPos) {
      var count = nodes.length;
      nodes.forEach(function (node, i) {
        var stepY = 220 / (count + 1);
        var yPos = 15 + stepY * (i + 1);

        var line = svgEl("line", {
          x1: xPos < centerX ? xPos + 95 : xPos - 95,
          y1: yPos,
          x2: xPos < centerX ? centerX - 110 : centerX + 110,
          y2: centerY,
          stroke: "#38bdf8",
          "stroke-width": "1.8",
          "stroke-dasharray": "5,4"
        });
        svg.appendChild(line);

        var g = svgEl("g", { cursor: "pointer" });
        var rect = svgEl("rect", {
          x: xPos - 95,
          y: yPos - 18,
          width: 190,
          height: 36,
          rx: 7,
          fill: "#131c31",
          stroke: "#334155",
          "stroke-width": "1.5"
        });
        var label = svgEl("text", {
          x: xPos,
          y: yPos + 4,
          fill: "#e2e8f0",
          "font-size": "11.5",
          "font-weight": "600",
          "text-anchor": "middle",
          "font-family": "Inter, sans-serif"
        });
        label.textContent = node.name;
        g.appendChild(rect);
        g.appendChild(label);
        g.addEventListener("click", function () {
          selectComponent(node.id);
        });
        svg.appendChild(g);
      });
    }

    drawGroup(leftNodes, 135);
    drawGroup(rightNodes, 725);

    // Center active node
    var centerRect = svgEl("rect", {
      x: centerX - 110,
      y: centerY - 34,
      width: 220,
      height: 68,
      rx: 10,
      fill: "#19243e",
      stroke: "#38bdf8",
      "stroke-width": "2.5"
    });
    var centerBadge = svgEl("text", {
      x: centerX,
      y: centerY - 10,
      fill: "#38bdf8",
      "font-size": "10",
      "font-weight": "700",
      "text-anchor": "middle",
      "font-family": "monospace"
    });
    centerBadge.textContent = selectedComp.badge + " (" + selectedComp.port + ")";

    var centerTitle = svgEl("text", {
      x: centerX,
      y: centerY + 12,
      fill: "#ffffff",
      "font-size": "13.5",
      "font-weight": "700",
      "text-anchor": "middle",
      "font-family": "Inter, sans-serif"
    });
    centerTitle.textContent = selectedComp.name;

    svg.appendChild(centerRect);
    svg.appendChild(centerBadge);
    svg.appendChild(centerTitle);
  }

  function renderInspector(comp) {
    var titleEl = document.getElementById("inspector-title");
    var badgeEl = document.getElementById("inspector-badge");
    var bodyEl = document.getElementById("inspector-body");
    if (!titleEl || !badgeEl || !bodyEl) return;

    titleEl.textContent = comp.name;
    badgeEl.textContent = comp.badge;
    badgeEl.className = "badge " + comp.badgeClass;
    bodyEl.replaceChildren();

    var summaryP = el("p", "inspector-text", comp.summary);
    bodyEl.appendChild(summaryP);

    var kvGrid = el("div", "kv-list");
    var pairs = [
      ["Runtime / Language", comp.language],
      ["Idle RAM Footprint", comp.ramMb + " MB"],
      ["Replaced Heavy Tool", comp.replacedTool],
      ["Port / Endpoint", comp.port]
    ];
    pairs.forEach(function (pair) {
      var item = el("div", "kv-item");
      item.appendChild(el("div", "kv-key", pair[0]));
      item.appendChild(el("div", "kv-val", pair[1]));
      kvGrid.appendChild(item);
    });
    bodyEl.appendChild(kvGrid);

    var cliSec = el("div", "inspector-section");
    cliSec.appendChild(el("div", "inspector-label", "Primary CLI / API Entrypoint"));
    cliSec.appendChild(el("div", "code-block", comp.cliOrApi));
    bodyEl.appendChild(cliSec);

    var filesSec = el("div", "inspector-section");
    filesSec.appendChild(el("div", "inspector-label", "Implementation Files in Repository"));
    var fileText = comp.files.join("\n");
    filesSec.appendChild(el("div", "code-block", fileText));
    bodyEl.appendChild(filesSec);

    var codeSec = el("div", "inspector-section");
    codeSec.appendChild(el("div", "inspector-label", "Implementation & Contract Snippet"));
    codeSec.appendChild(el("div", "code-block", comp.codeSnippet));
    bodyEl.appendChild(codeSec);
  }

  function renderLayers() {
    var container = document.getElementById("architecture-layers-container");
    if (!container) return;
    container.replaceChildren();

    var layerDefs = [
      { key: "ingress", title: "Layer 1: Edge Gateway, REST API & Operator CLI Ingress" },
      { key: "domains", title: "Layer 2: The 8 Core Hexagonal Domain Facades (src/domains/)" },
      { key: "orchestration", title: "Layer 3: Durable Orchestration, AI Reasoning & Clean Architecture" },
      { key: "infra", title: "Layer 4: Zero-JVM Native Persistence, Analytics & Cloud Offload" }
    ];

    layerDefs.forEach(function (ld) {
      if (activeLayerFilter !== "ALL" && activeLayerFilter !== ld.key) {
        return;
      }
      var layerBox = el("div", "arch-layer");
      layerBox.appendChild(el("div", "arch-layer-title", ld.title));

      var grid = el("div", "node-grid");
      COMPONENTS.filter(function (c) {
        return c.layer === ld.key;
      }).forEach(function (comp) {
        var btn = el("button", "arch-node" + (comp.id === selectedId ? " selected" : ""));
        btn.setAttribute("type", "button");
        var topRow = el("div", "arch-node-title");
        topRow.appendChild(el("span", "", comp.name));
        var b = el("span", "badge " + comp.badgeClass, comp.badge);
        topRow.appendChild(b);
        btn.appendChild(topRow);
        btn.appendChild(el("div", "arch-node-meta", comp.shortMeta));
        btn.addEventListener("click", function () {
          selectComponent(comp.id);
        });
        grid.appendChild(btn);
      });

      layerBox.appendChild(grid);
      container.appendChild(layerBox);
    });
  }

  function selectComponent(id) {
    selectedId = id;
    var found = COMPONENTS.find(function (c) {
      return c.id === id;
    }) || COMPONENTS[0];
    renderLayers();
    renderInspector(found);
    renderTopologyDiagram(found);
  }

  function renderRamSimulator() {
    var togglesWrap = document.getElementById("workload-toggles");
    var vmSelect = document.getElementById("vm-size-select");
    if (!togglesWrap || !vmSelect) return;

    togglesWrap.replaceChildren();
    WORKLOADS.forEach(function (w) {
      var btn = el("button", "btn" + (w.active ? " btn-primary" : ""), (w.active ? "[ON] " : "[OFF] ") + w.name);
      btn.setAttribute("type", "button");
      if (!w.locked) {
        btn.addEventListener("click", function () {
          w.active = !w.active;
          renderRamSimulator();
        });
      }
      togglesWrap.appendChild(btn);
    });

    var vmCapacityMb = parseInt(vmSelect.value, 10) || 32768;
    var artemisTotal = 0;
    var jvmTotal = 0;
    WORKLOADS.forEach(function (w) {
      if (w.active) {
        artemisTotal += w.artemisMb;
        jvmTotal += w.jvmMb;
      }
    });

    var artemisPct = Math.min(100, Math.round((artemisTotal / vmCapacityMb) * 100));
    var jvmPct = Math.min(100, Math.round((jvmTotal / vmCapacityMb) * 100));

    var artemisBar = document.getElementById("artemis-ram-bar");
    var jvmBar = document.getElementById("jvm-ram-bar");
    var artemisSum = document.getElementById("artemis-ram-summary");
    var jvmSum = document.getElementById("jvm-ram-summary");

    if (artemisBar) {
      artemisBar.style.width = artemisPct + "%";
      artemisBar.style.backgroundColor = artemisTotal <= 12288 ? "#10b981" : "#f59e0b";
    }
    if (jvmBar) {
      jvmBar.style.width = jvmPct + "%";
      jvmBar.style.backgroundColor = jvmTotal > vmCapacityMb ? "#f43f5e" : "#f59e0b";
    }

    if (artemisSum) {
      artemisSum.textContent = "Artemis Active Memory: " + (artemisTotal / 1024).toFixed(2) + " GB / " + (vmCapacityMb / 1024).toFixed(0) + " GB (" + artemisPct + "% used — Healthy Sovereign Headroom)";
    }
    if (jvmSum) {
      var statusText = jvmTotal > vmCapacityMb ? "CRITICAL: EXCEEDS HOST VM CAPACITY (OOM KILLER TRIGGERED)" : "HIGH MEMORY PRESSURE";
      jvmSum.textContent = "Traditional JVM Stack: " + (jvmTotal / 1024).toFixed(2) + " GB / " + (vmCapacityMb / 1024).toFixed(0) + " GB (" + statusText + ")";
    }

    var tbody = document.getElementById("ram-table-body");
    if (tbody && tbody.childNodes.length === 0) {
      RAM_TABLE_ROWS.forEach(function (row) {
        var tr = el("tr");
        row.forEach(function (cell, idx) {
          var td = el("td", "", cell);
          if (idx === 2) td.style.color = "#10b981";
          if (idx === 4) td.style.color = "#f43f5e";
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }
  }

  function renderApiCatalog() {
    var tbody = document.getElementById("api-catalog-body");
    var searchInput = document.getElementById("api-search-input");
    var domainFilter = document.getElementById("api-domain-filter");
    if (!tbody) return;

    var q = searchInput ? searchInput.value.trim().toLowerCase() : "";
    var dom = domainFilter ? domainFilter.value : "ALL";

    tbody.replaceChildren();
    API_CATALOG.filter(function (row) {
      var matchesDom = dom === "ALL" || row[0] === dom;
      var matchesQ = !q || row.join(" ").toLowerCase().indexOf(q) !== -1;
      return matchesDom && matchesQ;
    }).forEach(function (row) {
      var tr = el("tr");
      var tdDom = el("td");
      tdDom.appendChild(el("span", "badge badge-purple", row[0]));
      tr.appendChild(tdDom);

      var tdPath = el("td", "arch-node-meta", row[1]);
      tr.appendChild(tdPath);

      var tdCli = el("td", "arch-node-meta", row[2]);
      tr.appendChild(tdCli);

      var tdAuth = el("td", "", row[3]);
      tr.appendChild(tdAuth);

      var tdDesc = el("td", "", row[4]);
      tr.appendChild(tdDesc);

      tbody.appendChild(tr);
    });
  }

  function renderMarkdownDocs() {
    var grid = document.getElementById("markdown-docs-grid");
    if (!grid) return;
    grid.replaceChildren();

    DOCS_LIST.forEach(function (doc) {
      var card = el("a", "arch-node");
      card.setAttribute("href", doc.path);
      card.style.textDecoration = "none";

      var top = el("div", "arch-node-title");
      top.appendChild(el("span", "", doc.title));
      top.appendChild(el("span", "badge badge-blue", doc.spec));
      card.appendChild(top);

      card.appendChild(el("div", "arch-node-meta", "docs/" + doc.path));
      card.appendChild(el("p", "step-desc", doc.desc));
      grid.appendChild(card);
    });
  }

  function initTabs() {
    var tabButtons = document.querySelectorAll(".tab-btn");
    var panels = document.querySelectorAll(".tab-panel");

    tabButtons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var targetId = btn.getAttribute("data-tab");
        tabButtons.forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        panels.forEach(function (p) {
          if (p.id === targetId) {
            p.removeAttribute("hidden");
          } else {
            p.setAttribute("hidden", "hidden");
          }
        });
      });
    });

    var docsHubLink = document.getElementById("docs-hub-link");
    if (docsHubLink) {
      docsHubLink.addEventListener("click", function (e) {
        e.preventDefault();
        var docsBtn = document.querySelector('[data-tab="tab-docs"]');
        if (docsBtn) docsBtn.click();
      });
    }
  }

  function initFilters() {
    var btnAll = document.getElementById("filter-all");
    var btnDomains = document.getElementById("filter-domains");
    var btnInfra = document.getElementById("filter-infra");

    if (btnAll) {
      btnAll.addEventListener("click", function () {
        activeLayerFilter = "ALL";
        renderLayers();
      });
    }
    if (btnDomains) {
      btnDomains.addEventListener("click", function () {
        activeLayerFilter = "domains";
        renderLayers();
      });
    }
    if (btnInfra) {
      btnInfra.addEventListener("click", function () {
        activeLayerFilter = "infra";
        renderLayers();
      });
    }

    var vmSelect = document.getElementById("vm-size-select");
    if (vmSelect) {
      vmSelect.addEventListener("change", renderRamSimulator);
    }

    var searchInput = document.getElementById("api-search-input");
    var domainFilter = document.getElementById("api-domain-filter");
    if (searchInput) searchInput.addEventListener("input", renderApiCatalog);
    if (domainFilter) domainFilter.addEventListener("change", renderApiCatalog);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTabs();
    initFilters();
    selectComponent(selectedId);
    renderRamSimulator();
    renderApiCatalog();
    renderMarkdownDocs();
  });
})();
