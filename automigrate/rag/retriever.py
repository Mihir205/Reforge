"""
RAG Retrieval — Framework-Aware Context Stuffing.

Retrieves migration documentation for the active framework adapter.
The adapter bundles its own docs, so retrieval is just loading the
right doc file. Future: add vector search for large doc sets.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def retrieve_and_rerank(
    query: str,
    top_n: int = 3,
    framework: str = "angular",
    migration_type: str = "control_flow",
) -> str:
    """Retrieve migration context for injection into the LLM prompt.

    For the current implementation (Context Stuffing), we load the full
    documentation bundle from the framework adapter. The query and top_n
    parameters are kept for forward compatibility with future vector search.

    Args:
        query:          Semantic search query (currently unused).
        top_n:          Number of chunks to return (currently unused).
        framework:      Framework name (e.g., "angular", "react").
        migration_type: Migration type (e.g., "control_flow", "class_to_hooks").

    Returns:
        Documentation string to inject as {context} in the LLM prompt.
    """
    try:
        from automigrate.adapters.registry import get_adapter
        adapter = get_adapter(framework)
        docs = adapter.get_migration_docs(migration_type)
        if docs:
            return docs
    except Exception as e:
        logger.warning("Failed to load docs via adapter: %s", e)

    # Fallback: try the legacy rag/data/ directory
    legacy_path = Path("automigrate/rag/data") / f"{framework}_{migration_type}.md"
    if legacy_path.exists():
        logger.info("Using legacy doc file: %s", legacy_path)
        return legacy_path.read_text(encoding="utf-8")

    logger.warning("No docs found for %s/%s", framework, migration_type)
    return f"# {framework.title()} {migration_type} Migration\n\nNo documentation found."
