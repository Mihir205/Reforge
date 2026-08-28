"""
Confidence Calculator Node.

Calculates an overall confidence score for a file transformation based on
the signals collected during the validation and testing phases.
"""

from __future__ import annotations

from automigrate.agent.state import MigrationState, ValidationResult

import os

# Thresholds — exported so graph.py can use them for routing decisions.
AUTO_APPROVE_THRESHOLD = float(os.getenv("CONFIDENCE_AUTO_APPROVE_THRESHOLD", "90.0"))
QUICK_REVIEW_THRESHOLD = float(os.getenv("CONFIDENCE_QUICK_REVIEW_THRESHOLD", "70.0"))


def calculate_confidence(strategy: str, validation_results: dict | ValidationResult, test_passed: bool) -> float:
    """Calculate confidence based on validation signals."""
    score = 0.0
    
    # 1. Strategy used
    if strategy == "deterministic":
        score += 40.0
        
    # 2. Validation results
    # If it's a single ValidationResult, just check its passed status
    if hasattr(validation_results, "passed"):
        if validation_results.passed:
            score += 40.0
    else:
        # AST
        ast_res = validation_results.get("AST")
        if ast_res and ast_res.passed:
            score += 10.0
            
        # TypeCheck
        tc_res = validation_results.get("TypeCheck")
        if tc_res and tc_res.passed:
            score += 15.0
            
        # Lint
        lint_res = validation_results.get("Lint")
        if lint_res and lint_res.passed:
            score += 10.0
            
        # Verification Agent
        va_res = validation_results.get("VerificationAgent")
        if va_res and va_res.passed:
            score += 5.0
            
    # 3. Test Suite
    if test_passed:
        score += 20.0
        
    return score


def confidence_calc_node(state: MigrationState) -> dict:
    """Node that calculates confidence and sorts files."""
    current_file = state.get("current_file")
    if not current_file:
        return {}
        
    # Extract validation and test results
    validation_results = state.get("validation_results", {}).get(current_file.file_path, {})
    test_result = state.get("test_results", {}).get(current_file.file_path)
    test_passed = test_result.passed if test_result else False
    
    # Check if it was already escalated due to secrets
    if current_file.file_path in state.get("escalated_files", []):
        return {"confidence_scores": {current_file.file_path: 0.0}}
        
    score = calculate_confidence(
        strategy=current_file.strategy or "ambiguous",
        validation_results=validation_results,
        test_passed=test_passed
    )
    
    completed = [current_file.file_path] if score >= AUTO_APPROVE_THRESHOLD else []
    escalated = [current_file.file_path] if score < AUTO_APPROVE_THRESHOLD else []
    
    return {
        "confidence_scores": {current_file.file_path: score},
        "completed_files": completed,
        "escalated_files": escalated
    }
