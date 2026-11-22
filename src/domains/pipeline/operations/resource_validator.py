import math
import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple, Union, Dict, Any

try:
    from src.config.settings import settings
except ImportError:
    from config.settings import settings

MEMORY_REGEX = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([bkmg]b?)?\s*$", re.IGNORECASE)

UNIT_MULTIPLIERS: Dict[str, int] = {
    "": 1,
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "m": 1024 ** 2,
    "mb": 1024 ** 2,
    "g": 1024 ** 3,
    "gb": 1024 ** 3,
}


@dataclass(frozen=True)
class ResolvedResourceAllocation:
    effective_cpu_limit: float
    effective_memory_limit: str
    effective_memory_bytes: int
    requested_cpu_limit: Optional[float]
    requested_memory_limit: Optional[str]
    cpu_source: str          # "run_override" | "pipeline_default" | "system_default"
    memory_source: str       # "run_override" | "pipeline_default" | "system_default"
    cpu_clamped: bool
    memory_clamped: bool

    @property
    def resource_clamped(self) -> bool:
        return self.cpu_clamped or self.memory_clamped

    def to_metadata_dict(self) -> Dict[str, Any]:
        return {
            "effective_cpu_limit": self.effective_cpu_limit,
            "effective_memory_limit": self.effective_memory_limit,
            "effective_memory_bytes": self.effective_memory_bytes,
            "requested_cpu_limit": self.requested_cpu_limit,
            "requested_memory_limit": self.requested_memory_limit,
            "cpu_source": self.cpu_source,
            "memory_source": self.memory_source,
            "cpu_clamped": self.cpu_clamped,
            "memory_clamped": self.memory_clamped,
            "resource_clamped": self.resource_clamped,
        }


def parse_memory_bytes(value: Union[str, int, float]) -> int:
    """
    Parses a human-readable memory size expression (e.g., '512m', '2g', '1024KB', 134217728)
    into an exact positive integer byte count using base-1024 multipliers.
    Raises ValueError on malformed, zero, negative, or unsupported unit expressions.
    """
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Invalid memory limit '{value}': expected size string (e.g. '512m', '2g').")

    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ValueError(f"Invalid memory limit '{value}': value must be finite.")
        if value <= 0:
            raise ValueError(f"Invalid memory limit '{value}': memory must be greater than zero.")
        return int(round(value))

    if not isinstance(value, str):
        raise ValueError(f"Invalid memory limit '{value}': expected string or positive integer bytes.")

    stripped = value.strip()
    if not stripped:
        raise ValueError("Invalid memory limit '': value cannot be empty.")

    if stripped.startswith("-"):
        raise ValueError(f"Invalid memory limit '{value}': memory cannot be negative.")

    match = MEMORY_REGEX.match(stripped)
    if not match:
        raise ValueError(
            f"Invalid memory limit '{value}': must be a positive number with unit suffix "
            f"('b', 'k'/'kb', 'm'/'mb', 'g'/'gb'), e.g. '512m' or '2g'."
        )

    num_str, unit_str = match.group(1), (match.group(2) or "").lower()
    num_val = float(num_str)
    if math.isnan(num_val) or math.isinf(num_val) or num_val <= 0:
        raise ValueError(f"Invalid memory limit '{value}': memory must be greater than zero.")

    multiplier = UNIT_MULTIPLIERS.get(unit_str)
    if multiplier is None:
        raise ValueError(f"Unsupported memory unit '{unit_str}' in '{value}'.")

    byte_count = int(round(num_val * multiplier))
    if byte_count <= 0:
        raise ValueError(f"Invalid memory limit '{value}': computed byte size must be positive.")
    return byte_count


def format_memory_limit(byte_count: int) -> str:
    """
    Formats a byte count into a clean Docker-compatible memory limit string
    ('g', 'm', 'k', or 'b').
    """
    if byte_count <= 0:
        raise ValueError(f"Cannot format non-positive byte count: {byte_count}")
    gb = 1024 ** 3
    mb = 1024 ** 2
    kb = 1024
    if byte_count % gb == 0:
        return f"{byte_count // gb}g"
    if byte_count % mb == 0:
        return f"{byte_count // mb}m"
    if byte_count % kb == 0:
        return f"{byte_count // kb}k"
    return f"{byte_count}b"


def normalize_memory_string(raw: str) -> Tuple[str, int]:
    """
    Validates a memory limit string and returns (canonical_docker_string, byte_count).
    Preserves clean input strings like '512m', '2048m', '2g' in lowercase Docker format
    (stripping trailing 'b' from 'mb'/'gb'/'kb' so Docker accepts e.g. '512m', '2g').
    """
    byte_count = parse_memory_bytes(raw)
    stripped = str(raw).strip().lower()
    match = MEMORY_REGEX.match(stripped)
    if match:
        num_str, unit_str = match.group(1), (match.group(2) or "").lower()
        # If integer value with standard unit, normalize 'mb' -> 'm', 'gb' -> 'g', 'kb' -> 'k'
        if "." not in num_str and unit_str in ("k", "kb", "m", "mb", "g", "gb", "b"):
            short_unit = unit_str[0]
            return f"{int(num_str)}{short_unit}", byte_count
    return format_memory_limit(byte_count), byte_count


def _validate_cpu_value(
    cpu_val: float,
    min_cpu: float,
    max_cpu: float,
    overflow_policy: str,
    is_explicit_request: bool,
) -> Tuple[float, bool]:
    """
    Validates a CPU core count against minimum operational floor and hard maximum cap.
    Returns (effective_cpu, was_clamped).
    """
    if isinstance(cpu_val, bool) or not isinstance(cpu_val, (int, float)):
        raise ValueError(f"Invalid CPU limit '{cpu_val}': expected a numeric core count (e.g. 0.5, 2.0).")
    cpu_float = float(cpu_val)
    if math.isnan(cpu_float) or math.isinf(cpu_float):
        raise ValueError(f"Invalid CPU limit '{cpu_val}': CPU cores must be a finite number.")
    if cpu_float <= 0:
        raise ValueError(f"Invalid CPU limit {cpu_float}: CPU cores must be greater than zero (minimum {min_cpu} cores).")
    if cpu_float < min_cpu:
        raise ValueError(
            f"Requested CPU limit {cpu_float} cores is below the minimum operational floor of {min_cpu} cores."
        )

    if cpu_float > max_cpu:
        if is_explicit_request and overflow_policy != "clamp":
            raise ValueError(
                f"Requested CPU limit {cpu_float} cores exceeds administrator hard maximum cap of {max_cpu} cores."
            )
        return max_cpu, True

    return round(cpu_float, 4), False


def _validate_memory_value(
    mem_val: str,
    min_mem_str: str,
    max_mem_str: str,
    overflow_policy: str,
    is_explicit_request: bool,
) -> Tuple[str, int, bool]:
    """
    Validates a memory limit string against minimum operational floor and hard maximum cap.
    Returns (effective_memory_str, effective_memory_bytes, was_clamped).
    """
    min_bytes = parse_memory_bytes(min_mem_str)
    max_norm_str, max_bytes = normalize_memory_string(max_mem_str)
    norm_str, req_bytes = normalize_memory_string(mem_val)

    if req_bytes < min_bytes:
        raise ValueError(
            f"Requested memory limit '{mem_val}' ({req_bytes} bytes) is below the minimum operational floor "
            f"of '{min_mem_str}' ({min_bytes} bytes)."
        )

    if req_bytes > max_bytes:
        if is_explicit_request and overflow_policy != "clamp":
            raise ValueError(
                f"Requested memory limit '{mem_val}' ({req_bytes} bytes) exceeds administrator hard maximum cap "
                f"of '{max_mem_str}' ({max_bytes} bytes)."
            )
        return max_norm_str, max_bytes, True

    return norm_str, req_bytes, False


def validate_pipeline_default_resources(
    default_cpu_limit: Optional[float] = None,
    default_memory_limit: Optional[str] = None,
    min_cpu_limit: Optional[float] = None,
    max_cpu_limit: Optional[float] = None,
    min_memory_limit: Optional[str] = None,
    max_memory_limit: Optional[str] = None,
    overflow_policy: Optional[str] = None,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Validates optional per-pipeline default CPU and memory limits during pipeline creation or update.
    Returns (validated_default_cpu_limit, validated_default_memory_limit).
    """
    min_cpu = float(
        min_cpu_limit
        if min_cpu_limit is not None
        else os.getenv("DOCKER_RUNNER_MIN_CPU_LIMIT", str(settings.docker_runner_min_cpu_limit))
    )
    max_cpu = float(
        max_cpu_limit
        if max_cpu_limit is not None
        else os.getenv("DOCKER_RUNNER_MAX_CPU_LIMIT", str(settings.docker_runner_max_cpu_limit))
    )
    min_mem = str(
        min_memory_limit
        if min_memory_limit is not None
        else os.getenv("DOCKER_RUNNER_MIN_MEMORY_LIMIT", settings.docker_runner_min_memory_limit)
    )
    max_mem = str(
        max_memory_limit
        if max_memory_limit is not None
        else os.getenv("DOCKER_RUNNER_MAX_MEMORY_LIMIT", settings.docker_runner_max_memory_limit)
    )
    policy = str(
        overflow_policy
        if overflow_policy is not None
        else os.getenv("DOCKER_RUNNER_RESOURCE_OVERFLOW_POLICY", settings.docker_runner_resource_overflow_policy)
    ).lower()

    resolved_cpu: Optional[float] = None
    resolved_mem: Optional[str] = None

    if default_cpu_limit is not None:
        resolved_cpu, _ = _validate_cpu_value(
            cpu_val=default_cpu_limit,
            min_cpu=min_cpu,
            max_cpu=max_cpu,
            overflow_policy=policy,
            is_explicit_request=True,
        )

    if default_memory_limit is not None:
        resolved_mem, _, _ = _validate_memory_value(
            mem_val=default_memory_limit,
            min_mem_str=min_mem,
            max_mem_str=max_mem,
            overflow_policy=policy,
            is_explicit_request=True,
        )

    return resolved_cpu, resolved_mem


def resolve_run_resources(
    requested_cpu_limit: Optional[float] = None,
    requested_memory_limit: Optional[str] = None,
    pipeline_default_cpu_limit: Optional[float] = None,
    pipeline_default_memory_limit: Optional[str] = None,
    system_default_cpu_limit: Optional[float] = None,
    system_default_memory_limit: Optional[str] = None,
    min_cpu_limit: Optional[float] = None,
    max_cpu_limit: Optional[float] = None,
    min_memory_limit: Optional[str] = None,
    max_memory_limit: Optional[str] = None,
    overflow_policy: Optional[str] = None,
) -> ResolvedResourceAllocation:
    """
    Resolves and validates effective CPU and memory allocations for a pipeline run
    following the precedence hierarchy:
        per-run override -> pipeline-level default -> system default.

    - Explicit per-run overrides are validated against minimum operational floors and
      administrator hard maximum caps (enforcing 'reject' or 'clamp' overflow policy).
    - Fallback defaults (pipeline default or system default) that exceed the currently
      active administrator hard maximum cap are automatically clamped to the hard cap (FR-008).
    """
    sys_cpu = float(
        system_default_cpu_limit
        if system_default_cpu_limit is not None
        else os.getenv("DOCKER_RUNNER_CPU_LIMIT", str(settings.docker_runner_cpu_limit))
    )
    sys_mem = str(
        system_default_memory_limit
        if system_default_memory_limit is not None
        else os.getenv("DOCKER_RUNNER_MEMORY_LIMIT", settings.docker_runner_memory_limit)
    )
    min_cpu = float(
        min_cpu_limit
        if min_cpu_limit is not None
        else os.getenv("DOCKER_RUNNER_MIN_CPU_LIMIT", str(settings.docker_runner_min_cpu_limit))
    )
    max_cpu = float(
        max_cpu_limit
        if max_cpu_limit is not None
        else os.getenv("DOCKER_RUNNER_MAX_CPU_LIMIT", str(settings.docker_runner_max_cpu_limit))
    )
    min_mem = str(
        min_memory_limit
        if min_memory_limit is not None
        else os.getenv("DOCKER_RUNNER_MIN_MEMORY_LIMIT", settings.docker_runner_min_memory_limit)
    )
    max_mem = str(
        max_memory_limit
        if max_memory_limit is not None
        else os.getenv("DOCKER_RUNNER_MAX_MEMORY_LIMIT", settings.docker_runner_max_memory_limit)
    )
    policy = str(
        overflow_policy
        if overflow_policy is not None
        else os.getenv("DOCKER_RUNNER_RESOURCE_OVERFLOW_POLICY", settings.docker_runner_resource_overflow_policy)
    ).lower()

    # 1. Resolve CPU candidate & source
    if requested_cpu_limit is not None:
        cpu_candidate = requested_cpu_limit
        cpu_source = "run_override"
        cpu_explicit = True
    elif pipeline_default_cpu_limit is not None:
        cpu_candidate = pipeline_default_cpu_limit
        cpu_source = "pipeline_default"
        cpu_explicit = False
    else:
        cpu_candidate = sys_cpu
        cpu_source = "system_default"
        cpu_explicit = False

    effective_cpu, cpu_clamped = _validate_cpu_value(
        cpu_val=cpu_candidate,
        min_cpu=min_cpu,
        max_cpu=max_cpu,
        overflow_policy=policy,
        is_explicit_request=cpu_explicit,
    )

    # 2. Resolve Memory candidate & source
    if requested_memory_limit is not None:
        mem_candidate = requested_memory_limit
        mem_source = "run_override"
        mem_explicit = True
    elif pipeline_default_memory_limit is not None:
        mem_candidate = pipeline_default_memory_limit
        mem_source = "pipeline_default"
        mem_explicit = False
    else:
        mem_candidate = sys_mem
        mem_source = "system_default"
        mem_explicit = False

    effective_mem, effective_mem_bytes, mem_clamped = _validate_memory_value(
        mem_val=mem_candidate,
        min_mem_str=min_mem,
        max_mem_str=max_mem,
        overflow_policy=policy,
        is_explicit_request=mem_explicit,
    )

    return ResolvedResourceAllocation(
        effective_cpu_limit=effective_cpu,
        effective_memory_limit=effective_mem,
        effective_memory_bytes=effective_mem_bytes,
        requested_cpu_limit=requested_cpu_limit,
        requested_memory_limit=requested_memory_limit,
        cpu_source=cpu_source,
        memory_source=mem_source,
        cpu_clamped=cpu_clamped,
        memory_clamped=mem_clamped,
    )
