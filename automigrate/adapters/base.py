"""
FrameworkAdapter — Abstract Base Class.

Every framework migration adapter must implement this interface.
The agent pipeline, scanner, LLM transform, and validators all
operate against this interface — they know nothing about Angular,
React, or any other specific framework.

Adding a new framework = creating a new FrameworkAdapter subclass.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from automigrate.agent.state import ValidationResult

from automigrate.transforms.base_rules import RuleRegistry


# ---------------------------------------------------------------------------
# Descriptor: describes one migration type within a framework
# ---------------------------------------------------------------------------


@dataclass
class MigrationDescriptor:
    """Describes a single migration type that an adapter supports.

    Example:
        MigrationDescriptor(
            id="control_flow",
            display_name="Control Flow Syntax",
            description="Migrate *ngIf/*ngFor to @if/@for (Angular 17+)",
        )
    """

    id: str               # slug used internally (e.g., "control_flow")
    display_name: str     # shown in CLI (e.g., "Control Flow Syntax")
    description: str      # one-line description
    default: bool = False  # is this the default migration for the framework?


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class FrameworkAdapter(ABC):
    """Abstract base class for all framework migration adapters.

    Implementers provide all the framework-specific knowledge that the
    generic agent pipeline needs:
      - Which files to scan
      - What deterministic rules exist
      - What documentation to inject into the LLM prompt (RAG)
      - How to prompt the LLM
      - How to validate transformed files
      - What test command to run
    """

    # ---- Class-level metadata (must be set by subclasses) ----

    #: Unique lowercase slug, e.g. "angular", "react", "vue"
    name: str = ""

    #: Display name for CLI output, e.g. "Angular", "React", "Vue.js"
    display_name: str = ""

    # ---- Detection ----

    @classmethod
    @abstractmethod
    def detect(cls, project_path: str) -> bool:
        """Return True if this adapter can handle the given project.

        Implementations typically inspect package.json, requirements.txt,
        build config files, etc.

        Args:
            project_path: Absolute path to the project root directory.
        """

    # ---- Migration catalogue ----

    @abstractmethod
    def get_migrations(self) -> list[MigrationDescriptor]:
        """Return the list of migration types this adapter supports."""

    def get_default_migration(self) -> MigrationDescriptor:
        """Return the default migration (first with default=True, or first)."""
        migrations = self.get_migrations()
        for m in migrations:
            if m.default:
                return m
        return migrations[0]

    def get_migration(self, migration_id: str) -> MigrationDescriptor | None:
        """Look up a migration descriptor by its ID."""
        for m in self.get_migrations():
            if m.id == migration_id:
                return m
        return None

    # ---- File scanning ----

    @abstractmethod
    def get_file_patterns(self, migration_type: str) -> list[str]:
        """Return file suffix patterns to include when scanning.

        Example: [".html", ".component.html"] for Angular templates.
        """

    @abstractmethod
    def get_skip_dirs(self) -> set[str]:
        """Return directory names to skip during project scanning."""

    # ---- Deterministic rules ----

    @abstractmethod
    def get_rule_registry(self, migration_type: str) -> RuleRegistry:
        """Return the RuleRegistry for deterministic transforms."""

    # ---- LLM transform ----

    @abstractmethod
    def get_migration_docs(self, migration_type: str) -> str:
        """Return the migration documentation injected into the LLM prompt.

        This is the RAG layer: the adapter bundles its own docs and
        returns the relevant content as a string. For large doc sets,
        subclasses can implement actual vector retrieval here.
        """

    @abstractmethod
    def get_llm_system_prompt(self, migration_type: str) -> str:
        """Return the system prompt for the LLM transformation node."""

    @abstractmethod
    def get_llm_examples(self, migration_type: str) -> list[tuple[str, str]]:
        """Return few-shot examples as (user_message, assistant_message) pairs."""

    # ---- Failure recovery ----

    @abstractmethod
    def get_failure_hints(self, migration_type: str) -> dict[str, str]:
        """Return framework-specific hints keyed by FailureCategory.

        These are injected into the retry prompt to guide the LLM away
        from repeating the same mistake.

        Expected keys (matching FailureCategory literals):
            "syntax_failure", "compilation_failure", "type_error",
            "lint_error", "secrets_detected", "test_failure", "unknown"
        """

    # ---- Testing ----

    @abstractmethod
    def get_test_command(self, project_path: str) -> list[str] | None:
        """Return the shell command to run the project's test suite.

        Return None if tests cannot be auto-detected (will be skipped).

        Example: ["npx", "ng", "test", "--watch=false"]
        """

    # ---- Static validation ----

    def get_static_validators(
        self, migration_type: str
    ) -> list[Callable[[str, str, str], "ValidationResult"]]:
        """Return a list of static validator callables.

        Each callable has the signature:
            fn(file_path: str, content: str, project_path: str) -> ValidationResult

        Subclasses override this to add framework-specific validators
        (e.g., tsc, eslint, ruff, pyright). The default returns an empty list,
        meaning only the generic verification agent runs.
        """
        return []

    # ---- Helpers ----

    @classmethod
    def _read_json(cls, path: Path) -> dict[str, Any] | None:
        """Utility: read a JSON file, returning None on any error."""
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @classmethod
    def _file_contains(cls, path: Path, *patterns: str) -> bool:
        """Utility: check if a text file contains any of the given strings."""
        try:
            content = path.read_text(encoding="utf-8")
            return any(p in content for p in patterns)
        except Exception:
            return False

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
