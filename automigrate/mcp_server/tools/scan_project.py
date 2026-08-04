"""
scan_project — MCP tool that walks a codebase and classifies migration targets.

Walks the project tree, finds files matching the migration type (e.g., Angular
HTML templates), parses them against the rule registry, and classifies each
match as either "deterministic" (a fixed rule exists) or "ambiguous" (needs
LLM fallback).

Output: A list of ScanResult objects, one per detected pattern instance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from automigrate.transforms.angular_control_flow.rules import RuleRegistry, registry


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
    total_files_scanned: int
    total_patterns_found: int
    deterministic_count: int
    ambiguous_count: int
    results: list[ScanResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_path": self.project_path,
            "migration_type": self.migration_type,
            "total_files_scanned": self.total_files_scanned,
            "total_patterns_found": self.total_patterns_found,
            "deterministic_count": self.deterministic_count,
            "ambiguous_count": self.ambiguous_count,
            "results": [r.to_dict() for r in self.results],
        }


# File extension mapping per migration type
_FILE_EXTENSIONS: dict[str, list[str]] = {
    "angular_control_flow": [".html", ".component.html"],
}

# Directories to always skip
_SKIP_DIRS = {
    "node_modules",
    ".angular",
    "dist",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
}


def scan_project(
    project_path: str,
    migration_type: str = "angular_control_flow",
    rule_registry: RuleRegistry | None = None,
) -> ProjectScanOutput:
    """Scan a project directory for migration targets.

    Args:
        project_path: Absolute or relative path to the project root.
        migration_type: Which migration to scan for (currently only
                        "angular_control_flow" is supported).
        rule_registry: Optional custom RuleRegistry; defaults to the module-level
                       singleton.

    Returns:
        A ProjectScanOutput with all detected patterns classified.
    """
    reg = rule_registry or registry
    project = Path(project_path).resolve()

    if not project.is_dir():
        raise FileNotFoundError(f"Project path does not exist: {project}")

    extensions = _FILE_EXTENSIONS.get(migration_type)
    if extensions is None:
        raise ValueError(
            f"Unsupported migration type: {migration_type!r}. "
            f"Supported: {list(_FILE_EXTENSIONS.keys())}"
        )

    results: list[ScanResult] = []
    files_scanned = 0

    for root, dirs, files in os.walk(project):
        # Prune skipped directories
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]

        for filename in files:
            if not any(filename.endswith(ext) for ext in extensions):
                continue

            filepath = Path(root) / filename
            files_scanned += 1

            try:
                template = filepath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            classifications = reg.classify(template)
            for cls in classifications:
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
        migration_type=migration_type,
        total_files_scanned=files_scanned,
        total_patterns_found=len(results),
        deterministic_count=deterministic_count,
        ambiguous_count=ambiguous_count,
        results=results,
    )
