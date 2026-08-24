"""
CLI entry point for AutoMigrate.

Provides commands for scanning projects, applying transforms, and running
the full agent pipeline.

Usage:
  automigrate migrate ./my-project --framework angular --migration control-flow
  automigrate dry-run ./my-project
  automigrate scan    ./my-project
  automigrate report  ./reports/run_2026_08_24_2209
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

load_dotenv()  # Load .env so OLLAMA_MODEL etc. are available

from automigrate.mcp_server.tools.scan_project import scan_project
from automigrate.mcp_server.tools.apply_ast_transform import apply_ast_transform

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_run_id() -> str:
    return f"run_{datetime.now().strftime('%Y_%m_%d_%H%M')}"


def _run_agent(project_path: str, migration_type: str, dry_run: bool, max_retries: int) -> dict:
    """Scan the project, build a file queue, and run the LangGraph agent."""
    from automigrate.agent.graph import create_agent_graph
    from automigrate.agent.state import FileTask

    abs_path = str(Path(project_path).resolve())

    console.print(f"[bold cyan]Scanning[/bold cyan] {abs_path} for [bold]{migration_type}[/bold] targets…")
    scan_result = scan_project(abs_path, migration_type)

    if not scan_result.results:
        console.print("[bold green]No migration targets found.[/bold green] Your project is already up to date!")
        sys.exit(0)

    # Deduplicate: one FileTask per unique file path
    seen: dict[str, FileTask] = {}
    for r in scan_result.results:
        if r.file_path not in seen:
            seen[r.file_path] = FileTask(file_path=r.file_path)
    file_queue = list(seen.values())

    run_id = _build_run_id()
    console.print(
        f"[bold]Run ID:[/bold] {run_id}  |  "
        f"[bold]Files to migrate:[/bold] {len(file_queue)}  |  "
        f"[bold]Dry run:[/bold] {dry_run}"
    )

    initial_state = {
        "project_path": abs_path,
        "migration_type": migration_type,
        "dry_run": dry_run,
        "max_retries": max_retries,
        "run_id": run_id,
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

    graph = create_agent_graph()
    final_state = graph.invoke(initial_state)
    return final_state


def _print_summary(final_state: dict) -> None:
    """Print the live console summary after a run completes."""
    report = final_state.get("report")
    run_id = final_state.get("run_id", "unknown")
    run_dir = Path("reports") / run_id

    if report:
        completed = report.successful_files
        escalated = report.escalated_files
        total = report.total_files
        avg_conf = 0.0
        scores = final_state.get("confidence_scores", {})
        if scores:
            avg_conf = sum(scores.values()) / len(scores)

        console.print(
            Panel(
                f"[bold green]AutoMigrate run complete:[/bold green] {run_id}\n"
                f"  {total}  files processed\n"
                f"  [bold green]{completed}[/bold green]  auto-approved   "
                f"(avg confidence {avg_conf:.0f})\n"
                f"  [bold yellow]{escalated}[/bold yellow]  flagged for review\n"
                f"  Full report: [link={run_dir}/report.md]{run_dir}/report.md[/link]\n"
                f"  JSON:        [link={run_dir}/report.json]{run_dir}/report.json[/link]",
                title="[bold cyan]Migration Complete[/bold cyan]",
                expand=False,
            )
        )
    else:
        console.print("[yellow]Run finished but no report was generated.[/yellow]")


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(version="0.1.0")
def main():
    """AutoMigrate — Agentic Framework Migration & Validation System."""
    pass


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------

@main.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.option("--framework", "-f", default="angular", show_default=True,
              help="Target framework (currently: angular).")
@click.option("--migration", "-m", default="control-flow", show_default=True,
              help="Migration type slug (maps to angular_control_flow, etc.).")
@click.option("--max-retries", default=3, show_default=True,
              help="Number of retry attempts per file before escalating.")
def migrate(project_path: str, framework: str, migration: str, max_retries: int):
    """Run the full migration pipeline (scan → transform → verify → test → report)."""
    migration_type = f"{framework}_{migration.replace('-', '_')}"
    final_state = _run_agent(project_path, migration_type, dry_run=False, max_retries=max_retries)
    _print_summary(final_state)


# ---------------------------------------------------------------------------
# dry-run
# ---------------------------------------------------------------------------

@main.command("dry-run")
@click.argument("project_path", type=click.Path(exists=True))
@click.option("--framework", "-f", default="angular", show_default=True,
              help="Target framework.")
@click.option("--migration", "-m", default="control-flow", show_default=True,
              help="Migration type slug.")
def dry_run(project_path: str, framework: str, migration: str):
    """Plan-only run: show what would change without modifying any files."""
    migration_type = f"{framework}_{migration.replace('-', '_')}"
    final_state = _run_agent(project_path, migration_type, dry_run=True, max_retries=0)
    _print_summary(final_state)


# ---------------------------------------------------------------------------
# scan (fine-grained inspection)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.option("--migration-type", "-m", default="angular_control_flow", show_default=True,
              help="Migration type to scan for.")
@click.option("--json-output", "-j", is_flag=True, help="Output raw JSON instead of table.")
def scan(project_path: str, migration_type: str, json_output: bool):
    """Scan a project for migration targets (classification only, no transforms)."""
    result = scan_project(project_path, migration_type)

    if json_output:
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    console.print(
        Panel(
            f"[bold]Project:[/bold] {result.project_path}\n"
            f"[bold]Migration:[/bold] {result.migration_type}\n"
            f"[bold]Files scanned:[/bold] {result.total_files_scanned}\n"
            f"[bold]Patterns found:[/bold] {result.total_patterns_found}\n"
            f"[bold green]Deterministic:[/bold green] {result.deterministic_count}\n"
            f"[bold yellow]Ambiguous:[/bold yellow] {result.ambiguous_count}",
            title="[bold cyan]Scan Results[/bold cyan]",
            expand=False,
        )
    )

    if result.results:
        table = Table(title="Detected Patterns", show_lines=True)
        table.add_column("File", style="cyan", no_wrap=True)
        table.add_column("Line", justify="right")
        table.add_column("Pattern", style="magenta")
        table.add_column("Class", style="bold")
        table.add_column("Complexity")
        table.add_column("Snippet", max_width=60)

        for r in result.results:
            cls_style = "green" if r.classification == "deterministic" else "yellow"
            table.add_row(
                r.file_path,
                str(r.line),
                r.pattern_id,
                f"[{cls_style}]{r.classification}[/{cls_style}]",
                r.complexity,
                r.snippet[:60],
            )

        console.print(table)


# ---------------------------------------------------------------------------
# transform (single-file fine-grained control)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--pattern", "-p", default=None, help="Specific pattern ID to apply.")
@click.option("--write", "-w", is_flag=True, help="Write changes back to the file.")
@click.option("--diff-only", "-d", is_flag=True, help="Show only the diff.")
def transform(file_path: str, pattern: str | None, write: bool, diff_only: bool):
    """Apply deterministic transforms to a single file."""
    result = apply_ast_transform(file_path, pattern_id=pattern, write=write)

    if not result.success:
        console.print(f"[bold red]Error:[/bold red] {result.error}")
        sys.exit(1)

    if diff_only:
        if result.diff:
            console.print(Syntax(result.diff, "diff", theme="monokai"))
        else:
            console.print("[dim]No changes.[/dim]")
        return

    console.print(
        Panel(
            f"[bold]File:[/bold] {result.file_path}\n"
            f"[bold]Modified:[/bold] {result.was_modified}\n"
            f"[bold green]Applied:[/bold green] {', '.join(result.patterns_applied) or 'none'}\n"
            f"[bold yellow]Skipped (ambiguous):[/bold yellow] "
            f"{', '.join(result.patterns_skipped_ambiguous) or 'none'}\n"
            f"[bold]Written to disk:[/bold] {write}",
            title="[bold cyan]Transform Results[/bold cyan]",
            expand=False,
        )
    )

    if result.diff:
        console.print("\n[bold]Diff:[/bold]")
        console.print(Syntax(result.diff, "diff", theme="monokai"))


# ---------------------------------------------------------------------------
# report (re-render a past run)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("run_dir", type=click.Path(exists=True))
def report(run_dir: str):
    """Re-render a past run's report.json as markdown and print it to the console."""
    json_path = Path(run_dir) / "report.json"
    if not json_path.exists():
        console.print(f"[bold red]No report.json found in {run_dir}[/bold red]")
        sys.exit(1)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    summary = data.get("summary", {})

    table = Table(title=f"Report: {data.get('run_id', run_dir)}", show_lines=True)
    table.add_column("File", style="cyan")
    table.add_column("Strategy")
    table.add_column("Confidence", justify="right")
    table.add_column("Retries", justify="right")
    table.add_column("Status", style="bold")

    for f in data.get("files", []):
        status = "[green]✅ Approved[/green]" if not f.get("human_review_required") else "[yellow]⚠️  Review[/yellow]"
        table.add_row(
            f["file"], f["strategy"],
            str(f["confidence_score"]),
            str(f.get("retry_count", 0)),
            status,
        )

    console.print(table)
    console.print(
        Panel(
            f"[bold]Total:[/bold] {summary.get('total_files', 0)}\n"
            f"[bold green]Auto-approved:[/bold green] {summary.get('auto_approved', 0)}\n"
            f"[bold yellow]Flagged:[/bold yellow] {summary.get('flagged_for_review', 0)}\n"
            f"[bold]Avg confidence:[/bold] {summary.get('avg_confidence', 0)}\n"
            f"[bold]Time saved:[/bold] {summary.get('time_saved_estimate_hours', 0)} h",
            title="[bold cyan]Summary[/bold cyan]",
            expand=False,
        )
    )


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

@main.command()
@click.argument("project_path", type=click.Path(exists=True))
def rollback(project_path: str):
    """Rollback the last migration run using generated .bak files."""
    import os
    import shutil

    base = Path(project_path)
    count = 0
    for bak_file in base.rglob("*.bak"):
        original_file = bak_file.with_suffix("")
        shutil.copy2(bak_file, original_file)
        os.remove(bak_file)
        count += 1

    console.print(f"[bold green]Rollback complete.[/bold green] Restored {count} files.")


if __name__ == "__main__":
    main()

