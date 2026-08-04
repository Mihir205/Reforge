"""
Multi-file orchestration utilities.

Groups related files together (e.g., component.ts and component.html)
so the LangGraph agent can context-switch or migrate them in tandem.
"""

from __future__ import annotations

from pathlib import Path


def group_related_files(file_paths: list[str]) -> dict[str, list[str]]:
    """Groups Angular files by component.
    
    For example, groups `demo.component.ts`, `demo.component.html`,
    and `demo.component.css` under the key `demo.component`.
    """
    groups = {}
    
    for fp in file_paths:
        path = Path(fp)
        
        # Determine the base component name (everything before .ts, .html, etc.)
        # If it's a standard naming convention like name.component.ext
        stem = path.stem
        # sometimes stem is name.component, sometimes just name
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
            
        base_name = f"{path.parent.as_posix()}/{stem}"
        
        if base_name not in groups:
            groups[base_name] = []
        groups[base_name].append(fp)
        
    return groups
