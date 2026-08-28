"""
Agent State Schema.

Defines the LangGraph state for the AutoMigrate agent.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

# Failure categories that the retry classifier uses to route targeted retries.
FailureCategory = Literal[
    "syntax_failure",
    "compilation_failure",
    "type_error",
    "lint_error",
    "secrets_detected",
    "test_failure",
    "runtime_failure",
    "unknown",
]


class ValidationResult(BaseModel):
    """Result from a static validation stage."""
    passed: bool
    stage: str  # e.g., "AST", "TypeCheck", "Lint"
    errors: list[str] = Field(default_factory=list)


class TestResult(BaseModel):
    """Result from running the test suite."""
    passed: bool
    total: int
    failed: int
    logs: str


class FileTask(BaseModel):
    """A single file to be migrated."""
    file_path: str
    strategy: str | None = None  # "deterministic" or "ambiguous"
    complexity: str | None = None


class MigrationReport(BaseModel):
    """Final summary report."""
    total_files: int
    successful_files: int
    escalated_files: int
    estimated_time_saved_minutes: int


def reduce_list(left: list | None, right: list | None) -> list:
    """Reducer for LangGraph state to append to lists."""
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right


def reduce_dict(left: dict | None, right: dict | None) -> dict:
    """Reducer for LangGraph state to update dictionaries."""
    if left is None:
        left = {}
    if right is None:
        right = {}
    return {**left, **right}


class MigrationState(TypedDict):
    """The overall LangGraph state for a migration run."""

    # Run configuration
    project_path: str
    framework: str        # e.g. "angular", "react", "vue" — used to look up the adapter
    migration_type: str   # e.g. "control_flow", "class_to_hooks"
    dry_run: bool
    max_retries: int
    run_id: str  # Unique per-run ID, e.g. "run_2026_08_24_2209"
    
    # Queue management
    file_queue: list[FileTask]
    current_file: FileTask | None
    
    # State for the current file
    transformed_content: str | None
    diff: str | None

    # Failure context for targeted retries.
    # Maps file_path -> human-readable failure summary passed back to LLM.
    failure_context: Annotated[dict[str, str], reduce_dict]
    
    # Tracking progress and metrics
    # Using Annotated to specify how updates are merged (reducers)
    retry_counts: Annotated[dict[str, int], reduce_dict]
    confidence_scores: Annotated[dict[str, float], reduce_dict]
    validation_results: Annotated[dict[str, ValidationResult], reduce_dict]
    test_results: Annotated[dict[str, TestResult], reduce_dict]
    failure_categories: Annotated[dict[str, FailureCategory], reduce_dict]
    
    completed_files: Annotated[list[str], reduce_list]
    escalated_files: Annotated[list[str], reduce_list]
    
    report: MigrationReport | None
