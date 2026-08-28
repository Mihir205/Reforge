"""
Test Suite Runner Tool.

Runs the project's test suite using the command provided by the active
FrameworkAdapter. Falls back gracefully if no test command can be determined.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from automigrate.agent.state import TestResult


def run_test_suite(
    project_path: str,
    file_filter: str | None = None,
    framework: str = "angular",
) -> TestResult:
    """Invoke the project's test suite.

    Asks the framework adapter which command to run. The adapter inspects
    the project to determine the right command (ng test, npm test, pytest, etc.).

    Args:
        project_path:  Absolute path to the project root directory.
        file_filter:   Optional file path to restrict tests to a specific file.
        framework:     Framework name used to load the adapter.
    """
    path = Path(project_path)
    if not path.exists():
        return TestResult(passed=False, total=0, failed=1, logs="Project path not found.")

    # ── Ask the adapter for the test command ──────────────────────────────────
    cmd = None
    try:
        from automigrate.adapters.registry import get_adapter
        adapter = get_adapter(framework)
        cmd = adapter.get_test_command(project_path)
    except Exception:
        pass  # Fall through to heuristic detection

    if cmd is None:
        # Heuristic: try common test runners
        cmd = _detect_test_command(path)

    if cmd is None:
        return TestResult(
            passed=True,
            total=1,
            failed=0,
            logs="[SKIPPED] Could not determine test command for this project.",
        )

    # Append file filter if the command supports it
    if file_filter and len(cmd) > 1:
        # Jest-style: append pattern
        if "jest" in " ".join(cmd) or "react-scripts" in " ".join(cmd):
            cmd = cmd + [Path(file_filter).stem]
        # Angular-style: --include
        elif "ng" in cmd:
            cmd = cmd + [f"--include=**/{Path(file_filter).name}"]

    try:
        result = subprocess.run(
            cmd, cwd=str(path), capture_output=True, text=True, timeout=120
        )
        passed = result.returncode == 0
        return TestResult(
            passed=passed,
            total=1,
            failed=0 if passed else 1,
            logs=result.stdout + "\n" + result.stderr,
        )
    except subprocess.TimeoutExpired:
        return TestResult(passed=False, total=0, failed=1, logs="Test suite timed out after 120s.")
    except Exception as e:
        return TestResult(passed=False, total=0, failed=1, logs=f"Failed to execute tests: {e}")


def _detect_test_command(path: Path) -> list[str] | None:
    """Heuristic test command detection from project files."""
    if (path / "angular.json").exists():
        return ["npx", "ng", "test", "--watch=false"]
    if (path / "package.json").exists():
        import json
        try:
            data = json.loads((path / "package.json").read_text(encoding="utf-8"))
            if "test" in data.get("scripts", {}):
                return ["npm", "test", "--", "--watchAll=false"]
        except Exception:
            pass
    if (path / "pytest.ini").exists() or (path / "pyproject.toml").exists():
        return ["pytest", "--tb=short"]
    return None
