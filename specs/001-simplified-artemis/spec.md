# Feature Specification: Simplified Artemis

**Feature Branch**: `[001-simplified-artemis]`

**Created**: 2026-08-27

**Status**: Draft

**Input**: User description: "based on LTV cone knowledge, I want you to design and implement Simplified Artemis goal, that can be run on a VM. Take the technology_stack.md into consideration. The use case for this system is Big Data Platform that can process and analyze data with usage of AI."

## Clarifications

### Session 2026-08-28
- Q: How should the system recover from a sudden VM reboot or hardware failure? → A: Automatic restart with acceptable loss of in-flight/recent events (simplifies single-node architecture and favors performance over strict ACID guarantees for telemetry)
- Q: Which standard or system should provide the "centralized identity and access management" (FR-009)? → A: Lightweight local identity provider (e.g., Authelia or basic auth) to save RAM and simplify single-VM deployment
- Q: What primary protocol should edge devices use to send high-frequency telemetry to the system? → A: MQTT (IoT standard, lightweight, good for high-frequency telemetry on edge devices)
- Q: What size/class of LLM is targeted for local AI inference to fit within the 16-32GB VM constraint? → A: Use Google AI Studio external API not local LLM
- Q: For the "object storage" and "in-memory analytical SQL", what is the preferred technology approach? → A: Embedded query engine over lightweight object storage (e.g., DuckDB + MinIO) - lowest RAM overhead, runs directly on files
- Q: How should the ingestion layer handle bursts of telemetry that exceed storage I/O or network bandwidth? → A: Buffer incoming messages in a lightweight disk queue (e.g. Redpanda/NATS JetStream buffer) and backpressure clients when buffer reaches limit
- Q: How should the platform manage concurrent AI requests and external Google AI Studio API rate limits? → A: Asynchronous task queue with rate-limited worker dispatch and semantic caching (Redis) to prevent quota exhaustion
- Q: Is an NVIDIA GPU still required for the host VM given that AI inference runs via Google AI Studio? → A: No GPU needed (CPU-only VM is fully sufficient since AI runs via Google AI Studio)
- Q: How should OSINT collection scans (FR-007) be triggered and integrated into the knowledge graph (FR-006)? → A: Ad-hoc manual execution via SpiderFoot standalone UI with manual export/import
- Q: How should edge nodes and analysts securely connect to the single VM (FR-010)? → A: Reverse proxy only (HTTPS + mutual TLS for edge devices, no VPN)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Secure Telemetry and Data Ingestion (Priority: P1)

As a data engineer, I want to ingest high-volume telemetry and events securely from edge devices into a unified system, so that I can centralize all operational data without losing events.

**Why this priority**: Without reliable data ingestion, the Big Data platform has no data to process. This is the foundation of the system.

**Independent Test**: Can be fully tested by sending simulated high-frequency event streams and verifying that 100% of events are stored and available for querying.

**Acceptance Scenarios**:

1. **Given** a deployed platform, **When** edge devices send high-frequency telemetry data, **Then** the platform receives, queues, and stores the data without dropping events.
2. **Given** external data sources, **When** data pipelines are triggered, **Then** the platform fetches and standardizes the data into the central data lake.

---

### User Story 2 - High-Performance Analytics and Querying (Priority: P1)

As a data analyst, I want to execute complex analytical queries across massive datasets efficiently on a constrained environment, so that I can generate insights without needing a large cluster.

**Why this priority**: The core value proposition of the platform is processing Big Data efficiently on a single node.

**Independent Test**: Can be tested by loading a multi-gigabyte dataset and running complex analytical queries, measuring response times and resource utilization.

**Acceptance Scenarios**:

1. **Given** gigabytes of stored data in the lakehouse, **When** an analyst runs a complex aggregation query, **Then** the system returns results quickly without exhausting system memory.
2. **Given** multiple analysts querying simultaneously, **When** concurrent queries are executed, **Then** the system manages resources to complete all queries without crashing.

---

### User Story 3 - AI-Powered Intelligence Correlation (Priority: P2)

As an intelligence analyst, I want to use AI models to automatically correlate data and extract insights from the data lake, so that I can discover hidden relationships and threats.

**Why this priority**: AI integration is the key differentiator for Artemis, transforming it from a simple data lake to an intelligence platform.

**Independent Test**: Can be tested by providing unstructured data and verifying the AI model can extract entities, relationships, and answer natural language questions about the data.

**Acceptance Scenarios**:

1. **Given** unstructured intelligence reports, **When** ingested into the system, **Then** the system extracts entities and relationships into a knowledge graph.
2. **Given** the integrated knowledge graph, **When** an analyst asks a natural language question, **Then** the AI provides an accurate answer based on the stored data using Google AI Studio.

### Edge Cases

- **Ingestion Overload / I/O Saturation**: Excess incoming messages are buffered in a local disk queue (Redpanda / NATS JetStream); when buffer capacity is reached, backpressure is applied to producers.
- **AI Inference Spikes & API Rate Limits**: Concurrent requests are managed via an asynchronous task queue with rate-limited dispatch and response caching in Redis to prevent external API quota exhaustion.
- **VM Failure/Reboot**: System will automatically restart with acceptable loss of in-flight/recent events to favor performance over strict ACID guarantees.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST ingest high-frequency data streams and message queues primarily via MQTT protocol.
- **FR-002**: System MUST provide object storage capabilities for large-scale data retention (e.g., using MinIO).
- **FR-003**: System MUST execute in-memory analytical SQL queries directly on stored files using an embedded query engine (e.g., DuckDB).
- **FR-004**: System MUST maintain relational state and time-series metrics.
- **FR-005**: System MUST provide AI inference capabilities via Google AI Studio external API (RAG and LLM).
- **FR-006**: System MUST maintain a knowledge graph for intelligence correlation.
- **FR-007**: System MUST provide standalone OSINT collection and footprinting (e.g. SpiderFoot UI) with ad-hoc manual scan triggers and export/import capability into the knowledge graph.
- **FR-008**: System MUST orchestrate data pipelines and workflows.
- **FR-009**: System MUST enforce centralized identity and access management using a lightweight local identity provider (e.g., Authelia or basic auth) to conserve RAM.
- **FR-010**: System MUST provide secure reverse proxy (e.g. Traefik) with HTTPS for analysts and mutual TLS (mTLS) for edge devices (no VPN mesh required).

### Key Entities

- **Telemetry Event**: Time-stamped data point from an edge device.
- **Data Pipeline**: A scheduled or event-driven workflow for processing data.
- **Intelligence Node**: An entity (person, organization, IP) extracted and stored in the knowledge graph.
- **AI Query**: A natural language request processed via Google AI Studio against the data lake.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The entire platform MUST successfully deploy and run on a single Virtual Machine with 16-32GB RAM.
- **SC-002**: Idle memory consumption of the platform MUST remain below 12GB.
- **SC-003**: System MUST handle ingestion of at least 10,000 events per second without data loss.
- **SC-004**: Analytical queries on 10GB datasets MUST complete in under 5 seconds.
- **SC-005**: AI inference MUST execute via Google AI Studio external API to conserve local VM resources.

## Assumptions

- The target deployment environment is a single Virtual Machine with Linux.
- The VM has 16-32GB of RAM and sufficient NVMe storage.
- The VM is a standard CPU-only instance (no dedicated GPU required since AI inference runs externally via Google AI Studio).
- Users and edge devices access the platform via secure reverse proxy with TLS/mTLS.
