"""
Review Ticket Generator.

Outputs a markdown file summarising a failed or low-confidence migration
so a human developer can quickly review and fix it. Tickets are written
into reports/run_<id>/review/ so every artefact from one run is co-located.
"""

from __future__ import annotations

from pathlib import Path


def create_review_ticket(
    file_path: str,
    confidence_score: float,
    strategy: str,
    diff: str,
    validation_errors: list[str],
    test_logs: str,
    run_id: str = "run_unknown",
    output_dir: str | None = None,
) -> str:
    """Generate a markdown review ticket for a file.

    Args:
        run_id: Unique run identifier used to place tickets in the per-run
                directory (reports/run_<id>/review/).
        output_dir: Override the output directory (useful for tests).
    """
    if output_dir is not None:
        path = Path(output_dir)
    else:
        path = Path("reports") / run_id / "review"
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

