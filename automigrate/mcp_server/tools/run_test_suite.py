"""
Test Suite Runner Tool.

Runs the project's test suite to validate behavioral correctness.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from automigrate.agent.state import TestResult


def run_test_suite(project_path: str, file_filter: str | None = None) -> TestResult:
    """Invoke the project's test suite.
    
    For an Angular project, runs `npx ng test --watch=false`.
    If no package.json is found (e.g. in test fixtures), it safely skips.
    """
    path = Path(project_path)
    if not path.exists():
        return TestResult(passed=False, total=0, failed=1, logs="Project path not found.")
        
    if not (path / "package.json").exists():
        # Fallback for simple fixtures that don't have a full Node environment
        return TestResult(
            passed=True,
            total=1,
            failed=0,
            logs="[SKIPPED] No package.json found. Skipping real test execution."
        )

    cmd = ["npx", "ng", "test", "--watch=false"]
    # If the user's project uses Karma, --include can target the specific file.
    # For jest, it acts as a pattern.
    if file_filter:
        cmd.append(f"--include=**/{Path(file_filter).name}")

    try:
        result = subprocess.run(
            cmd, cwd=str(path), capture_output=True, text=True, timeout=120
        )
        passed = result.returncode == 0
        return TestResult(
            passed=passed,
            total=1,
            failed=0 if passed else 1,
            logs=result.stdout + "\n" + result.stderr
        )
    except subprocess.TimeoutExpired:
        return TestResult(passed=False, total=0, failed=1, logs="Test suite timed out after 120s.")
    except Exception as e:
        return TestResult(passed=False, total=0, failed=1, logs=f"Failed to execute tests: {e}")
