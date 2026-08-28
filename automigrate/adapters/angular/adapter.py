"""
Angular Framework Adapter.

Encapsulates all Angular-specific knowledge for the Reforge migration pipeline:
- Supported migrations (control flow, standalone components, signals, …)
- File patterns, skip dirs
- Deterministic transform rules
- Migration documentation (for RAG context)
- LLM system prompts and few-shot examples
- Failure recovery hints
- Static validators (tsc, eslint)
- Test command (ng test)

Detection: looks for @angular/core in package.json dependencies.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from automigrate.adapters.base import FrameworkAdapter, MigrationDescriptor
from automigrate.transforms.base_rules import RuleRegistry

# ── Angular-specific rule registry (wraps existing rules.py) ──────────────────
from automigrate.transforms.angular_control_flow.rules import registry as _angular_registry


# ---------------------------------------------------------------------------
# Docs bundles (one Markdown string per migration type)
# ---------------------------------------------------------------------------

_DOCS_DIR = Path(__file__).parent / "docs"


def _load_doc(filename: str) -> str:
    """Load a bundled documentation file, returning empty string if missing."""
    path = _DOCS_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# Angular Adapter
# ---------------------------------------------------------------------------


class AngularAdapter(FrameworkAdapter):
    """Adapter for Angular framework migrations."""

    name = "angular"
    display_name = "Angular"

    # ── Detection ────────────────────────────────────────────────────────────

    @classmethod
    def detect(cls, project_path: str) -> bool:
        """True if package.json lists @angular/core as a dependency."""
        pkg = Path(project_path) / "package.json"
        data = cls._read_json(pkg)
        if data is None:
            return False
        all_deps = {
            **data.get("dependencies", {}),
            **data.get("devDependencies", {}),
        }
        return "@angular/core" in all_deps

    # ── Migrations catalogue ─────────────────────────────────────────────────

    def get_migrations(self) -> list[MigrationDescriptor]:
        return [
            MigrationDescriptor(
                id="control_flow",
                display_name="Control Flow Syntax",
                description=(
                    "Migrate *ngIf / *ngFor / *ngSwitch to the new "
                    "@if / @for / @switch syntax (Angular 17+)"
                ),
                default=True,
            ),
            MigrationDescriptor(
                id="standalone_components",
                display_name="Standalone Components",
                description=(
                    "Convert NgModule-based components to standalone components "
                    "with explicit imports (Angular 15+)"
                ),
            ),
        ]

    # ── File scanning ─────────────────────────────────────────────────────────

    def get_file_patterns(self, migration_type: str) -> list[str]:
        if migration_type == "control_flow":
            return [".html"]
        if migration_type == "standalone_components":
            return [".ts"]
        return [".html", ".ts"]

    def get_skip_dirs(self) -> set[str]:
        return {
            "node_modules",
            ".angular",
            "dist",
            ".git",
            "__pycache__",
            ".venv",
            "venv",
            "coverage",
            "e2e",
        }

    # ── Deterministic rules ───────────────────────────────────────────────────

    def get_rule_registry(self, migration_type: str) -> RuleRegistry:
        if migration_type == "control_flow":
            return _angular_registry
        # Other migrations don't have deterministic rules yet → all LLM
        return RuleRegistry(rules=[])

    # ── RAG docs ─────────────────────────────────────────────────────────────

    def get_migration_docs(self, migration_type: str) -> str:
        doc_map = {
            "control_flow": "control_flow.md",
            "standalone_components": "standalone_components.md",
        }
        filename = doc_map.get(migration_type, f"{migration_type}.md")
        doc = _load_doc(filename)
        if not doc:
            return f"# Angular {migration_type} Migration\n\nNo bundled docs found."
        return doc

    # ── LLM prompts ───────────────────────────────────────────────────────────

    def get_llm_system_prompt(self, migration_type: str) -> str:
        if migration_type == "control_flow":
            return (
                "You are an expert Angular developer. Migrate the provided Angular "
                "HTML template to the new Angular v17+ control flow syntax based on "
                "the provided documentation.\n\n"
                "CRITICAL RULES:\n"
                "1. NEVER put @if, @for, or @switch inside HTML tags as attributes.\n"
                "2. The control flow blocks MUST wrap HTML elements, not be inside them.\n"
                "3. Always include a `track` expression in @for blocks.\n"
                "4. Reply ONLY with the rewritten code. Do NOT wrap in markdown code fences.\n\n"
                "DOCS:\n{context}"
            )
        if migration_type == "standalone_components":
            return (
                "You are an expert Angular developer. Convert the provided Angular component "
                "from NgModule-based to standalone. Follow the Angular 15+ standalone API.\n\n"
                "CRITICAL RULES:\n"
                "1. Add `standalone: true` to the @Component decorator.\n"
                "2. Move all NgModule imports directly into the component's `imports` array.\n"
                "3. Remove NgModule references where the component is declared.\n"
                "4. Reply ONLY with the rewritten code. Do NOT wrap in markdown code fences.\n\n"
                "DOCS:\n{context}"
            )
        return (
            "You are an expert Angular developer. Apply the requested migration "
            "based on the provided documentation.\n\n"
            "Reply ONLY with the rewritten code.\n\n"
            "DOCS:\n{context}"
        )

    def get_llm_examples(self, migration_type: str) -> list[tuple[str, str]]:
        if migration_type == "control_flow":
            return [
                (
                    "Migrate this template:\n<div *ngIf=\"condition\">\n  <p>Hello</p>\n</div>",
                    "@if (condition) {\n  <div>\n    <p>Hello</p>\n  </div>\n}",
                ),
                (
                    (
                        "Migrate this template:\n<ul>\n"
                        "  <li *ngFor=\"let item of items; trackBy: trackItem\">\n"
                        "    {{item}}\n  </li>\n</ul>"
                    ),
                    (
                        "<ul>\n  @for (item of items; track trackItem($index, item)) {\n"
                        "    <li>\n      {{item}}\n    </li>\n  }\n</ul>"
                    ),
                ),
            ]
        return []

    # ── Failure recovery hints ────────────────────────────────────────────────

    def get_failure_hints(self, migration_type: str) -> dict[str, str]:
        if migration_type == "control_flow":
            return {
                "syntax_failure": (
                    "Ensure all @if / @for / @switch blocks have matching opening and "
                    "closing braces. Do not leave any *ngIf, *ngFor, or *ngSwitch "
                    "attributes in the output."
                ),
                "type_error": (
                    "Check that all variable bindings reference properties that exist on "
                    "the component class. Prefer using the `as` alias pattern inside @if "
                    "to ensure type narrowing."
                ),
                "lint_error": (
                    "Ensure consistent indentation (2 spaces), no trailing whitespace, "
                    "and no unused template variables."
                ),
                "secrets_detected": (
                    "STOP. Do not include any API keys, passwords, tokens, or placeholder "
                    "credentials in the output. Never reproduce secrets from context files."
                ),
                "test_failure": (
                    "The transformed template broke at least one behavioral test. "
                    "Carefully preserve all existing data bindings, event handlers, "
                    "and template variables."
                ),
                "unknown": (
                    "Review the full template carefully and ensure the migration is "
                    "complete and correct."
                ),
            }
        return {
            "syntax_failure": "Check syntax carefully after migration.",
            "test_failure": "Preserve all existing behavior and data bindings.",
            "unknown": "Review the full file carefully.",
        }

    # ── Testing ───────────────────────────────────────────────────────────────

    def get_test_command(self, project_path: str) -> list[str] | None:
        """Use `ng test` if angular.json exists, otherwise skip."""
        if (Path(project_path) / "angular.json").exists():
            return ["npx", "ng", "test", "--watch=false"]
        if (Path(project_path) / "package.json").exists():
            # Fallback to npm test (works with Jest-based Angular projects)
            return ["npm", "test", "--", "--watchAll=false"]
        return None

    # ── Static validators ─────────────────────────────────────────────────────

    def get_static_validators(self, migration_type: str) -> list[Callable]:
        """Return TypeScript + ESLint validators for Angular projects."""
        validators = []

        def _tsc_validator(file_path: str, content: str, project_path: str):
            """Run tsc --noEmit for TypeScript type checking."""
            from automigrate.agent.state import ValidationResult

            tsconfig = Path(project_path) / "tsconfig.json"
            if not tsconfig.exists():
                return ValidationResult(
                    passed=True,
                    stage="TypeCheck",
                    errors=["[SKIPPED] No tsconfig.json found"],
                )
            try:
                res = subprocess.run(
                    ["npx", "tsc", "--noEmit"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                passed = res.returncode == 0
                return ValidationResult(
                    passed=passed,
                    stage="TypeCheck",
                    errors=[res.stdout + "\n" + res.stderr] if not passed else [],
                )
            except Exception as e:
                return ValidationResult(passed=False, stage="TypeCheck", errors=[str(e)])

        def _eslint_validator(file_path: str, content: str, project_path: str):
            """Run eslint if config exists."""
            from automigrate.agent.state import ValidationResult

            eslint_config = Path(project_path) / ".eslintrc.json"
            if not eslint_config.exists():
                return ValidationResult(
                    passed=True,
                    stage="Lint",
                    errors=["[SKIPPED] No eslint config found"],
                )
            try:
                res = subprocess.run(
                    ["npx", "eslint", file_path],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                passed = res.returncode == 0
                return ValidationResult(
                    passed=passed,
                    stage="Lint",
                    errors=[res.stdout + "\n" + res.stderr] if not passed else [],
                )
            except Exception as e:
                return ValidationResult(passed=False, stage="Lint", errors=[str(e)])

        validators.extend([_tsc_validator, _eslint_validator])
        return validators
