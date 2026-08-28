"""
React Framework Adapter.

Supports migrations:
  - class_to_hooks: Convert React class components → functional components with Hooks
  - cra_to_vite:    Migrate Create React App → Vite
  - router_v5_to_v6: React Router v5 → v6

Detection: looks for "react" in package.json dependencies.

Current status:
  - class_to_hooks: LLM-only path (no deterministic rules yet). The LLM is
    guided by high-quality few-shot examples and bundled migration docs.
  - Other migrations: scaffold only (docs + prompt, no rules).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from automigrate.adapters.base import FrameworkAdapter, MigrationDescriptor
from automigrate.transforms.base_rules import RuleRegistry

_DOCS_DIR = Path(__file__).parent / "docs"


def _load_doc(filename: str) -> str:
    path = _DOCS_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


class ReactAdapter(FrameworkAdapter):
    """Adapter for React framework migrations."""

    name = "react"
    display_name = "React"

    # ── Detection ────────────────────────────────────────────────────────────

    @classmethod
    def detect(cls, project_path: str) -> bool:
        """True if package.json contains 'react' as a dependency."""
        pkg = Path(project_path) / "package.json"
        data = cls._read_json(pkg)
        if data is None:
            return False
        all_deps = {
            **data.get("dependencies", {}),
            **data.get("devDependencies", {}),
        }
        # Exclude Angular projects that happen to have react-related packages
        if "@angular/core" in all_deps:
            return False
        return "react" in all_deps

    # ── Migrations catalogue ─────────────────────────────────────────────────

    def get_migrations(self) -> list[MigrationDescriptor]:
        return [
            MigrationDescriptor(
                id="class_to_hooks",
                display_name="Class Components → Hooks",
                description=(
                    "Convert React class components to functional components "
                    "using React Hooks (useState, useEffect, useRef, etc.)"
                ),
                default=True,
            ),
            MigrationDescriptor(
                id="cra_to_vite",
                display_name="Create React App → Vite",
                description=(
                    "Migrate a Create React App project to Vite for faster "
                    "builds and modern tooling"
                ),
            ),
            MigrationDescriptor(
                id="router_v5_to_v6",
                display_name="React Router v5 → v6",
                description=(
                    "Migrate from React Router v5 API (Switch, useHistory, Redirect) "
                    "to React Router v6 API (Routes, useNavigate, Navigate)"
                ),
            ),
        ]

    # ── File scanning ─────────────────────────────────────────────────────────

    def get_file_patterns(self, migration_type: str) -> list[str]:
        if migration_type == "cra_to_vite":
            # CRA→Vite touches config files too
            return [".jsx", ".tsx", ".js", ".ts", ".json"]
        return [".jsx", ".tsx", ".js", ".ts"]

    def get_skip_dirs(self) -> set[str]:
        return {
            "node_modules",
            "dist",
            "build",
            ".git",
            "__pycache__",
            ".venv",
            "venv",
            "coverage",
            ".next",
            "out",
        }

    # ── Deterministic rules ───────────────────────────────────────────────────

    def get_rule_registry(self, migration_type: str) -> RuleRegistry:
        """No deterministic rules yet — all transformations use the LLM path.

        Future: add regex/AST rules for simple patterns like:
          - `this.state = { ... }` → useState
          - `componentDidMount` → useEffect(() => {...}, [])
        """
        return RuleRegistry(rules=[])

    # ── RAG docs ─────────────────────────────────────────────────────────────

    def get_migration_docs(self, migration_type: str) -> str:
        doc_map = {
            "class_to_hooks": "class_to_hooks.md",
            "cra_to_vite": "cra_to_vite.md",
            "router_v5_to_v6": "router_v5_to_v6.md",
        }
        filename = doc_map.get(migration_type, f"{migration_type}.md")
        doc = _load_doc(filename)
        if not doc:
            return f"# React {migration_type} Migration\n\nNo bundled docs found."
        return doc

    # ── LLM prompts ───────────────────────────────────────────────────────────

    def get_llm_system_prompt(self, migration_type: str) -> str:
        if migration_type == "class_to_hooks":
            return (
                "You are an expert React developer specialising in modernising React codebases.\n"
                "Convert the provided React class component to an equivalent functional "
                "component using React Hooks.\n\n"
                "CRITICAL RULES:\n"
                "1. Convert ALL lifecycle methods to the correct Hook equivalents.\n"
                "2. Convert `this.state` → `useState`. Each state field becomes its own hook.\n"
                "3. Convert `this.props` → destructured function parameters.\n"
                "4. Remove the class and extend React.Component / PureComponent.\n"
                "5. Keep all business logic and JSX identical — only the structure changes.\n"
                "6. Preserve all TypeScript types/interfaces.\n"
                "7. Reply ONLY with the rewritten code. Do NOT wrap in markdown code fences.\n\n"
                "DOCS:\n{context}"
            )
        if migration_type == "router_v5_to_v6":
            return (
                "You are an expert React developer. Migrate the provided code from "
                "React Router v5 to React Router v6.\n\n"
                "CRITICAL RULES:\n"
                "1. Replace <Switch> with <Routes>.\n"
                "2. Replace useHistory() with useNavigate().\n"
                "3. Replace <Redirect> with <Navigate>.\n"
                "4. Update route path matching (exact is now the default in v6).\n"
                "5. Reply ONLY with the rewritten code.\n\n"
                "DOCS:\n{context}"
            )
        return (
            "You are an expert React developer. Apply the requested migration "
            "based on the provided documentation.\n\n"
            "Reply ONLY with the rewritten code. Do NOT wrap in markdown code fences.\n\n"
            "DOCS:\n{context}"
        )

    def get_llm_examples(self, migration_type: str) -> list[tuple[str, str]]:
        if migration_type == "class_to_hooks":
            return [
                (
                    (
                        "Migrate this component:\n"
                        "import React, { Component } from 'react';\n\n"
                        "class Counter extends Component {\n"
                        "  constructor(props) {\n"
                        "    super(props);\n"
                        "    this.state = { count: 0 };\n"
                        "  }\n\n"
                        "  componentDidMount() {\n"
                        "    document.title = `Count: ${this.state.count}`;\n"
                        "  }\n\n"
                        "  render() {\n"
                        "    return (\n"
                        "      <button onClick={() => this.setState({ count: this.state.count + 1 })}>\n"
                        "        {this.state.count}\n"
                        "      </button>\n"
                        "    );\n"
                        "  }\n"
                        "}"
                    ),
                    (
                        "import React, { useState, useEffect } from 'react';\n\n"
                        "function Counter() {\n"
                        "  const [count, setCount] = useState(0);\n\n"
                        "  useEffect(() => {\n"
                        "    document.title = `Count: ${count}`;\n"
                        "  }, [count]);\n\n"
                        "  return (\n"
                        "    <button onClick={() => setCount(count + 1)}>\n"
                        "      {count}\n"
                        "    </button>\n"
                        "  );\n"
                        "}"
                    ),
                )
            ]
        return []

    # ── Failure recovery hints ────────────────────────────────────────────────

    def get_failure_hints(self, migration_type: str) -> dict[str, str]:
        if migration_type == "class_to_hooks":
            return {
                "syntax_failure": (
                    "Check that all JSX is valid. Ensure the functional component "
                    "returns exactly one root element. No `this` keyword should appear."
                ),
                "type_error": (
                    "Check TypeScript interfaces and prop types. The functional component "
                    "props should be typed as: `function Comp(props: PropType)` or destructured."
                ),
                "lint_error": (
                    "Ensure all hooks are called at the top level of the component, "
                    "not inside conditionals or loops. Check for missing dependencies in useEffect."
                ),
                "test_failure": (
                    "The converted component broke a test. Verify that all event handlers "
                    "and side effects are preserved. Check if the component needs forwardRef."
                ),
                "secrets_detected": (
                    "Do not include any API keys, tokens, or credentials in the output."
                ),
                "unknown": "Review the converted component carefully for correctness.",
            }
        return {
            "syntax_failure": "Check JSX syntax carefully.",
            "test_failure": "Preserve all existing behaviour and prop handling.",
            "unknown": "Review the migration carefully.",
        }

    # ── Testing ───────────────────────────────────────────────────────────────

    def get_test_command(self, project_path: str) -> list[str] | None:
        pkg = Path(project_path) / "package.json"
        data = self._read_json(pkg)
        if data is None:
            return None
        scripts = data.get("scripts", {})
        if "test" in scripts:
            # If using Jest (CRA default), add --watchAll=false
            test_script = scripts["test"]
            if "jest" in test_script or "react-scripts" in test_script:
                return ["npm", "test", "--", "--watchAll=false"]
            return ["npm", "test"]
        return None

    # ── Static validators ─────────────────────────────────────────────────────

    def get_static_validators(self, migration_type: str) -> list[Callable]:
        """TypeScript check + ESLint for React projects."""
        validators = []

        def _tsc_validator(file_path: str, content: str, project_path: str):
            from automigrate.agent.state import ValidationResult
            import subprocess

            tsconfig = Path(project_path) / "tsconfig.json"
            if not tsconfig.exists():
                return ValidationResult(
                    passed=True, stage="TypeCheck",
                    errors=["[SKIPPED] No tsconfig.json"],
                )
            try:
                res = subprocess.run(
                    ["npx", "tsc", "--noEmit"],
                    cwd=project_path, capture_output=True, text=True, timeout=60,
                )
                return ValidationResult(
                    passed=res.returncode == 0, stage="TypeCheck",
                    errors=[res.stdout + res.stderr] if res.returncode != 0 else [],
                )
            except Exception as e:
                return ValidationResult(passed=False, stage="TypeCheck", errors=[str(e)])

        validators.append(_tsc_validator)
        return validators
