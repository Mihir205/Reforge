"""
Report Generator Node.

Generates the final migration report for the run:
  - reports/run_<id>/report.json   (canonical, machine-readable)
  - reports/run_<id>/report.md     (human-readable rendering)
  - reports/run_<id>/review/       (per-file review tickets for escalated files)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from automigrate.agent.state import MigrationState, MigrationReport
from automigrate.agent.nodes.confidence_calculator import QUICK_REVIEW_THRESHOLD, AUTO_APPROVE_THRESHOLD
from automigrate.mcp_server.tools.create_review_ticket import create_review_ticket


def _generate_md(report_dict: dict, run_dir: Path) -> str:
    """Render report.json into a human-readable markdown string."""
    s = report_dict["summary"]
    files = report_dict["files"]
    ts = report_dict["timestamp"]

    lines = [
        f"# AutoMigrate Report — `{report_dict['run_id']}`",
        f"",
        f"**Timestamp:** {ts}  ",
        f"**Project:** `{report_dict['project']}`  ",
        f"**Migration:** `{report_dict['migration_type']}`",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Total files | {s['total_files']} |",
        f"| Auto-approved (≥{AUTO_APPROVE_THRESHOLD:.0f}) | {s['auto_approved']} |",
        f"| Flagged for review | {s['flagged_for_review']} |",
        f"| Avg confidence | {s['avg_confidence']:.1f} |",
        f"| Estimated time saved | {s['time_saved_estimate_hours']:.1f} h |",
        f"",
        f"## File Details",
        f"",
        f"| File | Strategy | Confidence | Status |",
        f"|---|---|---|---|",
    ]

    for f in files:
        status = "✅ Auto-approved" if not f["human_review_required"] else "⚠️ Review required"
        lines.append(
            f"| `{f['file']}` | {f['strategy']} | {f['confidence_score']} | {status} |"
        )

    if any(f["human_review_required"] for f in files):
        lines += [
            f"",
            f"## Review Required",
            f"",
            f"The following files need human review (see `{run_dir}/review/`):",
            f"",
        ]
        for f in files:
            if f["human_review_required"]:
                lines.append(f"- `{f['file']}` (confidence {f['confidence_score']}, {f.get('failure_category', 'n/a')})")

    return "\n".join(lines)


def report_generator_node(state: MigrationState) -> dict:
    """Terminal node that generates the final migration report."""
    completed = state.get("completed_files", [])
    escalated = state.get("escalated_files", [])
    total = len(completed) + len(escalated)
    run_id = state.get("run_id", f"run_{datetime.now().strftime('%Y_%m_%d_%H%M')}")

    output_dir = state.get("output_dir", "reports")
    # Build per-run output directory
    run_dir = Path(output_dir) / run_id
    review_dir = run_dir / "review"
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate review tickets for escalated files
    for file_path in escalated:
        val_res = state.get("validation_results", {}).get(file_path)
        errors = val_res.errors if val_res else []
        test_res = state.get("test_results", {}).get(file_path)
        test_logs = test_res.logs if test_res else ""
        score = state.get("confidence_scores", {}).get(file_path, 0.0)
        category = state.get("failure_categories", {}).get(file_path, "unknown")

        create_review_ticket(
            file_path=file_path,
            confidence_score=score,
            strategy="ambiguous",
            diff="[Diff omitted for summary]",
            validation_errors=errors,
            test_logs=test_logs,
            run_id=run_id,
            output_dir=str(review_dir),
        )

    # 2. Compute summary stats
    all_scores = state.get("confidence_scores", {})
    avg_confidence = (
        sum(all_scores.values()) / len(all_scores) if all_scores else 0.0
    )

    # 3. Build canonical report.json structure
    file_records = []
    for fp in completed:
        score = all_scores.get(fp, 0.0)
        file_records.append({
            "file": fp,
            "strategy": "deterministic",
            "confidence_score": round(score, 1),
            "validation": {
                "ast": "pass", "type_check": "pass", "lint": "pass",
                "secrets_scan": "pass", "tests": "pass",
            },
            "retry_count": state.get("retry_counts", {}).get(fp, 0),
            "failure_category": state.get("failure_categories", {}).get(fp),
            "human_review_required": False,
            "trace_url": None,
        })
    for fp in escalated:
        score = all_scores.get(fp, 0.0)
        file_records.append({
            "file": fp,
            "strategy": "ambiguous",
            "confidence_score": round(score, 1),
            "validation": {},
            "retry_count": state.get("retry_counts", {}).get(fp, 0),
            "failure_category": state.get("failure_categories", {}).get(fp, "unknown"),
            "human_review_required": True,
            "trace_url": None,
        })

    report_dict = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "project": state.get("project_path"),
        "migration_type": state.get("migration_type"),
        "files": file_records,
        "summary": {
            "total_files": total,
            "auto_approved": len(completed),
            "flagged_for_review": len(escalated),
            "avg_confidence": round(avg_confidence, 1),
            "time_saved_estimate_hours": round(len(completed) * 15 / 60, 2),
        },
    }

    # 4. Write report.json (canonical)
    json_path = run_dir / "report.json"
    json_path.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")

    # 5. Write report.md (derived, never maintained separately)
    md_content = _generate_md(report_dict, run_dir)
    md_path = run_dir / "report.md"
    md_path.write_text(md_content, encoding="utf-8")

    report = MigrationReport(
        total_files=total,
        successful_files=len(completed),
        escalated_files=len(escalated),
        estimated_time_saved_minutes=len(completed) * 15,
    )

    return {"report": report}

