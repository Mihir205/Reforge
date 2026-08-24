"""
Tests for Phase 3: RAG-Grounded Fallback, Verification, and Secrets Scanning.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from automigrate.rag.retriever import retrieve_and_rerank
from automigrate.mcp_server.tools.verification_agent import run_verification_agent
from automigrate.mcp_server.tools.secrets_scan import run_secrets_scan
from automigrate.agent.state import FileTask
from automigrate.agent.graph import create_agent_graph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_initial_state(project_dir, file_queue):
    """Return a fully-populated initial state dict required by the updated schema."""
    return {
        "project_path": str(project_dir),
        "migration_type": "angular_control_flow",
        "dry_run": False,
        "max_retries": 3,
        "run_id": "run_test",
        "file_queue": file_queue,
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


# ---------------------------------------------------------------------------
# Unit tests for individual Phase 3 tools
# ---------------------------------------------------------------------------

class TestPhase3Tools:

    def test_verification_agent_passes_clean_code(self):
        code = "@if (show) {\n  <div>Hello</div>\n}"
        result = run_verification_agent("test.html", code)
        assert result.passed
        assert len(result.errors) == 0

    def test_verification_agent_fails_legacy_directives(self):
        code = "@if (show) {\n  <div *ngIf=\"inner\">Hello</div>\n}"
        result = run_verification_agent("test.html", code)
        assert not result.passed
        assert "Legacy structural directives" in result.errors[0]

    def test_verification_agent_fails_unbalanced_braces(self):
        code = "@if (show) {\n  <div>Hello</div>"
        result = run_verification_agent("test.html", code)
        assert not result.passed
        assert "Unbalanced braces" in result.errors[0]

    def test_secrets_scan_passes_clean_code(self):
        code = "@if (show) {\n  <div>Hello</div>\n}"
        result = run_secrets_scan("test.html", code)
        assert result.passed

    def test_secrets_scan_fails_on_credentials(self):
        code = "const apiKey = 'AKIA1234567890123456';"
        result = run_secrets_scan("test.js", code)
        assert not result.passed
        assert "Secret detected: AWS Access Key" in result.errors[0]


# ---------------------------------------------------------------------------
# Orchestration tests (graph-level)
# ---------------------------------------------------------------------------

class TestPhase3Orchestration:

    def test_ambiguous_routing_and_fallback(self, tmp_path):
        """Test that an ambiguous pattern triggers the RAG/LLM path.

        The LLM node itself is mocked at the graph level so the test is
        fast and doesn't require a live Ollama server.
        """
        project_dir = tmp_path / "project3"
        project_dir.mkdir()
        test_file = project_dir / "ambiguous.html"
        # ngif_async_pipe is classified as ambiguous in our rule registry
        test_file.write_text('<div *ngIf="data$ | async as data"><p>{{ data }}</p></div>')

        transformed_html = "@if (data$ | async; as data) {\n  <div><p>{{ data }}</p></div>\n}"

        def mock_llm_node(state):
            """Simulated LLM node: writes the pre-canned transform to disk."""
            curr = state.get("current_file")
            if not curr:
                return {}
            filepath = f"{state['project_path']}/{curr.file_path}"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(transformed_html)
            return {"transformed_content": transformed_html, "diff": "mock diff"}

        # Patch the node in the graph module (where it was imported at load time)
        with patch("automigrate.agent.graph.llm_transform_node", mock_llm_node):
            app = create_agent_graph()
            initial_state = _base_initial_state(
                project_dir, [FileTask(file_path="ambiguous.html")]
            )
            final_state = app.invoke(initial_state)

        assert final_state["report"] is not None
        assert final_state["report"].total_files == 1

        # Verify the file was transformed by the (mocked) LLM path
        content = test_file.read_text()
        assert "@if" in content
        assert "async as" not in content

    def test_secrets_scan_escalation(self, tmp_path):
        """Test that a file containing a secret gets escalated and not completed."""
        project_dir = tmp_path / "project_secrets"
        project_dir.mkdir()
        test_file = project_dir / "secret.html"
        # Adding a secret to the file so it triggers the scanner
        test_file.write_text('<div *ngIf="show">AKIA1234567890123456</div>')

        app = create_agent_graph()
        initial_state = _base_initial_state(
            project_dir, [FileTask(file_path="secret.html")]
        )
        final_state = app.invoke(initial_state)

        assert "secret.html" in final_state["escalated_files"]
        assert "secret.html" not in final_state["completed_files"]

