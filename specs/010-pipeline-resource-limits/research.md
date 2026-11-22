# Research & Architectural Decisions: Customizable CPU and Memory Limits for Pipeline Runs

**Feature**: `010-pipeline-resource-limits`  
**Date**: 2026-11-21  
**Spec**: [spec.md](./spec.md)

---

## 1. Settings & Environment Variable Schema for Defaults, Hard Caps, and Overflow Policy

- **Decision**: Extend `Settings` in `src/config/settings.py` with explicit administrator-controlled environment variables while preserving backward compatibility with existing `DOCKER_RUNNER_CPU_LIMIT` and `DOCKER_RUNNER_MEMORY_LIMIT` variables:
  - `docker_runner_cpu_limit: float = float(os.getenv("DOCKER_RUNNER_CPU_LIMIT", "2.0"))` — System default CPU allocation in fractional cores.
  - `docker_runner_memory_limit: str = os.getenv("DOCKER_RUNNER_MEMORY_LIMIT", "2g")` — System default memory allocation string.
  - `docker_runner_max_cpu_limit: float = float(os.getenv("DOCKER_RUNNER_MAX_CPU_LIMIT", "4.0"))` — Administrator hard maximum CPU cap in fractional cores.
  - `docker_runner_max_memory_limit: str = os.getenv("DOCKER_RUNNER_MAX_MEMORY_LIMIT", "4g")` — Administrator hard maximum memory cap string.
  - `docker_runner_min_cpu_limit: float = float(os.getenv("DOCKER_RUNNER_MIN_CPU_LIMIT", "0.1"))` — Minimum operational CPU floor in cores (`0.1`).
  - `docker_runner_min_memory_limit: str = os.getenv("DOCKER_RUNNER_MIN_MEMORY_LIMIT", "64m")` — Minimum operational memory floor (`64m`).
  - `docker_runner_resource_overflow_policy: str = os.getenv("DOCKER_RUNNER_RESOURCE_OVERFLOW_POLICY", "reject").lower()` — Overflow enforcement behavior (`"reject"` or `"clamp"`).
- **Rationale**: Keeps existing `.env` and deployment configurations working without modification (`2.0` CPU cores and `2g` memory default) while providing dedicated, self-documenting environment variables for hard maximum caps (`4.0` CPU cores and `4g` memory) and overflow behavior (`reject` by default) that respect the Constitution's `< 12 GB` single-VM idle memory budget (`FR-001`, `FR-002`).
- **Alternatives Considered**:
  - *Reusing `DOCKER_CPU_LIMIT` / `DOCKER_MEMORY_LIMIT` as hard caps*: Rejected because `DOCKER_RUNNER_MAX_CPU_LIMIT` and `DOCKER_RUNNER_MAX_MEMORY_LIMIT` avoid ambiguity between the fallback default and the administrator ceiling.

---

## 2. Deterministic Memory String Parsing & Normalization

- **Decision**: Create a dedicated validation and resolution module `src/domains/pipeline/operations/resource_validator.py` with `parse_memory_bytes(value: str | int) -> int` and `format_memory_limit(bytes_val: int) -> str`:
  - Accepts case-insensitive human-readable strings matching `^\s*(\d+(?:\.\d+)?)\s*([bkmg]b?)?\s*$` (specifically `b`, `k`/`kb`, `m`/`mb`, `g`/`gb`) or positive integer byte strings.
  - Uses standard binary (base-1024) multipliers matching Docker's `mem_limit` engine parser:
    - `b`: `1`
    - `k` / `kb`: `1024`
    - `m` / `mb`: `1024 ** 2` (`1,048,576`)
    - `g` / `gb`: `1024 ** 3` (`1,073,741,824`)
  - Normalizes all memory comparisons (minimum floor `64m = 67,108,864` bytes, requested limit, pipeline default, system default, and admin hard cap `4g = 4,294,967,296` bytes) to exact integer bytes before evaluation (`FR-005`).
- **Rationale**: Comparing raw strings breaks across equivalent unit representations (`2048m` vs `2g` or `512MB` vs `0.5g`). Normalizing to exact integer bytes using Docker's native base-1024 convention guarantees zero discrepancy between validation checks and what the Docker daemon enforces (`SC-002`).
- **Alternatives Considered**:
  - *Base-1000 decimal multipliers for `MB`/`GB`*: Rejected because Docker's container runtime interprets `2g` and `2048m` in base-1024 bytes; matching Docker's exact unit interpretation ensures `2048m == 2g`.

---

## 3. Hierarchical Resolution (`Run Override → Pipeline Default → System Default`) & Overflow Policy

- **Decision**:
  - **Precedence Resolution**: `resolve_run_resources(...)` evaluates CPU and memory independently:
    1. If the run request specifies `cpu_limit` (or `memory_limit`), use it (`source = "run_override"`).
    2. Else if the target `Pipeline` entity has `default_cpu_limit` (or `default_memory_limit`) configured, use it (`source = "pipeline_default"`).
    3. Else fall back to `settings.docker_runner_cpu_limit` (or `settings.docker_runner_memory_limit`) (`source = "system_default"`).
  - **Validation Rules**:
    1. **Minimum Operational Floor (Always Reject)**: Any CPU `< 0.1` cores (or `<= 0`, `NaN`, `inf`) or memory `< 64m` (`67,108,864` bytes) or malformed unit string is immediately rejected with a descriptive `ValueError` regardless of whether `reject` or `clamp` policy is active (`FR-006`).
    2. **Explicit Request Exceeding Hard Cap**:
       - When validating an explicit user input (on `create_pipeline`, `update_pipeline`, or `trigger_run` with a `run_override`):
         - If `settings.docker_runner_resource_overflow_policy == "reject"` (default): raise `ValueError` stating the requested value and the maximum permitted hard cap (`FR-007`).
         - If `settings.docker_runner_resource_overflow_policy == "clamp"`: clamp the value down to the hard maximum cap and set `cpu_clamped = True` / `memory_clamped = True` (`resource_clamped = True`).
    3. **Fallback Default Exceeding Active Hard Cap**:
       - If an administrator lowers `DOCKER_RUNNER_MAX_CPU_LIMIT` or `DOCKER_RUNNER_MAX_MEMORY_LIMIT` below the system default or below a previously saved pipeline's `default_cpu_limit`/`default_memory_limit`, any run using that fallback automatically clamps the effective limit to the current hard maximum cap and records `resource_clamped = True` (`FR-008`).
- **Rationale**: Satisfies both `FR-007` (strict rejection or optional clamping on user inputs) and `FR-008` (resilient fallback clamping when admin caps are tightened post-creation so default runs never fail unexpectedly or violate caps).
- **Alternatives Considered**:
  - *Failing default runs when admin lowers hard cap below system default*: Rejected because `FR-008` explicitly mandates clamping the effective fallback default to the hard maximum cap.

---

## 4. Container Enforcement & Out-of-Memory (`exit_code: 137`) Detection

- **Decision**:
  - Update `DockerPipelineRunner.execute_script(...)` in `src/domains/pipeline/operations/docker_runner.py` to accept `cpu_limit: Optional[float] = None` and `memory_limit: Optional[str] = None`.
  - Resolve effective limits before container creation and pass `mem_limit=effective_memory_limit` and `nano_cpus=int(round(effective_cpu_limit * 1e9))` to `self._client.containers.run(...)`.
  - After `container.wait(timeout=timeout)` returns, inspect `result.get("StatusCode", 1)` and container state (`container.reload()` → `container.attrs.get("State", {}).get("OOMKilled", False)`):
    - If `exit_code == 137` or `oom_killed is True`:
      - Ensure `exit_code` is recorded as `137` (`docker_runner.py` returns `oom_killed: bool = True` on `DockerRunnerResult`).
      - `PipelineExecutor` keeps `status = "FAILED"`, sets `exit_code = 137`, and formats an explicit OOM diagnostic error message in `details["error"]` and `details["oom_killed"] = True` (and appends the OOM diagnostic notice to `logs` if stderr is empty):
        `f"Out of Memory (OOM): Container killed (exit code 137) after exceeding effective memory limit of {effective_memory_limit}."` (`FR-011`).
- **Rationale**: In Linux/Docker cgroups, a container that exceeds `mem_limit` is killed by the kernel OOM killer with `SIGKILL` (`128 + 9 = 137`) and flags `State.OOMKilled = true`. Checking both `exit_code == 137` and `State.OOMKilled` guarantees accurate detection across Docker engines while preserving existing `status = "FAILED"` enum compatibility (`Q3: Option A`).
- **Alternatives Considered**:
  - *Disabling memory swap without setting `mem_limit`*: We pass `mem_limit=effective_memory_limit` directly to Docker so cgroup memory limits are strictly enforced.

---

## 5. Database Schema Evolution & Backward Compatibility

- **Decision**:
  - Update `src/config/postgres_init.sql` to include:
    - On `project_pipelines`: `default_cpu_limit DOUBLE PRECISION` and `default_memory_limit VARCHAR(32)`.
    - Idempotent `ALTER TABLE project_pipelines ADD COLUMN IF NOT EXISTS default_cpu_limit DOUBLE PRECISION;` and `ALTER TABLE project_pipelines ADD COLUMN IF NOT EXISTS default_memory_limit VARCHAR(32);` statements.
  - Also ensure `PipelineManager` executes a lightweight idempotent column check (`_ensure_resource_columns()`) and stores per-run resource allocation metadata inside `project_pipeline_runs.details` JSONB (`effective_cpu_limit`, `effective_memory_limit`, `requested_cpu_limit`, `requested_memory_limit`, `cpu_source`, `memory_source`, `resource_clamped`, `oom_killed`) AND hydrates top-level fields on `PipelineRunResponseContract`.
- **Rationale**: Storing per-run resource allocation details in `project_pipeline_runs.details` JSONB (and hydrating top-level contract fields on `PipelineRunResponseContract` in `create_run_record`, `complete_run_record`, and `list_runs`) avoids destructive table rebuilds while persisting full audit metadata (`FR-010`). Adding nullable `default_cpu_limit` and `default_memory_limit` columns to `project_pipelines` supports per-pipeline defaults cleanly (`FR-003`).
- **Alternatives Considered**:
  - *Creating a separate `pipeline_resource_allocations` table with foreign keys*: Rejected as over-engineered when `project_pipelines` has 2 nullable columns and `project_pipeline_runs` already has a `details JSONB` column designed for execution metadata.
