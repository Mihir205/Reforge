"""
Tests for Phase 4: Confidence Scoring, Reporting, Observability.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automigrate.agent.state import FileTask, ValidationResult, TestResult
from automigrate.agent.nodes.confidence_calculator import calculate_confidence
from automigrate.agent.graph import create_agent_graph


class TestPhase4Features:

    def test_confidence_calculator(self):
        # Perfect deterministic score
        val_results = {
            "AST": ValidationResult(passed=True, stage="AST"),
            "TypeCheck": ValidationResult(passed=True, stage="TypeCheck"),
            "Lint": ValidationResult(passed=True, stage="Lint"),
            "VerificationAgent": ValidationResult(passed=True, stage="VerificationAgent"),
        }
        score = calculate_confidence("deterministic", val_results, True)
        assert score == 100.0

        # Ambiguous but passes tests
        score = calculate_confidence("ambiguous", val_results, True)
        assert score == 60.0  # 10 + 15 + 10 + 5 + 20

        # Fails tests
        score = calculate_confidence("deterministic", val_results, False)
        assert score == 80.0

    def test_report_and_ticket_generation(self, tmp_path):
        """Test that the graph produces a JSON report and markdown tickets for escalated files."""
        run_id = "run_test"
        app = create_agent_graph()

        project_dir = tmp_path / "project4"
        project_dir.mkdir()
        test_file = project_dir / "report_test.html"
        test_file.write_text('<div *ngIf="show">AKIA1234567890123456</div>')

        initial_state = {
            "project_path": str(project_dir),
            "migration_type": "angular_control_flow",
            "dry_run": False,
            "max_retries": 3,
            "run_id": run_id,
            "file_queue": [FileTask(file_path="report_test.html")],
            "current_file": None,
            "transformed_content": None,
            "diff": None,
            "failure_context": {},
            "retry_counts": {},
            "confidence_scores": {},
            "validation_results": {},
            "test_results": {},
            "failure_categories": {},
            "completed_files": [],
            "escalated_files": [],
            "report": None,
        }

        final_state = app.invoke(initial_state)

        # Verify graph finished
        assert final_state.get("report") is not None

        # Check JSON report exists in the per-run directory
        report_path = Path("reports") / run_id / "report.json"
        assert report_path.exists(), f"Expected report at {report_path}"

        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        assert report_data["summary"]["total_files"] >= 1
        escalated = [f["file"] for f in report_data["files"] if f.get("human_review_required")]
        assert "report_test.html" in escalated

        # Check review ticket is in the per-run review directory
        safe_name = "report_test.html".replace("/", "_").replace("\\", "_")
        ticket_path = Path("reports") / run_id / "review" / f"REVIEW_{safe_name}.md"
        assert ticket_path.exists(), f"Expected ticket at {ticket_path}"

        ticket_content = ticket_path.read_text(encoding="utf-8")
        assert "Migration Review Required" in ticket_content
        assert "Confidence Score" in ticket_content

