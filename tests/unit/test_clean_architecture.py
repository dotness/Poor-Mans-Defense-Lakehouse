import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SRC_DIR = ROOT_DIR / "src"


def test_no_mock_mode_in_production():
    """Validates that zero occurrences of mock_mode exist in the src/ production codebase."""
    mock_mode_files = []
    pattern = re.compile(r"\bmock_mode\b")

    for py_file in SRC_DIR.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if pattern.search(content):
            mock_mode_files.append(str(py_file.relative_to(ROOT_DIR)))

    assert not mock_mode_files, f"Found mock_mode in production files: {mock_mode_files}"


def test_no_simulation_loops_in_production():
    """Validates that zero simulation loop methods exist in the src/ production codebase."""
    sim_files = []
    pattern = re.compile(r"_run_simulated_loop")

    for py_file in SRC_DIR.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if pattern.search(content):
            sim_files.append(str(py_file.relative_to(ROOT_DIR)))

    assert not sim_files, f"Found _run_simulated_loop in production files: {sim_files}"


def test_no_simulation_scripts_in_production_scripts():
    """Validates that simulate_telemetry.py was relocated out of src/scripts/."""
    assert not (SRC_DIR / "scripts" / "simulate_telemetry.py").exists(), (
        "src/scripts/simulate_telemetry.py must be relocated to tools/simulate_telemetry.py"
    )
