(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
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

  var SCENARIOS = [
    {
      id: "flow_telemetry",
      title: "1. MQTT Telemetry & Parquet Compaction",
      badge: "FEATURE 001",
      actors: ["Simulator / Sensor", "Mosquitto :1883", "Disk Buffer", "FlushWorkflow", "MinIO S3 Parquet", "Postgres Audit"],
      steps: [
        {
          title: "Step 1: High-Frequency MQTT Publish (1,000 evt/s)",
          fromIdx: 0,
          toIdx: 1,
          latency: "0.4 ms/evt",
          file: "tools/simulate_telemetry.py",
          desc: "Edge sensors or tools/simulate_telemetry.py publish JSON telemetry payloads to topic telemetry/<site>/<device_id>/<metric> on Eclipse Mosquitto (:1883).",
          payload: "Topic: telemetry/site_a/sensor_042/cpu_temp\nPayload:\n{\n  \"timestamp\": \"2026-10-22T10:30:00Z\",\n  \"device_id\": \"sensor_042\",\n  \"metric_name\": \"cpu_temp\",\n  \"value\": 78.4,\n  \"unit\": \"celsius\",\n  \"metadata\": {\"firmware\": \"v2.4.1\"}\n}"
        },
        {
          title: "Step 2: Pydantic Validation & POSIX O_APPEND Buffer Write",
          fromIdx: 1,
          toIdx: 2,
          latency: "0.2 ms",
          file: "src/services/ingestion/mqtt_listener.py",
          desc: "MqttIngestionListener._on_message validates the payload via TelemetryEvent (Pydantic v2) and atomically appends a UTF-8 JSON line to /tmp/artemis/buffer/events.jsonl.",
          payload: "# Appended to /tmp/artemis/buffer/events.jsonl\n{\"event_id\":\"9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d\",\"timestamp\":\"2026-10-22T10:30:00Z\",\"device_id\":\"sensor_042\",\"metric_name\":\"cpu_temp\",\"value\":78.4,\"unit\":\"celsius\",\"metadata\":{\"firmware\":\"v2.4.1\"}}"
        },
        {
          title: "Step 3: Crash Recovery & Zero-Downtime Atomic Rotation",
          fromIdx: 3,
          toIdx: 2,
          latency: "0.1 ms",
          file: "src/pipelines/mqtt_to_minio.py | src/domains/ingestion/operations/flush.py",
          desc: "FlushBufferWorkflow first recovers any interrupted events.processing.*.jsonl files, then atomically renames events.jsonl -> events.processing.<ts>.jsonl so incoming MQTT writes never block.",
          payload: "os.rename(\n  '/tmp/artemis/buffer/events.jsonl',\n  '/tmp/artemis/buffer/events.processing.1792665000123.jsonl'\n)\n# Malformed lines are counted and skipped without aborting batch"
        },
        {
          title: "Step 4: In-Memory PyArrow Snappy Parquet Compaction",
          fromIdx: 3,
          toIdx: 4,
          latency: "42 ms (10k rows)",
          file: "src/services/ingestion/minio_writer.py",
          desc: "MinioParquetWriter converts the validated TelemetryEvent batch into an Apache Arrow Table and streams Snappy-compressed Parquet bytes directly into MinIO S3.",
          payload: "S3 Bucket: telemetry\nS3 Object Key: year=2026/month=10/day=22/batch_1792665000_a8f91c2b.parquet\nCompression: SNAPPY\nRows Written: 10,000"
        },
        {
          title: "Step 5: Buffer Cleanup & PostgreSQL Run Audit",
          fromIdx: 3,
          toIdx: 5,
          latency: "3.1 ms",
          file: "src/pipelines/mqtt_to_minio.py",
          desc: "After MinIO confirms the PUT object upload, the temporary processing file is unlinked and a SUCCESS record is inserted into PostgreSQL pipeline_runs.",
          payload: "INSERT INTO pipeline_runs (pipeline_name, status, events_processed, details)\nVALUES (\n  'mqtt_to_minio',\n  'SUCCESS',\n  10000,\n  '{\"object_key\": \"year=2026/month=10/day=22/batch_1792665000_a8f91c2b.parquet\"}'\n);"
        }
      ]
    },
    {
      id: "flow_ai_ask",
      title: "2. 6-Tool Autonomous AI Agent Loop (artemis ask)",
      badge: "FEATURES 003 & 005",
      actors: ["Analyst CLI/API", "AIFacade & Redis", "ADK Planner/Critic", "DynamicAgentLoop", "6 Read-Only Tools", "Gemini 2.5 Flash"],
      steps: [
        {
          title: "Step 1: Rate Limiting (60 req/m) & SHA-256 Semantic Cache",
          fromIdx: 0,
          toIdx: 1,
          latency: "1.2 ms",
          file: "src/domains/ai/facade/ai.py | src/services/ai/cache.py",
          desc: "Analyst runs artemis ask. QueryCache verifies the sliding-window rate limit in Redis (artemis:ratelimit:analyst) and checks artemis:ai:query:<sha256> for a cached response.",
          payload: "$ artemis ask \"Which projects reference account ACCT-99812 and what CPU spikes occurred?\"\n\nRedis Lookup: GET artemis:ai:query:4e9c8b... -> MISS\nRate Limit Counter: 4 / 60 req/min"
        },
        {
          title: "Step 2: ADK PlannerAgent & GuardianCriticAgent Validation",
          fromIdx: 1,
          toIdx: 2,
          latency: "0.8 ms",
          file: "src/domains/ai/operations/ai_agents.py",
          desc: "PlannerAgent decomposes the inquiry into multi-database steps; GuardianCriticAgent verifies that the request does not attempt destructive mutations or unauthorized system access.",
          payload: "Planner Output: [\"1. Correlate entity ACCT-99812 via KDG\", \"2. Query DuckDB telemetry for CPU spikes\"]\nGuardianCritic Verdict: APPROVED (Read-Only Bounds Verified)"
        },
        {
          title: "Step 3: Turn 1 — Gemini Function Call: find_cross_project_entities",
          fromIdx: 3,
          toIdx: 5,
          latency: "420 ms",
          file: "src/domains/ai/operations/dynamic_loop.py",
          desc: "DynamicAgentLoop invokes gemini-2.5-flash-lite with 6 declared tool schemas. Gemini decides to call find_cross_project_entities(value='ACCT-99812').",
          payload: "Gemini Function Call:\n{\n  \"name\": \"find_cross_project_entities\",\n  \"args\": {\n    \"value\": \"ACCT-99812\",\n    \"fuzzy\": true\n  }\n}"
        },
        {
          title: "Step 4: KDG Tool Execution (Zero-Trust Member Scoped)",
          fromIdx: 3,
          toIdx: 4,
          latency: "11 ms",
          file: "src/domains/ai/operations/tools.py | src/domains/discovery/facade/discovery.py",
          desc: "AgentTools executes find_cross_project_entities scoped strictly to the caller's member_projects in Memgraph. Non-member projects leave 0% trace.",
          payload: "Tool Result (databases_consulted += 'memgraph'):\n{\n  \"total_projects\": 2,\n  \"matches\": [\n    {\"project_id\": \"proj-alpha\", \"resource_id\": \"accounts\", \"tier\": \"BRONZE\", \"attribute\": \"acct_id\", \"value\": \"ACCT-99812\", \"confidence\": 1.0},\n    {\"project_id\": \"proj-beta\", \"resource_id\": \"transfers\", \"tier\": \"SILVER\", \"attribute\": \"client_account\", \"value\": \"ACCT-99812\", \"confidence\": 1.0}\n  ]\n}"
        },
        {
          title: "Step 5: Turn 2 — Gemini Function Call: query_analytics (DuckDB SQL)",
          fromIdx: 3,
          toIdx: 4,
          latency: "14 ms",
          file: "src/domains/ai/operations/guardrails.py | src/services/analytics/duckdb_client.py",
          desc: "Gemini requests query_analytics. validate_read_only_sql() verifies zero mutating keywords before DuckDB queries MinIO Parquet files.",
          payload: "Validated Read-Only SQL:\nSELECT device_id, MAX(value) AS peak_cpu\nFROM read_parquet('s3://telemetry/**/*.parquet')\nWHERE metric_name = 'cpu_load'\nGROUP BY device_id ORDER BY peak_cpu DESC LIMIT 3;\n\nResult: [{\"device_id\": \"srv-alpha-01\", \"peak_cpu\": 98.7}]"
        },
        {
          title: "Step 6: Final Grounded Synthesis, Redis Cache & Postgres Audit",
          fromIdx: 5,
          toIdx: 0,
          latency: "510 ms",
          file: "src/domains/ai/operations/dynamic_loop.py | src/services/ai/audit_logger.py",
          desc: "Gemini synthesizes the final response grounded strictly on retrieved Memgraph KDG and DuckDB records. Response is cached in Redis (TTL 3600s) and logged in PostgreSQL ai_queries.",
          payload: "{\n  \"query_id\": \"qry-8f31a9c2\",\n  \"model_used\": \"gemini-2.5-flash-lite\",\n  \"databases_consulted\": [\"duckdb\", \"memgraph\"],\n  \"tool_calls\": [\n    {\"tool_name\": \"find_cross_project_entities\", \"duration_ms\": 11},\n    {\"tool_name\": \"query_analytics\", \"duration_ms\": 14}\n  ],\n  \"response\": \"Account ACCT-99812 appears in proj-alpha (accounts) and proj-beta (transfers). Peak CPU load of 98.7% was recorded on srv-alpha-01.\"\n}"
        }
      ]
    },
    {
      id: "flow_medallion",
      title: "3. Medallion Pipeline & Ephemeral Docker Sandbox",
      badge: "FEATURE 004",
      actors: ["Analyst CLI/API", "PipelineFacade", "ScriptValidator (AST)", "MinIO Lakehouse", "Docker Sandbox", "Memgraph Lineage"],
      steps: [
        {
          title: "Step 1: Upload Python Script & AST Syntax Validation",
          fromIdx: 0,
          toIdx: 2,
          latency: "1.5 ms",
          file: "src/domains/pipeline/operations/script_validator.py",
          desc: "Analyst registers a transformation pipeline (BRONZE_TO_SILVER). ScriptValidator parses the script with Python's native ast.parse() to reject syntax errors before storing version 1 in PostgreSQL.",
          payload: "$ artemis project pipeline create --project alpha-ops --name clean_cpu --stage BRONZE_TO_SILVER --script ./clean.py\n\nAST Validation: PASSED (0 syntax errors)\nRegistered Pipeline ID: pipe-7c92e1 (Version: 1)"
        },
        {
          title: "Step 2: Stage Source Bronze Datasets from MinIO to Host Temp",
          fromIdx: 1,
          toIdx: 3,
          latency: "18 ms",
          file: "src/domains/pipeline/operations/pipeline_executor.py",
          desc: "When pipeline run is triggered, PipelineExecutor downloads the requested input datasets from s3://telemetry/projects/alpha-ops/bronze/raw_metrics/ into an isolated host staging directory.",
          payload: "Staged Input Files:\n/tmp/artemis_run_991a/input/raw_metrics.parquet (Read-Only mount -> /workspace/input)\n/tmp/artemis_run_991a/output/ (Read-Write mount -> /workspace/output)"
        },
        {
          title: "Step 3: Execute in Hardened Rootless Docker Sandbox",
          fromIdx: 1,
          toIdx: 4,
          latency: "640 ms",
          file: "src/domains/pipeline/operations/docker_runner.py",
          desc: "DockerPipelineRunner launches artemis-pipeline-runner:latest with network_mode='none' (zero egress), mem_limit='2g', nano_cpus=2e9 (2 CPUs), non-root user 'artemis' (UID 10001), and 300s timeout.",
          payload: "Container Config:\n  image: \"artemis-pipeline-runner:latest\"\n  user: \"artemis\" (UID 10001)\n  network_mode: \"none\"\n  mem_limit: \"2g\"\n  nano_cpus: 2000000000\nExit Code: 0 (Container destroyed immediately in finally block)"
        },
        {
          title: "Step 4: Commit Transformed Silver Parquet to MinIO",
          fromIdx: 4,
          toIdx: 3,
          latency: "24 ms",
          file: "src/domains/pipeline/operations/pipeline_executor.py",
          desc: "Output Parquet artifacts produced in /workspace/output/ are uploaded to the target Medallion tier (s3://telemetry/projects/alpha-ops/silver/clean_anomalies/) and cataloged in project_datasets.",
          payload: "Committed S3 URI:\ns3://telemetry/projects/alpha-ops/silver/clean_anomalies/year=2026/month=10/day=22/part_01.parquet\nRecords Processed: 4,820"
        },
        {
          title: "Step 5: Record Provenance Lineage & Index in KDG",
          fromIdx: 1,
          toIdx: 5,
          latency: "9 ms",
          file: "src/domains/discovery/operations/lineage.py",
          desc: "LineageService records the PipelineExecution node and links clean_anomalies -[DERIVED_FROM]-> raw_metrics in Memgraph so analysts can trace full data provenance.",
          payload: "Cypher Lineage Upsert:\n(clean_anomalies:DataResource {tier:'SILVER'})-[:DERIVED_FROM]->(raw_metrics:DataResource {tier:'BRONZE'})\n(run:PipelineExecution {status:'SUCCESS'})-[:CONSUMED]->(raw_metrics)\n(run)-[:PRODUCED]->(clean_anomalies)"
        }
      ]
    },
    {
      id: "flow_kdg",
      title: "4. Two-Phase KDG Indexing & Entity Resolution",
      badge: "FEATURE 005",
      actors: ["ScopedIngestion", "StructuralIndexer", "PatternProfiler", "Memgraph KDG Store", "EnrichmentService", "EntityResolution (DSU)"],
      steps: [
        {
          title: "Step 1: Project Dataset Ingestion Trigger",
          fromIdx: 0,
          toIdx: 1,
          latency: "2 ms",
          file: "src/domains/project/operations/scoped_ingestion.py",
          desc: "When tabular (CSV/JSON/Parquet) or text data is ingested into a project, ScopedIngestionService writes the Parquet object to MinIO and invokes Phase 1 StructuralIndexer synchronously.",
          payload: "$ artemis project ingest --project proj-alpha --dataset accounts --tier bronze --file accounts.csv\n\nIngested 500 records -> Triggering Phase 1 StructuralIndexer"
        },
        {
          title: "Step 2: Phase 1 Schema Introspection & 9-Regex Pattern Profiling",
          fromIdx: 1,
          toIdx: 2,
          latency: "19 ms",
          file: "src/domains/discovery/operations/structural_indexer.py | pattern_profiler.py",
          desc: "StructuralIndexer inspects physical column types, cardinality, and null ratios. PatternProfiler classifies values against 9 regex patterns (UUID, EMAIL, IP_ADDRESS, HASH, ISO_TIMESTAMP, PHONE, URL, COORDINATES, IDENTIFIER).",
          payload: "Column Profile for 'accounts':\n- acct_id (VARCHAR) -> Inferred: IDENTIFIER (cardinality=500, nulls=0)\n- contact_email (VARCHAR) -> Inferred: EMAIL (confidence=1.0)\n- last_login_ip (VARCHAR) -> Inferred: IP_ADDRESS (confidence=1.0)"
        },
        {
          title: "Step 3: Upsert KDG Graph Ontology Nodes in Memgraph",
          fromIdx: 1,
          toIdx: 3,
          latency: "14 ms",
          file: "src/domains/discovery/operations/kdg_graph_store.py",
          desc: "KDGGraphStore upserts Workspace, DataResource, DataAttribute, and GenericEntity nodes into Memgraph, all tagged with project_id='proj-alpha'.",
          payload: "Upserted KDG Nodes:\n(:Workspace {project_id: 'proj-alpha'})\n  -[:OWNS]->(:DataResource {resource_id: 'accounts', tier: 'BRONZE'})\n  -[:HAS_ATTRIBUTE]->(:DataAttribute {name: 'acct_id', inferred_type: 'IDENTIFIER'})\n  -[:CONTAINS_ENTITY]->(:GenericEntity {value: 'ACCT-99812', entity_type: 'Identifier'})"
        },
        {
          title: "Step 4: Phase 2 Semantic Taxonomy Mapping & Unstructured NER",
          fromIdx: 4,
          toIdx: 3,
          latency: "35 ms (Async)",
          file: "src/domains/discovery/operations/enrichment.py",
          desc: "EnrichmentService maps synonymous column names (e.g. acct_id, client_account) to shared SemanticTaxonomy nodes (:SemanticTaxonomy {name: 'AccountIdentifier'}) via MAPS_TO edges.",
          payload: "Semantic Taxonomy Link:\n(:DataAttribute {name: 'acct_id', project_id: 'proj-alpha'})\n  -[:MAPS_TO]->(:SemanticTaxonomy {concept_id: 'tax_account_id', name: 'AccountIdentifier'})\n<-[:MAPS_TO]-(:DataAttribute {name: 'client_account', project_id: 'proj-beta'})"
        },
        {
          title: "Step 5: Cross-Project Entity Resolution (Rapidfuzz + DSU Clustering)",
          fromIdx: 5,
          toIdx: 3,
          latency: "28 ms",
          file: "src/domains/discovery/operations/entity_resolution.py",
          desc: "EntityResolutionService compares GenericEntity nodes across workspaces using exact normalization and rapidfuzz.fuzz.token_sort_ratio (>= 88%), grouping equivalents via Disjoint-Set Union (DSU) and creating SAME_AS edges.",
          payload: "Entity Resolution Cluster:\n(:GenericEntity {project_id: 'proj-alpha', value: 'ACCT-99812'})\n  <-[:SAME_AS {confidence: 1.0, method: 'exact'}]->\n(:GenericEntity {project_id: 'proj-beta', value: 'ACCT-99812'})"
        }
      ]
    },
    {
      id: "flow_clean_arch",
      title: "5. Fail-Fast Production vs. Pytest Mock Harness",
      badge: "FEATURE 006",
      actors: ["Caller / Test", "Domain Service (src/)", "src/core/exceptions.py", "Live Daemon / API", "tests/conftest.py", "tests/fixtures/mocks/"],
      steps: [
        {
          title: "Step 1: Clean Constructor Initialization (Zero mock_mode Flags)",
          fromIdx: 0,
          toIdx: 1,
          latency: "0.1 ms",
          file: "src/domains/ai/operations/dynamic_loop.py | tests/unit/test_clean_architecture.py",
          desc: "Every production class in src/ accepts clean dependency-injected clients (e.g. client, memgraph_client, graph_store) with zero mock_mode flags or embedded fake dictionaries.",
          payload: "# Verified by tests/unit/test_clean_architecture.py\nDynamicAgentLoop(api_key=..., model=..., tools=..., client=...)\n# Zero '_run_simulated_loop' or 'mock_mode' anywhere in src/"
        },
        {
          title: "Step 2: Production Missing Credential -> Fail-Fast ConfigurationError",
          fromIdx: 1,
          toIdx: 2,
          latency: "0.1 ms (Fail-Fast)",
          file: "src/core/exceptions.py | src/services/ai/genai_service.py",
          desc: "In production, if GOOGLE_AI_STUDIO_API_KEY is unset or left as the placeholder string, initialization immediately raises ConfigurationError instead of silently faking responses.",
          payload: "raise ConfigurationError(\n    \"Google AI Studio API key is missing or set to placeholder value.\",\n    key=\"google_api_key\"\n)"
        },
        {
          title: "Step 3: Production Daemon Down -> Sub-Second TCP ConnectionError",
          fromIdx: 1,
          toIdx: 3,
          latency: "0.5 ms (Fail-Fast)",
          file: "src/services/graph/memgraph_client.py | src/domains/discovery/operations/kdg_graph_store.py",
          desc: "Before executing Bolt or SQL operations, MemgraphClient and KDGGraphStore perform a fast TCP socket check. If Memgraph (:7687) is down, ConnectionError is raised immediately.",
          payload: "raise ConnectionError(\n    \"Cannot connect to Memgraph at localhost:7687\",\n    host=\"localhost\",\n    port=7687\n)"
        },
        {
          title: "Step 4: Offline Test Execution -> Pytest Fixture Injection",
          fromIdx: 4,
          toIdx: 5,
          latency: "0.2 ms",
          file: "tests/conftest.py | tests/fixtures/mocks/",
          desc: "During automated pytest runs (make test), tests/conftest.py injects reusable test doubles from tests/fixtures/mocks/ into production constructors.",
          payload: "# tests/fixtures/mocks/\n- MockGenAIClient (simulates 6-tool Gemini Function Calling)\n- MockMemgraphClient (in-memory property graph)\n- MockKDGGraphStore (in-memory KDG ontology & lineage)\n- MockDockerRunner (local tmpdir sandbox runner)\n- MockQueryCache & MockAuditLogger"
        },
        {
          title: "Step 5: 100% Deterministic Offline Verification (162/162 Passing)",
          fromIdx: 5,
          toIdx: 0,
          latency: "4.2 s total suite",
          file: "tests/unit/test_mock_fixtures.py",
          desc: "All 162 contract, unit, and integration tests pass 100% offline with complete behavioral parity while keeping src/ completely free of test code.",
          payload: "$ make test\n======================== 162 passed in 4.21s ========================\n- 0 mock branches in src/\n- 100% fail-fast exception coverage"
        }
      ]
    }
  ];

  var currentScenarioIdx = 0;
  var currentStepIdx = 0;
  var playTimer = null;

  function stopAutoPlay() {
    if (playTimer !== null) {
      window.clearInterval(playTimer);
      playTimer = null;
    }
    var playBtn = document.getElementById("btn-play-pause");
    if (playBtn) {
      playBtn.textContent = "\u25B6 Auto-Play Flow";
    }
  }

  function toggleAutoPlay() {
    if (playTimer !== null) {
      stopAutoPlay();
      return;
    }
    var playBtn = document.getElementById("btn-play-pause");
    if (playBtn) {
      playBtn.textContent = "\u23F8 Pause Flow";
    }
    playTimer = window.setInterval(function () {
      var scen = SCENARIOS[currentScenarioIdx];
      if (currentStepIdx < scen.steps.length - 1) {
        currentStepIdx += 1;
        renderCurrentScenario();
      } else {
        stopAutoPlay();
      }
    }, 2400);
  }

  function renderScenarioTabs() {
    var bar = document.getElementById("scenario-tab-bar");
    if (!bar) return;
    bar.replaceChildren();

    SCENARIOS.forEach(function (scen, idx) {
      var btn = el("button", "tab-btn" + (idx === currentScenarioIdx ? " active" : ""), scen.title);
      btn.setAttribute("type", "button");
      btn.addEventListener("click", function () {
        stopAutoPlay();
        currentScenarioIdx = idx;
        currentStepIdx = 0;
        renderScenarioTabs();
        renderCurrentScenario();
      });
      bar.appendChild(btn);
    });
  }

  function renderSequenceSvg(scen, activeStepIdx) {
    var svg = document.getElementById("flow-sequence-svg");
    if (!svg) return;
    svg.replaceChildren();

    svg.appendChild(svgEl("rect", { x: 0, y: 0, width: 880, height: 310, fill: "#050811" }));

    var actors = scen.actors;
    var count = actors.length;
    var marginX = 75;
    var usableW = 880 - marginX * 2;
    var stepX = count > 1 ? usableW / (count - 1) : 0;

    // Draw lifelines and actor headers
    actors.forEach(function (actorName, i) {
      var x = marginX + stepX * i;
      var activeStep = scen.steps[activeStepIdx];
      var isInvolved = activeStep && (activeStep.fromIdx === i || activeStep.toIdx === i);

      var line = svgEl("line", {
        x1: x,
        y1: 52,
        x2: x,
        y2: 295,
        stroke: isInvolved ? "#38bdf8" : "#1e293b",
        "stroke-width": isInvolved ? "2" : "1.5",
        "stroke-dasharray": "4,4"
      });
      svg.appendChild(line);

      var box = svgEl("rect", {
        x: x - 64,
        y: 14,
        width: 128,
        height: 36,
        rx: 6,
        fill: isInvolved ? "#19243e" : "#131c31",
        stroke: isInvolved ? "#38bdf8" : "#334155",
        "stroke-width": isInvolved ? "2" : "1.2"
      });
      svg.appendChild(box);

      var txt = svgEl("text", {
        x: x,
        y: 36,
        fill: isInvolved ? "#ffffff" : "#94a3b8",
        "font-size": "10.5",
        "font-weight": "700",
        "text-anchor": "middle",
        "font-family": "Inter, sans-serif"
      });
      txt.textContent = actorName;
      svg.appendChild(txt);
    });

    // Draw steps arrows
    var totalSteps = scen.steps.length;
    var startY = 82;
    var gapY = Math.min(38, 200 / Math.max(1, totalSteps));

    scen.steps.forEach(function (st, idx) {
      var y = startY + idx * gapY;
      var x1 = marginX + stepX * st.fromIdx;
      var x2 = marginX + stepX * st.toIdx;
      var isCurrent = idx === activeStepIdx;
      var isPast = idx < activeStepIdx;

      var strokeColor = isCurrent ? "#38bdf8" : isPast ? "#10b981" : "#334155";
      var strokeW = isCurrent ? "2.8" : "1.6";

      var msgLine = svgEl("line", {
        x1: x1,
        y1: y,
        x2: x2,
        y2: y,
        stroke: strokeColor,
        "stroke-width": strokeW
      });
      svg.appendChild(msgLine);

      // Arrowhead
      var dir = x2 >= x1 ? 1 : -1;
      var arrowPts = (x2 - dir * 8) + "," + (y - 4.5) + " " + x2 + "," + y + " " + (x2 - dir * 8) + "," + (y + 4.5);
      var arrow = svgEl("polygon", {
        points: arrowPts,
        fill: strokeColor
      });
      svg.appendChild(arrow);

      // Packet pulse circle on active step
      if (isCurrent) {
        var midX = (x1 + x2) / 2;
        var pulse = svgEl("circle", {
          cx: midX,
          cy: y,
          r: 6,
          fill: "#38bdf8",
          stroke: "#ffffff",
          "stroke-width": "1.5"
        });
        svg.appendChild(pulse);
      }

      var labelX = (x1 + x2) / 2;
      var label = svgEl("text", {
        x: labelX,
        y: y - 7,
        fill: isCurrent ? "#ffffff" : isPast ? "#a7f3d0" : "#64748b",
        "font-size": isCurrent ? "11" : "10",
        "font-weight": isCurrent ? "700" : "500",
        "text-anchor": "middle",
        "font-family": "Inter, sans-serif"
      });
      label.textContent = st.title;
      svg.appendChild(label);
    });
  }

  function renderCurrentScenario() {
    var scen = SCENARIOS[currentScenarioIdx];
    var step = scen.steps[currentStepIdx];

    var stageTitle = document.getElementById("flow-stage-title");
    var stepCounter = document.getElementById("flow-step-counter");
    if (stageTitle) stageTitle.textContent = scen.title;
    if (stepCounter) stepCounter.textContent = "Step " + (currentStepIdx + 1) + " / " + scen.steps.length;

    renderSequenceSvg(scen, currentStepIdx);

    var listEl = document.getElementById("flow-steps-list");
    if (listEl) {
      listEl.replaceChildren();
      scen.steps.forEach(function (st, idx) {
        var cls = "step-card";
        if (idx === currentStepIdx) cls += " active";
        else if (idx < currentStepIdx) cls += " completed";

        var card = el("div", cls);
        var hdr = el("div", "step-header");
        hdr.appendChild(el("div", "step-title", st.title));
        var actorSpan = el("span", "step-actors", scen.actors[st.fromIdx] + " \u2192 " + scen.actors[st.toIdx] + " (" + st.latency + ")");
        hdr.appendChild(actorSpan);
        card.appendChild(hdr);
        card.appendChild(el("div", "step-desc", st.desc));

        card.addEventListener("click", function () {
          stopAutoPlay();
          currentStepIdx = idx;
          renderCurrentScenario();
        });
        listEl.appendChild(card);
      });
    }

    var detailTitle = document.getElementById("step-detail-title");
    var detailBadge = document.getElementById("step-detail-badge");
    var detailBody = document.getElementById("step-detail-body");
    if (detailTitle && detailBadge && detailBody && step) {
      detailTitle.textContent = step.title;
      detailBadge.textContent = step.latency;
      detailBody.replaceChildren();

      detailBody.appendChild(el("p", "inspector-text", step.desc));

      var kv = el("div", "kv-list");
      var item1 = el("div", "kv-item");
      item1.appendChild(el("div", "kv-key", "Source Actor"));
      item1.appendChild(el("div", "kv-val", scen.actors[step.fromIdx]));
      kv.appendChild(item1);

      var item2 = el("div", "kv-item");
      item2.appendChild(el("div", "kv-key", "Target Actor"));
      item2.appendChild(el("div", "kv-val", scen.actors[step.toIdx]));
      kv.appendChild(item2);
      detailBody.appendChild(kv);

      var fileSec = el("div", "inspector-section");
      fileSec.appendChild(el("div", "inspector-label", "Executing Code Module"));
      fileSec.appendChild(el("div", "code-block", step.file));
      detailBody.appendChild(fileSec);

      var paySec = el("div", "inspector-section");
      paySec.appendChild(el("div", "inspector-label", "Live Wire Payload / Query / Contract State"));
      paySec.appendChild(el("div", "code-block", step.payload));
      detailBody.appendChild(paySec);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderScenarioTabs();
    renderCurrentScenario();

    var prevBtn = document.getElementById("btn-prev-step");
    var nextBtn = document.getElementById("btn-next-step");
    var playBtn = document.getElementById("btn-play-pause");
    var resetBtn = document.getElementById("btn-reset-flow");

    if (prevBtn) {
      prevBtn.addEventListener("click", function () {
        stopAutoPlay();
        if (currentStepIdx > 0) {
          currentStepIdx -= 1;
          renderCurrentScenario();
        }
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", function () {
        stopAutoPlay();
        var scen = SCENARIOS[currentScenarioIdx];
        if (currentStepIdx < scen.steps.length - 1) {
          currentStepIdx += 1;
          renderCurrentScenario();
        }
      });
    }
    if (playBtn) {
      playBtn.addEventListener("click", toggleAutoPlay);
    }
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        stopAutoPlay();
        currentStepIdx = 0;
        renderCurrentScenario();
      });
    }
  });
})();
