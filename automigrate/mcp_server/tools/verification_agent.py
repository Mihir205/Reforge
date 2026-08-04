"""
Verification Agent Tool.

Lightweight rule-based checker that runs before static validation to catch
obvious structural issues, malformed syntax, or deprecated API residues
after an LLM transformation.
"""

from __future__ import annotations

from automigrate.agent.state import ValidationResult


def run_verification_agent(file_path: str, transformed_content: str) -> ValidationResult:
    """Run verification rules on the transformed content.
    
    Checks for:
    - Missing or unbalanced brackets/braces
    - Leftover *ngIf or *ngFor that the LLM failed to convert
    """
    errors = []
    
    # Check 1: Incomplete transformations
    if "*ngIf=" in transformed_content or "*ngFor=" in transformed_content:
        errors.append("Legacy structural directives still present.")
        
    # Check 2: Unbalanced braces for new control flow
    if transformed_content.count("{") != transformed_content.count("}"):
        errors.append("Unbalanced braces detected.")
        
    # Check 3: Malformed @if syntax (basic heuristic)
    if "@if" in transformed_content and "@if (" not in transformed_content:
        errors.append("Malformed @if syntax, missing parentheses.")
        
    passed = len(errors) == 0
    return ValidationResult(passed=passed, stage="VerificationAgent", errors=errors)
