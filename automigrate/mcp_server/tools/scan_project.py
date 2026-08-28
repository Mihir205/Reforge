"""
scan_project — MCP tool that walks a codebase and classifies migration targets.

Framework-agnostic: delegates file pattern selection and rule classification
to the active FrameworkAdapter.

Output: A list of ScanResult objects, one per detected pattern instance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from automigrate.transforms.base_rules import RuleRegistry

# Directories to always skip (baseline; adapters may add more)
_DEFAULT_SKIP_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
}


@dataclass
class ScanResult:
    """A single detected migration pattern in a file."""

    file_path: str
    line: int
    column: int
    pattern_id: str
    classification: str  # "deterministic" | "ambiguous"
    complexity: str  # "simple" | "medium" | "complex" | "ambiguous"
    snippet: str  # first 120 chars of the matched region

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "pattern_id": self.pattern_id,
            "classification": self.classification,
            "complexity": self.complexity,
            "snippet": self.snippet,
        }


@dataclass
class ProjectScanOutput:
    """Aggregated output from scanning a project."""

    project_path: str
    migration_type: str
    framework: str
    total_files_scanned: int
    total_patterns_found: int
    deterministic_count: int
    ambiguous_count: int
    results: list[ScanResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_path": self.project_path,
            "migration_type": self.migration_type,
            "framework": self.framework,
            "total_files_scanned": self.total_files_scanned,
            "total_patterns_found": self.total_patterns_found,
            "deterministic_count": self.deterministic_count,
            "ambiguous_count": self.ambiguous_count,
            "results": [r.to_dict() for r in self.results],
        }


def scan_project(
    project_path: str,
    migration_type: str = "angular_control_flow",
    framework: str | None = None,
    rule_registry: RuleRegistry | None = None,
) -> ProjectScanOutput:
    """Scan a project directory for migration targets.

    Args:
        project_path:   Absolute or relative path to the project root.
        migration_type: Which migration to scan for. Legacy form accepted
                        (e.g., "angular_control_flow" is mapped to
                        framework="angular", migration_type="control_flow").
        framework:      Explicit framework name. If None, auto-detected or
                        inferred from migration_type.
        rule_registry:  Optional custom RuleRegistry (overrides adapter lookup).

    Returns:
        A ProjectScanOutput with all detected patterns classified.
    """
    project = Path(project_path).resolve()

    if not project.is_dir():
        raise FileNotFoundError(f"Project path does not exist: {project}")

    # ── Resolve framework + migration_type ─────────────────────────────────────
    # Support legacy "angular_control_flow" style migration_type strings.
    resolved_framework, resolved_migration = _resolve_migration(
        migration_type, framework, project_path
    )

    # ── Load adapter ──────────────────────────────────────────────────────────
    from automigrate.adapters.registry import get_adapter, detect_framework

    if rule_registry is None:
        try:
            adapter = get_adapter(resolved_framework)
        except ValueError:
            adapter = detect_framework(str(project))
            if adapter is None:
                raise ValueError(
                    f"Could not detect or load framework adapter for "
                    f"framework={resolved_framework!r}."
                )

        file_patterns = adapter.get_file_patterns(resolved_migration)
        skip_dirs = _DEFAULT_SKIP_DIRS | adapter.get_skip_dirs()
        reg = adapter.get_rule_registry(resolved_migration)
    else:
        # Legacy path: caller provides registry directly (used in tests)
        file_patterns = _legacy_file_patterns(migration_type)
        skip_dirs = _DEFAULT_SKIP_DIRS
        reg = rule_registry

    # ── Walk the project ──────────────────────────────────────────────────────
    results: list[ScanResult] = []
    files_scanned = 0

    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for filename in files:
            if not any(filename.endswith(ext) for ext in file_patterns):
                continue

            filepath = Path(root) / filename
            files_scanned += 1

            try:
                source = filepath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            for cls in reg.classify(source):
                results.append(
                    ScanResult(
                        file_path=str(filepath.relative_to(project)),
                        line=cls["line"],
                        column=cls["column"],
                        pattern_id=cls["pattern_id"],
                        classification=cls["classification"],
                        complexity=cls["complexity"],
                        snippet=cls["snippet"],
                    )
                )

    deterministic_count = sum(1 for r in results if r.classification == "deterministic")
    ambiguous_count = sum(1 for r in results if r.classification == "ambiguous")

    return ProjectScanOutput(
        project_path=str(project),
        migration_type=resolved_migration,
        framework=resolved_framework,
        total_files_scanned=files_scanned,
        total_patterns_found=len(results),
        deterministic_count=deterministic_count,
        ambiguous_count=ambiguous_count,
        results=results,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_migration(
    migration_type: str, framework: str | None, project_path: str
) -> tuple[str, str]:
    """Resolve (framework, migration_type) from various input forms.

    Handles:
      - Legacy form: "angular_control_flow" → ("angular", "control_flow")
      - Explicit: framework="angular", migration_type="control_flow"
      - Auto-detect: if framework is None and migration_type is plain ("control_flow")
    """
    # Legacy underscore-compound form (e.g. "angular_control_flow")
    known_prefixes = ["angular", "react", "vue", "nextjs", "python"]
    for prefix in known_prefixes:
        if migration_type.startswith(prefix + "_"):
            resolved_fw = prefix
            resolved_mt = migration_type[len(prefix) + 1:]
            return resolved_fw, resolved_mt

    # Explicit framework provided
    if framework:
        return framework, migration_type

    # Auto-detect from project files
    from automigrate.adapters.registry import detect_framework
    adapter = detect_framework(project_path)
    if adapter:
        return adapter.name, migration_type

    # Last resort: assume angular (backwards compat)
    return "angular", migration_type


def _legacy_file_patterns(migration_type: str) -> list[str]:
    """Return file patterns for old migration_type strings (backwards compat)."""
    if "angular" in migration_type:
        return [".html"]
    if "react" in migration_type:
        return [".jsx", ".tsx", ".js", ".ts"]
    return [".html", ".ts", ".js"]
