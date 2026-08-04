"""
Planner Node.

The brain of the agent. Pops the next file from the queue, scans it to
determine the migration strategy, and sets the current task state.
If running in dry_run mode, it just records the intended strategy without
applying changes.
"""

from __future__ import annotations

from automigrate.agent.state import FileTask, MigrationState
from automigrate.mcp_server.tools.scan_project import scan_project


def planner_node(state: MigrationState) -> dict:
    """Planner node: picks the next file and determines the strategy."""
    queue = list(state.get("file_queue", []))
    
    if not queue:
        return {"current_file": None}
    
    current_file = queue.pop(0)
    project_path = state["project_path"]
    migration_type = state["migration_type"]
    dry_run = state.get("dry_run", False)
    
    # In a real run, if the file already has a strategy, we might be retrying.
    # For now, we always scan to determine strategy if it's not set.
    if not current_file.strategy:
        # We can use the scan_project tool (which operates on directories)
        # by scanning the whole project once, or if we refactor it, scan just one file.
        # For simplicity here, we'll scan the whole project and find our file.
        # In a fully optimized version, we'd have a single-file scanner tool.
        scan_result = scan_project(project_path, migration_type)
        
        # Find matches for our specific file
        file_matches = [
            r for r in scan_result.results
            if r.file_path == current_file.file_path
        ]
        
        if not file_matches:
            # Nothing to migrate in this file? Shouldn't happen if queued properly,
            # but default to deterministic if empty.
            current_file.strategy = "deterministic"
            current_file.complexity = "simple"
        else:
            # If any match is ambiguous, the whole file goes through the LLM fallback path
            has_ambiguous = any(r.classification == "ambiguous" for r in file_matches)
            current_file.strategy = "ambiguous" if has_ambiguous else "deterministic"
            
            # Estimate complexity
            if any(r.complexity == "complex" for r in file_matches):
                current_file.complexity = "complex"
            elif any(r.complexity == "medium" for r in file_matches):
                current_file.complexity = "medium"
            else:
                current_file.complexity = "simple"
                
    # Initialize retry count if this is the first time seeing the file
    retry_updates = {}
    if current_file.file_path not in state.get("retry_counts", {}):
        retry_updates[current_file.file_path] = 0
        
    return {
        "file_queue": queue,
        "current_file": current_file,
        "retry_counts": retry_updates,
    }


def route_after_planner(state: MigrationState) -> str:
    """Determine the next step after the planner."""
    current_file = state.get("current_file")
    
    if not current_file:
        return "report_generator"
        
    if state.get("dry_run"):
        return "record_result"
        
    if current_file.strategy == "ambiguous":
        return "rag_retriever"  # Phase 3
        
    return "apply_ast_transform"
