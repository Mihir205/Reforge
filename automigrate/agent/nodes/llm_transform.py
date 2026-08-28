"""
LLM Transformation Node.

Handles ambiguous transformations using LLM and retrieved context.
"""

from __future__ import annotations

import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from automigrate.agent.state import MigrationState
from automigrate.rag.retriever import retrieve_and_rerank
from automigrate.transforms.angular_control_flow.rules import registry


def llm_transform_node(state: MigrationState) -> dict:
    """LangGraph node for LLM-based transformation."""
    current_file = state.get("current_file")
    if not current_file:
        return {}
        
    from pathlib import Path
    project_path = state["project_path"]
    full_path = str(Path(project_path) / current_file.file_path)
    
    try:
        content = open(full_path, "r", encoding="utf-8").read()
    except OSError:
        return {"transformed_content": None}

    # Extract the ambiguous snippet. For simplicity, just use the whole file content
    # or rely on the RAG query to be about the file.
    # In a full version, we'd extract specifically the `ambiguous` regions from the scanner.
    
    context = retrieve_and_rerank(
        query=f"Angular {state['migration_type']} migration for: {content[:200]}"
    )
    
    # Real LLM call using Ollama
    failure_ctx = state.get("failure_context", {}).get(current_file.file_path, "")

    system_prompt = (
        "You are an expert Angular developer. Migrate the provided template to the new "
        "Angular v17 control flow syntax based on the provided documentation.\n\n"
        "CRITICAL RULES:\n"
        "1. NEVER put @if, @for, or @switch inside HTML tags like attributes.\n"
        "2. The control flow syntax MUST wrap the HTML elements, not be inside them.\n"
        "3. Reply ONLY with the rewritten code. Do NOT wrap it in markdown block quotes.\n\n"
        "DOCS:\n{context}"
    )
    if failure_ctx:
        system_prompt += f"\n\nPREVIOUS FAILURE CONTEXT (read carefully before rewriting):\n{failure_ctx}"

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "Migrate this template:\n<div *ngIf=\"condition\">\n  <p>Hello</p>\n</div>"),
        ("assistant", "@if (condition) {{\n  <div>\n    <p>Hello</p>\n  </div>\n}}"),
        ("user", "Migrate this template:\n<ul>\n  <li *ngFor=\"let item of items; trackBy: trackItem\">\n    {{{{item}}}}\n  </li>\n</ul>"),
        ("assistant", "<ul>\n  @for (item of items; track trackItem($index, item)) {{\n    <li>\n      {{{{item}}}}\n    </li>\n  }}\n</ul>"),
        ("user", "{code}"),
    ])
    
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    # Use 127.0.0.1 explicitly to avoid WinError 10049 (IPv6 localhost resolution issue)
    llm = ChatOllama(
        model=ollama_model, 
        temperature=0,
        base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    )
    chain = prompt | llm
    
    response = chain.invoke({
        "context": context,
        "code": content
    })
    transformed = response.content
    
    # In a real app, strip markdown code block formatting just in case
    if transformed.startswith("```html"):
        transformed = transformed.split("\n", 1)[1].rsplit("\n", 1)[0]
    elif transformed.startswith("```"):
        transformed = transformed.split("\n", 1)[1].rsplit("\n", 1)[0]
    
    # Write to disk so static validation can test the real file
    try:
        import shutil
        from pathlib import Path
        p = Path(full_path)
        if p.exists() and transformed != content:
            shutil.copy2(p, p.with_suffix(p.suffix + ".bak"))
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(transformed)
    except OSError as e:
        pass
        
    return {
        "transformed_content": transformed,
        "diff": "LLM diff placeholder"  # normally computed using difflib
    }
