"""
Planner Node.

The brain of the agent. Pops the next file from the queue, scans it to
determine the migration strategy, and sets the current task state.

On re-entry (retry), it reads the failure category from state and builds
a targeted failure_context string that the LLM transformation node can
use to avoid repeating the same mistake.
"""

from __future__ import annotations

import logging

from automigrate.agent.state import FailureCategory, FileTask, MigrationState
from automigrate.mcp_server.tools.scan_project import scan_project

logger = logging.getLogger(__name__)


# ----- Failure category detection -----

def _classify_failure(
    file_path: str,
    validation_results: dict,
    test_results: dict,
) -> FailureCategory:
    """Inspect validation and test results to assign a failure category."""
    val = validation_results.get(file_path)
    test = test_results.get(file_path)

    if val and not val.passed:
        stage = val.stage.lower()
        if stage == "ast":
            return "syntax_failure"
        if stage == "typecheck":
            return "type_error"
        if stage == "lint":
            return "lint_error"
        if stage == "secretsscan":
            return "secrets_detected"
        if stage == "verificationagent":
            return "syntax_failure"

    if test and not test.passed:
        return "test_failure"

    return "unknown"


def _build_failure_context(
    category: FailureCategory,
    val_errors: list[str],
    test_logs: str,
    framework: str,
    migration_type: str,
) -> str:
    """Build a targeted natural-language description of the failure for the retry prompt."""
    lines = [f"Previous attempt failed with category: {category}."]

    if val_errors:
        lines.append("Validation errors:")
        lines.extend(f"  - {e}" for e in val_errors)

    if category == "test_failure" and test_logs:
        last_lines = test_logs.strip().splitlines()[-30:]
        lines.append("Test failure output:")
        lines.extend(f"  {l}" for l in last_lines)

    # Load framework-specific hints from the adapter
    try:
        from automigrate.adapters.registry import get_adapter
        adapter = get_adapter(framework)
        category_hints = adapter.get_failure_hints(migration_type)
    except Exception:
        category_hints = {
            "unknown": "Review the full file carefully and ensure the migration is complete.",
        }

    hint = category_hints.get(category, category_hints.get("unknown", "Review carefully."))
    lines.append(f"Correction guidance: {hint}")
    return "\n".join(lines)


# ----- Planner node -----

def planner_node(state: MigrationState) -> dict:
    """Planner node: picks the next file and determines the strategy.

    On a retry iteration, the file is re-queued by the graph after a failed
    confidence pass. In that case we classify the failure, build failure
    context, and let the LLM node read it.
    """
    queue = list(state.get("file_queue", []))
    max_retries = state.get("max_retries", 3)

    if not queue:
        return {"current_file": None}

    current_file = queue.pop(0)
    project_path = state["project_path"]
    migration_type = state["migration_type"]

    # ---- Retry detection ----
    retry_counts = dict(state.get("retry_counts", {}))
    file_retries = retry_counts.get(current_file.file_path, 0)

    if file_retries > 0:
        # Classify the previous failure and build targeted context for the LLM.
        category = _classify_failure(
            current_file.file_path,
            state.get("validation_results", {}),
            state.get("test_results", {}),
        )

        # Secrets failures are never retried — escalate immediately.
        if category == "secrets_detected":
            logger.warning("Secrets detected in %s — escalating immediately.", current_file.file_path)
            return {
                "file_queue": queue,
                "current_file": current_file,
                "failure_categories": {current_file.file_path: category},
                "escalated_files": [current_file.file_path],
                "retry_counts": {current_file.file_path: file_retries},
            }

        # Budget exhausted — escalate.
        if file_retries >= max_retries:
            logger.warning(
                "Retry budget exhausted (%d/%d) for %s — escalating.",
                file_retries, max_retries, current_file.file_path,
            )
            return {
                "file_queue": queue,
                "current_file": current_file,
                "failure_categories": {current_file.file_path: category},
                "escalated_files": [current_file.file_path],
                "retry_counts": {current_file.file_path: file_retries},
            }

        val_result = state.get("validation_results", {}).get(current_file.file_path)
        val_errors = val_result.errors if val_result else []
        test_result = state.get("test_results", {}).get(current_file.file_path)
        test_logs = test_result.logs if test_result else ""

        failure_ctx = _build_failure_context(
            category,
            val_errors,
            test_logs,
            framework=state.get("framework", "angular"),
            migration_type=state.get("migration_type", "control_flow"),
        )
        logger.info(
            "Retry %d/%d for %s — category: %s",
            file_retries, max_retries, current_file.file_path, category,
        )

        return {
            "file_queue": queue,
            "current_file": current_file,
            "failure_categories": {current_file.file_path: category},
            "failure_context": {current_file.file_path: failure_ctx},
            "retry_counts": {current_file.file_path: file_retries},
        }

    # ---- First-time setup (if strategy not provided) ----
    if not current_file.strategy:
        current_file.strategy = "deterministic"
        current_file.complexity = "simple"

    return {
        "file_queue": queue,
        "current_file": current_file,
        "retry_counts": {current_file.file_path: 0},
    }


def route_after_planner(state: MigrationState) -> str:
    """Determine the next step after the planner."""
    current_file = state.get("current_file")

    if not current_file:
        return "report_generator"

    if state.get("dry_run"):
        return "record_result"

    # If the file has already been escalated (budget or secrets), loop to the next file.
    if current_file.file_path in state.get("escalated_files", []):
        return "planner"

    if current_file.strategy == "ambiguous":
        return "rag_retriever"

    return "apply_ast_transform"

