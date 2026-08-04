"""
LangGraph State Graph definition for AutoMigrate.

Constructs the directed graph of agent states.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import StateGraph, END
from automigrate.agent.state import MigrationState, MigrationReport
from automigrate.agent.nodes.planner import planner_node, route_after_planner
from automigrate.mcp_server.tools.apply_ast_transform import apply_ast_transform
from automigrate.mcp_server.tools.static_validation import run_static_validation
from automigrate.mcp_server.tools.run_test_suite import run_test_suite

logger = logging.getLogger(__name__)


def apply_transform_node(state: MigrationState) -> dict:
    """Node to apply deterministic AST transforms."""
    current_file = state.get("current_file")
    if not current_file:
        return {}
        
    project_path = state["project_path"]
    full_path = f"{project_path}/{current_file.file_path}"
    
    # Run transform
    result = apply_ast_transform(full_path, write=True)
    
    return {
        "transformed_content": result.transformed_content,
        "diff": result.diff,
    }


def validate_node(state: MigrationState) -> dict:
    """Node to run static validation."""
    current_file = state.get("current_file")
    if not current_file:
        return {}
        
    results = run_static_validation(current_file.file_path, state["project_path"])
    return {"validation_results": {current_file.file_path: list(results.values())[-1]}}  # Simplified


def run_tests_node(state: MigrationState) -> dict:
    """Node to run the project's test suite."""
    current_file = state.get("current_file")
    if not current_file:
        return {}
        
    result = run_test_suite(state["project_path"], current_file.file_path)
    return {"test_results": {current_file.file_path: result}}


from automigrate.agent.nodes.confidence_calculator import confidence_calc_node
from automigrate.agent.nodes.report_generator import report_generator_node


def record_dry_run_node(state: MigrationState) -> dict:
    """Node for recording a dry-run result without modifying files."""
    current_file = state.get("current_file")
    if not current_file:
        return {}
        
    # In dry run, we don't calculate full confidence, but we can estimate
    estimated_score = 90.0 if current_file.strategy == "deterministic" else 40.0
    
    return {
        "confidence_scores": {current_file.file_path: estimated_score},
        "completed_files": [current_file.file_path] if estimated_score >= 70 else [],
        "escalated_files": [current_file.file_path] if estimated_score < 70 else [],
    }


from automigrate.agent.nodes.llm_transform import llm_transform_node
from automigrate.mcp_server.tools.verification_agent import run_verification_agent
from automigrate.mcp_server.tools.secrets_scan import run_secrets_scan


def verification_node(state: MigrationState) -> dict:
    current_file = state.get("current_file")
    transformed = state.get("transformed_content")
    if not current_file or not transformed:
        return {}
        
    result = run_verification_agent(current_file.file_path, transformed)
    return {"validation_results": {current_file.file_path: result}}


def secrets_scan_node(state: MigrationState) -> dict:
    current_file = state.get("current_file")
    transformed = state.get("transformed_content")
    if not current_file or not transformed:
        return {}
        
    result = run_secrets_scan(current_file.file_path, transformed)
    # A secrets scan failure is an automatic escalation
    escalated = [current_file.file_path] if not result.passed else []
    
    return {
        "validation_results": {current_file.file_path: result},
        "escalated_files": escalated
    }


def create_agent_graph() -> StateGraph:
    """Constructs and compiles the LangGraph."""
    graph = StateGraph(MigrationState)
    
    # Add nodes
    graph.add_node("planner", planner_node)
    graph.add_node("apply_ast_transform", apply_transform_node)
    graph.add_node("rag_retriever", llm_transform_node)  # LLM path acts as RAG node
    graph.add_node("verification_agent", verification_node)
    graph.add_node("static_validation", validate_node)
    graph.add_node("secrets_scan", secrets_scan_node)
    graph.add_node("run_tests", run_tests_node)
    graph.add_node("confidence_calc", confidence_calc_node)
    graph.add_node("record_dry_run", record_dry_run_node)
    graph.add_node("report_generator", report_generator_node)
    
    # Edges
    graph.set_entry_point("planner")
    
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "apply_ast_transform": "apply_ast_transform",
            "rag_retriever": "rag_retriever",
            "record_result": "record_dry_run",
            "report_generator": "report_generator",
        }
    )
    
    # Both paths converge at verification
    graph.add_edge("apply_ast_transform", "verification_agent")
    graph.add_edge("rag_retriever", "verification_agent")
    
    # Linear validation pipeline
    graph.add_edge("verification_agent", "static_validation")
    graph.add_edge("static_validation", "secrets_scan")
    
    # Conditional edge after secrets scan: if failed, escalate; else test
    def route_secrets(s):
        curr = s.get("current_file")
        if not curr: return "planner"
        res = s.get("validation_results", {}).get(curr.file_path)
        if res and res.stage == "SecretsScan" and not res.passed:
            return "planner"  # Loop back (it was already marked escalated)
        return "run_tests"

    graph.add_conditional_edges(
        "secrets_scan",
        route_secrets,
        {
            "planner": "planner",
            "run_tests": "run_tests"
        }
    )
    
    graph.add_edge("run_tests", "confidence_calc")
    graph.add_edge("confidence_calc", "planner") # Loop back to planner for next file
    
    graph.add_edge("record_dry_run", "planner") # Loop back to planner
    
    graph.add_edge("report_generator", END)
    
    return graph.compile()
