"""
LLM Transformation Node.

Handles ambiguous transformations using an LLM grounded by framework-specific
documentation retrieved from the active FrameworkAdapter.

The adapter provides:
  - Migration docs (injected as {context} in the system prompt)
  - System prompt template
  - Few-shot examples

This node is framework-agnostic: Angular, React, Vue, etc. all run through
the same node — the adapter controls what the LLM sees.
"""

from __future__ import annotations

import difflib
import logging
import os
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from automigrate.agent.state import MigrationState

logger = logging.getLogger(__name__)


def _get_adapter(state: MigrationState):
    """Load the framework adapter from state."""
    from automigrate.adapters.registry import get_adapter
    framework = state.get("framework", "angular")
    try:
        return get_adapter(framework)
    except ValueError:
        logger.warning("Unknown framework %r — falling back to angular adapter", framework)
        return get_adapter("angular")


def _strip_code_fence(text: str) -> str:
    """Remove markdown code fence wrappers if the LLM added them."""
    text = text.strip()
    for lang_tag in ("```html", "```jsx", "```tsx", "```typescript", "```ts", "```js", "```"):
        if text.startswith(lang_tag):
            text = text[len(lang_tag):]
            if text.endswith("```"):
                text = text[:-3]
            return text.strip()
    return text


def llm_transform_node(state: MigrationState) -> dict:
    """LangGraph node for LLM-based transformation.

    Loads the framework adapter from state, retrieves migration docs,
    builds a framework-specific prompt, and calls the configured LLM.
    """
    current_file = state.get("current_file")
    if not current_file:
        return {}

    project_path = state["project_path"]
    full_path = str(Path(project_path) / current_file.file_path)

    try:
        content = Path(full_path).read_text(encoding="utf-8")
    except OSError:
        logger.error("Could not read %s", full_path)
        return {"transformed_content": None}

    # ── Load adapter ─────────────────────────────────────────────────────────
    adapter = _get_adapter(state)
    migration_type = state.get("migration_type", adapter.get_default_migration().id)

    # ── Retrieve migration docs (RAG context) ─────────────────────────────────
    context = adapter.get_migration_docs(migration_type)

    # ── Build system prompt ───────────────────────────────────────────────────
    failure_ctx = state.get("failure_context", {}).get(current_file.file_path, "")
    system_prompt_template = adapter.get_llm_system_prompt(migration_type)

    # Inject context into the system prompt template
    system_prompt = system_prompt_template.format(context=context)

    if failure_ctx:
        system_prompt += (
            f"\n\nPREVIOUS FAILURE CONTEXT (read carefully before rewriting):\n{failure_ctx}"
        )

    # ── Build few-shot messages ───────────────────────────────────────────────
    messages = [("system", system_prompt)]
    for user_ex, assistant_ex in adapter.get_llm_examples(migration_type):
        messages.append(("user", user_ex))
        messages.append(("assistant", assistant_ex))
    messages.append(("user", "Migrate this file:\n{code}"))

    prompt = ChatPromptTemplate.from_messages(messages)

    # ── LLM call ─────────────────────────────────────────────────────────────
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    llm = ChatOllama(
        model=ollama_model,
        temperature=0,
        base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    )
    chain = prompt | llm

    response = chain.invoke({"code": content})
    transformed = _strip_code_fence(response.content)

    # ── Generate diff ─────────────────────────────────────────────────────────
    diff = "".join(
        difflib.unified_diff(
            content.splitlines(keepends=True),
            transformed.splitlines(keepends=True),
            fromfile=f"a/{current_file.file_path}",
            tofile=f"b/{current_file.file_path}",
        )
    )

    # ── Write to disk so validators can inspect the real file ─────────────────
    if transformed and transformed != content:
        try:
            import shutil

            p = Path(full_path)
            shutil.copy2(p, p.with_suffix(p.suffix + ".bak"))
            p.write_text(transformed, encoding="utf-8")
        except OSError as e:
            logger.warning("Could not write transformed file %s: %s", full_path, e)

    return {
        "transformed_content": transformed,
        "diff": diff or "No changes",
    }
