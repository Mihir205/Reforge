"""
Tests for Phase 2: Agentic Orchestration & Dry Run.

Validates the LangGraph state graph, planner node logic, dry run routing,
and report generation.
"""

from __future__ import annotations

import pytest

from automigrate.agent.state import FileTask
from automigrate.agent.graph import create_agent_graph


class TestAgentOrchestration:
    """Test the LangGraph state and planner node."""
    
    def test_dry_run_routing(self, tmp_path):
        """Test that dry_run skips modification nodes and routes correctly."""
        app = create_agent_graph()
        
        # Setup dummy project
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        test_file = project_dir / "test.html"
        test_file.write_text('<div *ngIf="show"></div>')
        
        initial_state = {
            "project_path": str(project_dir),
            "migration_type": "angular_control_flow",
            "dry_run": True,
            "max_retries": 3,
            "run_id": "run_test",
            "file_queue": [FileTask(file_path="test.html")],
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
        
        # Run graph
        final_state = app.invoke(initial_state)
        
        assert final_state["report"] is not None
        assert final_state["report"].total_files == 1
        assert "test.html" in final_state["completed_files"]
        
        # Verify file wasn't modified
        assert test_file.read_text() == '<div *ngIf="show"></div>'

    def test_live_run_routing(self, tmp_path):
        """Test that a live run applies transforms."""
        app = create_agent_graph()
        
        project_dir = tmp_path / "project2"
        project_dir.mkdir()
        test_file = project_dir / "test2.html"
        test_file.write_text('<div *ngIf="show"></div>')
        
        initial_state = {
            "project_path": str(project_dir),
            "migration_type": "angular_control_flow",
            "dry_run": False,
            "max_retries": 3,
            "run_id": "run_test",
            "file_queue": [FileTask(file_path="test2.html")],
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
        
        assert final_state["report"] is not None
        assert final_state["report"].total_files == 1
        
        # Verify file was modified
        assert "@if" in test_file.read_text()
