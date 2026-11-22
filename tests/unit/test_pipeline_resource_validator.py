import pytest
from src.domains.pipeline.operations.resource_validator import (
    parse_memory_bytes,
    format_memory_limit,
    normalize_memory_string,
    validate_pipeline_default_resources,
    resolve_run_resources,
)


def test_parse_memory_bytes_valid_units():
    assert parse_memory_bytes("1024b") == 1024
    assert parse_memory_bytes("512k") == 512 * 1024
    assert parse_memory_bytes("512KB") == 512 * 1024
    assert parse_memory_bytes("64m") == 64 * 1024 * 1024
    assert parse_memory_bytes("512MB") == 512 * 1024 * 1024
    assert parse_memory_bytes("2048m") == 2 * 1024 ** 3
    assert parse_memory_bytes("2g") == 2 * 1024 ** 3
    assert parse_memory_bytes("2GB") == 2 * 1024 ** 3
    assert parse_memory_bytes("0.5g") == 512 * 1024 * 1024
    assert parse_memory_bytes(134217728) == 134217728


def test_parse_memory_bytes_invalid_inputs():
    for invalid in ["", "   ", "-512m", "0m", "0", "-100", "2t", "2tb", "512x", "abc", None, True]:
        with pytest.raises(ValueError):
            parse_memory_bytes(invalid)


def test_format_and_normalize_memory_string():
    assert format_memory_limit(2 * 1024 ** 3) == "2g"
    assert format_memory_limit(512 * 1024 ** 2) == "512m"
    norm_str, byte_count = normalize_memory_string("2048MB")
    assert norm_str == "2048m"
    assert byte_count == 2 * 1024 ** 3


def test_resolve_run_resources_precedence_hierarchy():
    # 1. System default fallback when both pipeline default and run override are None
    res_sys = resolve_run_resources(
        system_default_cpu_limit=2.0,
        system_default_memory_limit="2g",
        max_cpu_limit=4.0,
        max_memory_limit="4g",
    )
    assert res_sys.effective_cpu_limit == 2.0
    assert res_sys.effective_memory_limit == "2g"
    assert res_sys.cpu_source == "system_default"
    assert res_sys.memory_source == "system_default"
    assert res_sys.resource_clamped is False

    # 2. Pipeline default fallback when run override is None
    res_pipe = resolve_run_resources(
        pipeline_default_cpu_limit=1.5,
        pipeline_default_memory_limit="1g",
        system_default_cpu_limit=2.0,
        system_default_memory_limit="2g",
        max_cpu_limit=4.0,
        max_memory_limit="4g",
    )
    assert res_pipe.effective_cpu_limit == 1.5
    assert res_pipe.effective_memory_limit == "1g"
    assert res_pipe.cpu_source == "pipeline_default"
    assert res_pipe.memory_source == "pipeline_default"
    assert res_pipe.resource_clamped is False

    # 3. Partial run override (CPU specified on run, memory inherited from pipeline default)
    res_partial = resolve_run_resources(
        requested_cpu_limit=3.0,
        requested_memory_limit=None,
        pipeline_default_cpu_limit=1.5,
        pipeline_default_memory_limit="1536m",
        system_default_cpu_limit=2.0,
        system_default_memory_limit="2g",
        max_cpu_limit=4.0,
        max_memory_limit="4g",
    )
    assert res_partial.effective_cpu_limit == 3.0
    assert res_partial.effective_memory_limit == "1536m"
    assert res_partial.cpu_source == "run_override"
    assert res_partial.memory_source == "pipeline_default"

    # 4. Full run override
    res_override = resolve_run_resources(
        requested_cpu_limit=3.5,
        requested_memory_limit="3g",
        pipeline_default_cpu_limit=1.5,
        pipeline_default_memory_limit="1g",
        system_default_cpu_limit=2.0,
        system_default_memory_limit="2g",
        max_cpu_limit=4.0,
        max_memory_limit="4g",
    )
    assert res_override.effective_cpu_limit == 3.5
    assert res_override.effective_memory_limit == "3g"
    assert res_override.cpu_source == "run_override"
    assert res_override.memory_source == "run_override"


def test_minimum_operational_floors_always_rejected():
    # Below CPU floor (0.1) or memory floor (64m) must reject even if policy == "clamp"
    for policy in ["reject", "clamp"]:
        with pytest.raises(ValueError, match="minimum operational floor"):
            resolve_run_resources(requested_cpu_limit=0.05, overflow_policy=policy)

        with pytest.raises(ValueError, match="minimum operational floor"):
            resolve_run_resources(requested_memory_limit="32m", overflow_policy=policy)

        with pytest.raises(ValueError, match="greater than zero"):
            resolve_run_resources(requested_cpu_limit=-1.0, overflow_policy=policy)


def test_hard_cap_enforcement_reject_vs_clamp():
    # Reject policy (default)
    with pytest.raises(ValueError, match="exceeds administrator hard maximum cap"):
        resolve_run_resources(
            requested_cpu_limit=6.0,
            max_cpu_limit=4.0,
            overflow_policy="reject",
        )

    with pytest.raises(ValueError, match="exceeds administrator hard maximum cap"):
        resolve_run_resources(
            requested_memory_limit="4500m",
            max_memory_limit="4g",
            overflow_policy="reject",
        )

    # Clamp policy
    clamped = resolve_run_resources(
        requested_cpu_limit=8.0,
        requested_memory_limit="8g",
        max_cpu_limit=4.0,
        max_memory_limit="4g",
        overflow_policy="clamp",
    )
    assert clamped.effective_cpu_limit == 4.0
    assert clamped.effective_memory_limit == "4g"
    assert clamped.requested_cpu_limit == 8.0
    assert clamped.requested_memory_limit == "8g"
    assert clamped.cpu_clamped is True
    assert clamped.memory_clamped is True
    assert clamped.resource_clamped is True


def test_lowered_hard_cap_clamps_fallback_defaults_automatically():
    # FR-008: If admin lowers hard cap below system default or saved pipeline default,
    # fallback resolution clamps to the active hard cap even under 'reject' policy.
    res = resolve_run_resources(
        requested_cpu_limit=None,
        requested_memory_limit=None,
        pipeline_default_cpu_limit=3.0,
        pipeline_default_memory_limit="3g",
        system_default_cpu_limit=2.0,
        system_default_memory_limit="2g",
        max_cpu_limit=1.5,
        max_memory_limit="1g",
        overflow_policy="reject",
    )
    assert res.effective_cpu_limit == 1.5
    assert res.effective_memory_limit == "1g"
    assert res.resource_clamped is True


def test_validate_pipeline_default_resources():
    cpu, mem = validate_pipeline_default_resources(
        default_cpu_limit=1.5,
        default_memory_limit="1024MB",
        max_cpu_limit=4.0,
        max_memory_limit="4g",
        overflow_policy="reject",
    )
    assert cpu == 1.5
    assert mem == "1024m"

    with pytest.raises(ValueError, match="exceeds administrator hard maximum cap"):
        validate_pipeline_default_resources(
            default_cpu_limit=5.0,
            max_cpu_limit=4.0,
            overflow_policy="reject",
        )
