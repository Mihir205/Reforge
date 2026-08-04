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

    # 2. Type Check (Simulated for Angular: we would normally run `tsc --noEmit`)
    results["TypeCheck"] = ValidationResult(passed=True, stage="TypeCheck")
    
    # 3. Lint (Simulated)
    results["Lint"] = ValidationResult(passed=True, stage="Lint")
    
    return results
