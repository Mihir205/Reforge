"""
Secrets Scanning Gate.

Runs before validation/tests to ensure the LLM didn't hallucinate or leak
credentials (e.g., API keys, passwords) into the source code.
"""

from __future__ import annotations

import re
from automigrate.agent.state import ValidationResult


def run_secrets_scan(file_path: str, transformed_content: str) -> ValidationResult:
    """Run a fast regex-based secrets scan.
    
    In a real environment, this would shell out to `gitleaks detect` or `trufflehog`.
    For this project, we simulate with common credential regex patterns.
    """
    errors = []
    
    # Simple simulated patterns for testing
    patterns = {
        "AWS Access Key": r"AKIA[0-9A-Z]{16}",
        "Generic Secret": r"secret(?:_key)?\s*=\s*['\"][A-Za-z0-9_-]{20,}['\"]"
    }
    
    for name, pattern in patterns.items():
        if re.search(pattern, transformed_content, re.IGNORECASE):
            errors.append(f"Secret detected: {name}")
            
    passed = len(errors) == 0
    return ValidationResult(passed=passed, stage="SecretsScan", errors=errors)
