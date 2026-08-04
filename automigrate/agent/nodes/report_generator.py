"""
Report Generator Node.

Generates the final summary report for the migration run.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from automigrate.agent.state import MigrationState, MigrationReport
from automigrate.mcp_server.tools.create_review_ticket import create_review_ticket


def report_generator_node(state: MigrationState) -> dict:
    """Terminal node that generates the final migration report."""
    completed = state.get("completed_files", [])
    escalated = state.get("escalated_files", [])
    total = len(completed) + len(escalated)
    
    # 1. Generate tickets for escalated files
    for file_path in escalated:
        val_res = state.get("validation_results", {}).get(file_path, {})
        errors = val_res.errors if hasattr(val_res, "errors") else []
        
        test_res = state.get("test_results", {}).get(file_path)
        test_logs = test_res.logs if test_res else ""
        
        score = state.get("confidence_scores", {}).get(file_path, 0.0)
        
        # We find the file task to get the strategy
        strategy = "ambiguous"
        for t in state.get("file_queue", []):
            if t.file_path == file_path:
                strategy = t.strategy or "ambiguous"
                break
                
        # Diff isn't globally tracked per file in our simple state right now,
        # but in a full version it would be in a dictionary state like validation_results.
        
        create_review_ticket(
            file_path=file_path,
            confidence_score=score,
            strategy=strategy,
            diff="[Diff omitted for summary]",
            validation_errors=errors,
            test_logs=test_logs
        )
    
    # 2. Build final summary report
    report = MigrationReport(
        total_files=total,
        successful_files=len(completed),
        escalated_files=len(escalated),
        estimated_time_saved_minutes=len(completed) * 15
    )
    
    report_dict = {
        "timestamp": datetime.now().isoformat(),
        "project": state.get("project_path"),
        "migration_type": state.get("migration_type"),
        "metrics": report.model_dump(),
        "completed_files": completed,
        "escalated_files": escalated
    }
    
    # Write JSON report
    report_path = Path("reports/migration_summary.json")
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")
    
    return {"report": report}
