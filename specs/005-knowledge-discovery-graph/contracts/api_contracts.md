# REST API Contracts: Discovery (`/api/v1/discovery`)

All endpoints require authentication (existing middleware). Schemas: see [data-model.md](../data-model.md).

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/workspace/{project_id}` | Project knowledge summary | `WorkspaceKnowledgeContract` (404 unknown project) |
| GET | `/cross-project?value=&type=&fuzzy=` | Entity correlation across projects | `EntityCorrelationContract` (400 if neither value nor type) |
| GET | `/lineage/{project_id}/{dataset_id}?depth=` | Lineage tree | `LineageContract` (404 unknown dataset) |
| POST | `/reindex/{project_id}` | Trigger reindex (body: optional `dataset_id`) | 202 `IndexJobContract` |
| GET | `/jobs/{project_id}?status=` | List indexing jobs | `IndexJobContract[]` |
| GET | `/api/v1/projects/{project_id}/members` | List members (members only) | `MemberContract[]` |
| POST | `/api/v1/projects/{project_id}/members` | Add member (owner/admin); body `MemberAddRequestContract` | 201 `MemberContract` |
| DELETE | `/api/v1/projects/{project_id}/members/{user_id}` | Remove member (owner/admin; last owner cannot be removed → 409) | 204 |

## Rules
- Every discovery endpoint filters by the caller's project membership; non-member projects are omitted, including from counts and totals. Requests naming a non-member project return 404, identical to an unknown project (FR-021).
- Cross-project responses MUST NOT include `location_uri`, sample rows, or S3 paths (FR-016).
- Errors use the platform's standard `{ "detail": "..." }` shape.

## AI Agent Tool Contracts (`DynamicAgentLoop`)

| Tool | Arguments | Returns |
|------|-----------|---------|
| `discover_workspace_schema` | `project_id: str` | `WorkspaceKnowledgeContract` as dict |
| `find_cross_project_entities` | `value: str \| None`, `entity_type: str \| None` | `EntityCorrelationContract` as dict |
| `get_data_lineage` | `project_id: str`, `dataset_id: str` | `LineageContract` as dict |

Tools are read-only, parameterized, and bound by the existing 5 s timeout. The member-project list is taken from the authenticated request context, not from tool arguments.
