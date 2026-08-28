"""
Static Validation Tool.

Runs static checks on a transformed file: AST parse, Type Check, and Lint.
For Angular, we simulate these checks.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from automigrate.agent.state import ValidationResult


def run_static_validation(file_path: str, project_path: str) -> dict[str, ValidationResult]:
    """Run static validation pipeline on a file.
    
    In a real implementation, this would invoke `tsc` and `eslint`.
    For this project, we will simulate or use lightweight checks.
    """
    results = {}
    
    # 1. AST/Syntax Check (Simulated: check if it parses as valid HTML with new syntax)
    # We could use an HTML parser here, but for now we'll just check for obvious bad tags
    content = Path(project_path, file_path).read_text(encoding="utf-8")
    
    ast_passed = "<!-- WARNING:" not in content
    results["AST"] = ValidationResult(
        passed=ast_passed,
        stage="AST",
        errors=["Orphaned ng-template reference found"] if not ast_passed else []
    )
    
    if not ast_passed:
        return results

    # 2. Type Check (Run `tsc --noEmit` if tsconfig.json exists)
    tsconfig = Path(project_path) / "tsconfig.json"
    if tsconfig.exists():
        try:
            res = subprocess.run(
                ["npx", "tsc", "--noEmit"], 
                cwd=project_path, 
                capture_output=True, 
                text=True, 
                timeout=60
            )
            passed = res.returncode == 0
            errs = [res.stdout + "\n" + res.stderr] if not passed else []
            results["TypeCheck"] = ValidationResult(passed=passed, stage="TypeCheck", errors=errs)
        except Exception as e:
            results["TypeCheck"] = ValidationResult(passed=False, stage="TypeCheck", errors=[str(e)])
    else:
        results["TypeCheck"] = ValidationResult(passed=True, stage="TypeCheck", errors=["[SKIPPED] No tsconfig.json found"])
    
    # 3. Lint (Run `eslint` if eslintrc exists)
    eslint_config = Path(project_path) / ".eslintrc.json"
    if eslint_config.exists():
        try:
            res = subprocess.run(
                ["npx", "eslint", file_path], 
                cwd=project_path, 
                capture_output=True, 
                text=True, 
                timeout=60
            )
            passed = res.returncode == 0
            errs = [res.stdout + "\n" + res.stderr] if not passed else []
            results["Lint"] = ValidationResult(passed=passed, stage="Lint", errors=errs)
        except Exception as e:
            results["Lint"] = ValidationResult(passed=False, stage="Lint", errors=[str(e)])
    else:
        results["Lint"] = ValidationResult(passed=True, stage="Lint", errors=["[SKIPPED] No eslint config found"])
    
    return results
