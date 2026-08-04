"""
Dependency Analysis Tool.

Determines impact radius by analyzing imports across files.
"""

from __future__ import annotations

import re
from pathlib import Path


def analyze_dependencies(project_path: str, target_file: str) -> list[str]:
    """Find files that depend on the target_file using regex heuristics.
    
    In a real implementation, this would use a language server (LSP) or TS compiler API.
    """
    path = Path(project_path)
    if not path.exists():
        return []
        
    target_stem = Path(target_file).stem  # e.g. "demo.component"
    dependents = []
    
    # Simple recursive scan of all TS files
    for p in path.rglob("*.ts"):
        if p.name == Path(target_file).name:
            continue
            
        try:
            content = p.read_text(encoding="utf-8")
            # Look for import containing the stem
            if re.search(f"from\\s+['\"].*{target_stem}['\"]", content):
                dependents.append(str(p.relative_to(path)).replace("\\", "/"))
        except OSError:
            pass
            
    return dependents
