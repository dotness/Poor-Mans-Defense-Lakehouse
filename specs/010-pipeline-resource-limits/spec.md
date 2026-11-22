# Feature Specification: Customizable CPU and Memory Limits for Pipeline Runs

**Feature Branch**: `010-pipeline-resource-limits`

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "Add support for customizable CPU and memory limits on pipeline runs. Introduce admin-defined hard maximum caps alongside system defaults (via settings/environment variables), and allow users to request custom CPU and memory allocations per run request. Any requested resources must be validated against the admin hard caps, clamping or rejecting values that exceed them while falling back to the defaults when unspecified."

## Clarifications

### Session 2026-11-21

- Q: When a user requests CPU or memory exceeding the administrator's hard maximum cap, should the system reject the request, clamp it to the cap, or support a configurable policy? → A: Configurable overflow policy (Default: `reject`) — reject with a validation error by default, with an admin setting (`reject` | `clamp`) to clamp to the hard cap instead.
- Q: Should custom CPU and memory limits be specified only per run request, or also saved as optional per-pipeline defaults on the Pipeline entity? → A: Per-pipeline defaults + per-run overrides — pipelines can store optional default CPU/memory allocations, and runs resolve limits in the order `run request → pipeline default → system default` (all validated against admin hard caps).
- Q: When a pipeline container exceeds its effective memory limit at runtime and is killed (exit code `137`), how should the run record report it? → A: `FAILED` status + OOM diagnostic detail — keep status `FAILED`, record `exit_code: 137`, and populate an explicit OOM error message referencing the applied memory limit.
- Q: What input format and minimum operational bounds should be enforced for CPU and memory requests across CLI and API? → A: Float CPU cores (min `0.1`, e.g., `0.5`, `2.0`) and unit-suffixed memory size string (`b`, `k`/`kb`, `m`/`mb`, `g`/`gb`, case-insensitive, min `64m`, e.g., `512m`, `2g`).
- Q: What out-of-the-box values should be set for system defaults and administrator hard maximum caps when environment variables are not overridden? → A: System Defaults: `2.0` CPU cores / `2g` RAM; Administrator Hard Caps: `4.0` CPU cores / `4g` RAM.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Per-Pipeline Default and Per-Run Custom CPU & Memory Requests (Priority: P1)

As a data analyst or pipeline operator creating or triggering a pipeline, I want to optionally define default CPU and memory allocations on a saved pipeline definition and optionally override CPU and memory allocations on an individual run request—falling back through `run request → pipeline default → system default`—so that recurring workloads retain appropriate resource profiles while ad-hoc runs can be tuned on demand.

**Why this priority**: Delivers the core user-facing capability allowing pipeline authors and operators to tailor compute and memory resources to the size and complexity of both recurring pipelines and individual run requests without requiring global configuration changes.

**Independent Test**: Create a pipeline with custom default CPU/memory limits, trigger one run without per-run overrides (verifying it uses the pipeline defaults), trigger a second run with per-run CPU/memory overrides (verifying it uses the per-run values), and trigger a third run on a pipeline without pipeline defaults (verifying it falls back to the system defaults `2.0` CPU / `2g` RAM).

**Acceptance Scenarios**:

1. **Given** a registered project pipeline and valid custom CPU and memory values at or below the administrator hard caps, **When** a user submits a pipeline run request specifying both custom CPU and memory limits, **Then** the system executes the pipeline run constrained to those exact requested CPU and memory allocations (overriding any pipeline-level or system defaults) and records the applied limits on the run record.
2. **Given** a registered project pipeline configured with pipeline-level default CPU and memory limits, **When** a user submits a pipeline run request without specifying per-run CPU or memory parameters, **Then** the system applies the pipeline's default CPU and memory limits (validated against the administrator hard caps).
3. **Given** a registered project pipeline with no pipeline-level resource defaults configured, **When** a user submits a pipeline run request without specifying CPU or memory parameters, **Then** the system automatically applies the configured system default CPU (`2.0` cores) and memory (`2g`) limits to the execution.
4. **Given** a registered project pipeline, **When** a user submits a pipeline run request specifying only a custom CPU limit (omitting memory) or only a custom memory limit (omitting CPU), **Then** the system applies the custom per-run value for the specified resource and resolves the omitted resource via `pipeline default → system default`.

---

### User Story 2 - Administrator Hard Maximum Caps & Validation Enforcement (Priority: P1)

As a platform administrator operating on a resource-constrained host, I want to define system-wide default allocations (`2.0` CPU / `2g` RAM out-of-the-box) alongside hard maximum caps (`4.0` CPU / `4g` RAM out-of-the-box) and an overflow policy (`reject` by default, or `clamp`) via system settings, and have the platform automatically validate pipeline defaults and run requests against those caps so that no single pipeline execution can exhaust host capacity or starve core platform services.

**Why this priority**: Essential operational safeguard on a single-host platform with a strict memory budget; custom resource requests cannot be safely exposed without enforceable upper bounds.

**Independent Test**: Configure system default limits and administrator hard maximum caps, submit a run request (or pipeline creation/update) exceeding the CPU or memory hard cap under both `reject` and `clamp` policies, and verify that the system enforces the cap according to the active validation policy and never launches an execution above the hard maximum.

**Acceptance Scenarios**:

1. **Given** administrator-configured hard maximum caps for CPU and memory and the default `reject` overflow policy, **When** a user requests a per-run or pipeline-default CPU or memory allocation that exceeds the respective hard maximum cap, **Then** the system rejects the request before execution or persistence and returns an actionable error message stating the requested value and the maximum permitted limit.
2. **Given** administrator-configured hard maximum caps and the `clamp` overflow policy enabled in system settings, **When** a user requests a CPU or memory allocation that exceeds the respective hard maximum cap, **Then** the system clamps the allocation down to the hard maximum cap, executes the run with the clamped value, and records both the requested and effective (clamped) limits in the run details.
3. **Given** a user submitting a malformed, zero, negative, or below-floor CPU or memory limit (e.g., `< 0.1` CPU cores, `< 64m` memory, or an unrecognized unit suffix), **When** the request is validated, **Then** the system immediately rejects the request with a descriptive validation error regardless of whether `reject` or `clamp` overflow policy is active.
4. **Given** system startup or runtime resolution where a system default or saved pipeline default CPU/memory setting exceeds the currently configured administrator hard maximum cap, **When** the effective limit is resolved, **Then** the system clamps the effective fallback default to the hard maximum cap so runs never violate administrator caps.

---

### User Story 3 - Resource Allocation & OOM Visibility in Run Status & History (Priority: P2)

As an analyst or administrator reviewing pipeline executions, I want to inspect the effective CPU and memory limits applied to any active or historical pipeline run—including whether a request was defaulted or clamped, and explicit Out-of-Memory (OOM) diagnostics when a run exceeds its memory limit—so that I can diagnose OOM failures, performance bottlenecks, and resource utilization trends across projects.

**Why this priority**: Provides observability and auditability for custom resource usage, enabling users to understand why a heavy transformation succeeded, failed, or was constrained.

**Independent Test**: Execute pipeline runs using default, custom, and clamped resource allocations as well as a run that exceeds its memory allocation at runtime; query the pipeline run status and run history via both the command-line interface and programmatic interface to confirm the applied CPU/memory limits and OOM diagnostics (`FAILED` status, exit code `137`, and OOM message referencing the memory limit) are displayed accurately.

**Acceptance Scenarios**:

1. **Given** a completed or running pipeline execution, **When** an authorized user inspects the run details or project pipeline execution history, **Then** the output includes the effective CPU limit and memory limit applied to that run (along with requested values and clamping indicators if clamped).
2. **Given** a pipeline execution that is terminated by the container runtime for exceeding its effective memory limit (exit code `137` / OOM kill), **When** the user inspects the failed run record, **Then** the run record reports status `FAILED`, records `exit_code: 137`, and includes an explicit OOM diagnostic error message referencing the effective memory limit that was enforced.

---

### Edge Cases

- **Human-Readable Memory Units & Normalization**: Users and administrators may express memory allocations in different standard units (`b`, `k`/`kb`, `m`/`mb`, `g`/`gb`, case-insensitive, e.g., `512m` / `512MB`, `2g` / `2GB`). Validation against minimum floors and hard caps must normalize memory values to an exact byte scale before comparison so `2048m` is accurately recognized as equal to `2g` and `2500m` is recognized as exceeding `2g`.
- **Fractional CPU Allocations**: Users must be able to request fractional CPU allocations (e.g., `0.5` cores, `1.5` cores) as well as whole numbers, subject to a minimum floor of `0.1` CPU cores to prevent unusable near-zero execution allocations.
- **Minimum Viable Memory Floor**: Requests specifying positive but impossibly small memory limits below `64m` (`64MB`, the minimum threshold required to start the execution runtime) must be rejected with a clear minimum-bound validation error.
- **Default or Saved Pipeline Limit Exceeding Lowered Hard Cap**: If an administrator lowers the hard maximum cap via an environment variable override below the system default or below a previously saved pipeline's default limit, the effective limit resolved at run time must be clamped to the current hard maximum cap so no run ever exceeds the active hard cap.
- **Partial Resource Specification Across Hierarchy**: If a run request specifies only CPU, memory must resolve from the pipeline's default memory limit (if set) or the system default memory limit; conversely, specifying only memory on a run request must resolve CPU from the pipeline's default CPU limit (if set) or the system default CPU limit.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide administrator-configurable settings (controllable via environment variables) defining the system default CPU limit (defaulting to `2.0` cores out-of-the-box) and system default memory limit (defaulting to `2g` out-of-the-box) for pipeline runs.
- **FR-002**: System MUST provide administrator-configurable settings (controllable via environment variables) defining the hard maximum CPU cap (defaulting to `4.0` cores out-of-the-box), hard maximum memory cap (defaulting to `4g` out-of-the-box), and cap overflow policy (`reject` or `clamp`, defaulting to `reject`) allowed for any single pipeline run.
- **FR-003**: System MUST allow users creating or updating a Pipeline definition (via both the command-line interface and programmatic interface) to optionally configure pipeline-level default CPU and memory limits, and allow users triggering a pipeline run to optionally specify per-run custom CPU and memory limits.
- **FR-004**: When resolving resource limits for a pipeline run, the system MUST apply the precedence order `per-run request → pipeline-level default → system default` independently for CPU and memory.
- **FR-005**: System MUST accept CPU limits as floating-point core counts and memory limits as human-readable size strings with standard unit suffixes (`b`, `k`/`kb`, `m`/`mb`, `g`/`gb`, case-insensitive), normalizing memory expressions into an exact byte value before comparing against minimum bounds and administrator hard maximum caps.
- **FR-006**: System MUST validate requested CPU and memory values (both on pipeline definitions and run requests) against minimum operational floors (CPU >= `0.1` cores; memory >= `64m` / `64MB`) and immediately reject any zero, negative, malformed, or below-floor values with an explicit validation error.
- **FR-007**: System MUST validate requested CPU and memory allocations against the administrator-defined hard maximum caps, enforcing cap compliance according to the configured overflow policy: rejecting requests that exceed either cap with an actionable validation error stating the requested value and maximum permitted limit (when policy is `reject`), or clamping excessive values down to the hard maximum cap and recording that clamping occurred (when policy is `clamp`).
- **FR-008**: If the configured system default or a saved pipeline-level default for CPU or memory exceeds the currently active administrator hard maximum cap, the system MUST clamp the effective fallback limit to the hard maximum cap so that pipeline runs never violate active administrator hard caps.
- **FR-009**: System MUST enforce the resolved effective CPU and memory limits on the isolated pipeline execution container for the duration of the pipeline run.
- **FR-010**: System MUST persist and expose the effective CPU limit and memory limit (along with requested values and an indication if clamping occurred) in the pipeline run execution record and run history responses across both formatted human-readable output and machine-readable JSON output.
- **FR-011**: When a pipeline execution container is terminated due to exceeding its memory allocation (exit code `137` / OOM kill), the system MUST record the run status as `FAILED` with `exit_code: 137` and populate an explicit OOM diagnostic error message referencing the effective memory limit that was enforced.

### Key Entities *(include if feature involves data)*

- **ResourceLimitPolicy**: Represents the system-wide resource governance configuration managed by administrators. Key attributes: default CPU limit (`2.0` cores default), default memory limit (`2g` default), hard maximum CPU cap (`4.0` cores default), hard maximum memory cap (`4g` default), minimum CPU floor (`0.1` cores), minimum memory floor (`64m`), and cap overflow policy (`reject` default, or `clamp`).
- **Pipeline**: Extended with optional pipeline-level resource defaults (`default_cpu_limit`: optional float cores; `default_memory_limit`: optional size string) that serve as the fallback when a run request does not specify per-run overrides.
- **PipelineRunResourceRequest**: Represents the optional user-supplied resource preferences on an individual pipeline run trigger. Key attributes: requested CPU cores (`cpu_limit`: optional float), requested memory limit (`memory_limit`: optional size string).
- **AppliedResourceAllocation**: Represents the validated, resolved resource limits enforced on a specific pipeline run and recorded in its execution metadata. Key attributes: effective CPU cores, effective memory limit, requested CPU cores, requested memory limit, resolution source (`run_override`, `pipeline_default`, or `system_default`), clamping indicator (`resource_clamped: boolean`), and OOM diagnostic metadata when terminated with exit code `137`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of pipeline run requests that omit per-run CPU and/or memory parameters accurately resolve their effective limits via `pipeline default → system default` without requiring changes to existing callers.
- **SC-002**: 100% of pipeline run requests specifying custom CPU and memory values within administrator caps are enforced on the isolated execution environment with zero discrepancy between the resolved limit and the runtime limit.
- **SC-003**: 100% of pipeline run requests specifying CPU or memory allocations above the administrator hard maximum caps are prevented from exceeding those caps (either rejected in under 1 second prior to container launch under `reject` policy, or clamped strictly to the hard maximum cap under `clamp` policy).
- **SC-004**: 100% of pipeline run records in execution history report the effective CPU and memory limits applied to the run, and 100% of memory-exceeded terminations (`exit_code: 137`) record a `FAILED` status with an explicit OOM message citing the applied memory limit.
- **SC-005**: Enforcing per-run CPU and memory caps keeps individual pipeline executions bounded so total platform host memory remains compliant with the single-VM operating budget.

## Assumptions

- Out-of-the-box system defaults remain aligned with the platform's existing resource budget (`2.0` CPU cores and `2g` memory default per run), while administrator hard maximum caps default to safe single-VM burst bounds (`4.0` CPU cores max and `4g` memory max) unless overridden via settings/environment variables.
- Both strict rejection and automatic clamping of values exceeding hard caps are supported through an administrator-configurable overflow behavior setting (defaulting to `reject` so users receive clear feedback when requesting more resources than permitted, with optional `clamp` mode when administrators prefer automatic cap clamping).
- Minimum operational bounds are `0.1` CPU cores and `64m` (`64MB`) of memory to prevent container startup failures from near-zero values.
- Existing pipelines created prior to this feature have null/unset pipeline-level resource defaults and seamlessly inherit the system default limits (`2.0` CPU cores and `2g` memory) unless updated.
