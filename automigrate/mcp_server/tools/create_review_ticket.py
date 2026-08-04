"""
Review Ticket Generator.

Outputs a markdown file summarizing a failed or low-confidence migration
so a human developer can quickly review and fix it.
"""

from __future__ import annotations

import json
from pathlib import Path


def create_review_ticket(
    file_path: str,
    confidence_score: float,
    strategy: str,
    diff: str,
    validation_errors: list[str],
    test_logs: str,
    output_dir: str = "reports/review_tickets"
) -> str:
    """Generate a markdown review ticket for a file."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    
    safe_name = file_path.replace("/", "_").replace("\\", "_")
    ticket_path = path / f"REVIEW_{safe_name}.md"
    
    ticket_content = f"""# Migration Review Required: `{file_path}`

**Confidence Score:** {confidence_score}/100
**Strategy Used:** {strategy}

## Validation Errors
{chr(10).join(f"- {e}" for e in validation_errors) if validation_errors else "None"}

## Test Output
```text
{test_logs or 'No tests run / passed.'}
```

## Proposed Diff
```diff
{diff or 'No changes proposed.'}
```
"""
    ticket_path.write_text(ticket_content, encoding="utf-8")
    return str(ticket_path)
