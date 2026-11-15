# Quickstart Validation Guide: Decouple Test Mocks from Production Codebase

**Feature**: `006-remove-production-mocks`  
**Date**: 2026-10-20  

This guide provides step-by-step verification procedures to validate that test mocks, embedded simulation engines, and test flags have been cleanly removed from the production codebase and isolated in `tests/`.

---

## Prerequisites

- Python 3.12+ virtual environment activated.
- Project dependencies installed: `pip install -e .` or `pip install -r requirements.txt`.
- No active Docker daemon, Memgraph, or Gemini API key required for offline test suite verification.

---

## Validation Scenarios

### Scenario 1: Verify Zero `mock_mode` References in `src/`

Confirm that no production file under `src/` contains `mock_mode` or simulation fallback methods.

```bash
# 1. Search for mock_mode in production code (MUST return 0 lines)
grep -rn "mock_mode" src/ || echo "PASS: No mock_mode in src/"

# 2. Search for _run_simulated_loop in production code (MUST return 0 lines)
grep -rn "_run_simulated_loop" src/ || echo "PASS: No _run_simulated_loop in src/"

# 3. Confirm simulate_telemetry.py has been removed from src/scripts/
test ! -f src/scripts/simulate_telemetry.py && echo "PASS: simulate_telemetry.py removed from src/scripts/"
```

**Expected Outcome**:
All checks print `PASS` with zero matches found in `src/`.

---

### Scenario 2: Validate Explicit Domain Exception on Missing Configuration

Verify that initializing `DynamicAgentLoop` or `GenAIService` without a valid API key raises `ConfigurationError` instead of falling back to offline simulation.

```bash
python3 -c "
import pytest
from src.domains.ai.operations.dynamic_loop import DynamicAgentLoop
from src.core.exceptions import ConfigurationError

try:
    loop = DynamicAgentLoop(api_key='')
    print('FAIL: Expected ConfigurationError was not raised')
except ConfigurationError:
    print('PASS: ConfigurationError raised successfully on missing key')
except Exception as e:
    print(f'FAIL: Unexpected exception: {type(e).__name__}: {e}')
"
```

**Expected Outcome**:
Prints `PASS: ConfigurationError raised successfully on missing key`.

---

### Scenario 3: Validate Explicit Domain Exception on Unreachable Memgraph

Verify that connecting `MemgraphClient` to an unreachable port raises `ConnectionError` instead of falling back to `mock_mode`.

```bash
python3 -c "
from src.services.graph.memgraph_client import MemgraphClient
from src.core.exceptions import ConnectionError

try:
    client = MemgraphClient(host='127.0.0.1', port=65530)
    print('FAIL: Expected ConnectionError was not raised')
except ConnectionError:
    print('PASS: ConnectionError raised successfully on unreachable Memgraph')
except Exception as e:
    print(f'FAIL: Unexpected exception: {type(e).__name__}: {e}')
"
```

**Expected Outcome**:
Prints `PASS: ConnectionError raised successfully on unreachable Memgraph`.

---

### Scenario 4: Run Full Offline Automated Test Suite

Verify that all existing unit, integration, and contract test suites execute and pass cleanly using test-side mock fixtures from `tests/fixtures/mocks/`.

```bash
pytest tests/ -v
```

**Expected Outcome**:
All tests pass without failures, with zero regressions in functional test coverage.

---

### Scenario 5: Run Relocated Telemetry Simulator from `tools/`

Verify that the telemetry load generator runs as an external tool without embedded fake fallbacks.

```bash
# Verify file exists under tools/
test -f tools/simulate_telemetry.py && echo "PASS: Generator tool exists under tools/"

# Run with --help to verify argument parsing
python3 tools/simulate_telemetry.py --help
```

**Expected Outcome**:
Prints tool help options; verifies clean separation from production package.
