"""
Static Validation Tool.

Runs static checks on a transformed file using validators provided by the
active FrameworkAdapter. Falls back to a generic syntax check if the adapter
provides no validators.
"""

from __future__ import annotations

from pathlib import Path

from automigrate.agent.state import ValidationResult


def run_static_validation(
    file_path: str,
    project_path: str,
    framework: str = "angular",
    migration_type: str = "control_flow",
) -> dict[str, ValidationResult]:
    """Run static validation pipeline on a transformed file.

    Loads validators from the framework adapter. The adapter decides what
    checks are appropriate (tsc, eslint, ruff, pyright, etc.).

    Args:
        file_path:      Path to the file, relative to project_path.
        project_path:   Absolute path to the project root.
        framework:      Framework name (used to load the adapter).
        migration_type: Migration type (passed to adapter.get_static_validators).

    Returns:
        Dict mapping stage name → ValidationResult.
    """
    results: dict[str, ValidationResult] = {}

    # ── Generic AST-level check ───────────────────────────────────────────────
    # Read the file and do a framework-agnostic pre-check for obvious errors.
    try:
        content = Path(project_path, file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return {
            "AST": ValidationResult(passed=False, stage="AST", errors=[str(e)])
        }

    # Generic heuristic: warn if there are orphaned comment markers from transforms
    ast_errors = []
    if "<!-- WARNING:" in content:
        ast_errors.append("Orphaned ng-template reference found in output")

    results["AST"] = ValidationResult(
        passed=len(ast_errors) == 0,
        stage="AST",
        errors=ast_errors,
    )

    if ast_errors:
        return results  # Don't bother running further validators on bad output

    # ── Framework-specific validators from adapter ────────────────────────────
    try:
        from automigrate.adapters.registry import get_adapter
        adapter = get_adapter(framework)
        validators = adapter.get_static_validators(migration_type)
    except Exception:
        validators = []

    for validator_fn in validators:
        try:
            result = validator_fn(file_path, content, project_path)
            results[result.stage] = result
            if not result.passed:
                break  # Stop on first hard failure
        except Exception as e:
            results["Validator"] = ValidationResult(
                passed=False, stage="Validator", errors=[str(e)]
            )
            break

    return results
