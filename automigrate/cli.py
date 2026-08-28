"""
CLI entry point for Reforge (AutoMigrate).

Provides commands for scanning projects, applying transforms, and running
the full agent pipeline. Supports any framework via auto-detection or
explicit --framework flag.

Usage:
  automigrate migrate ./my-project                         # auto-detect framework
  automigrate migrate ./my-project --framework angular
  automigrate migrate ./my-project --framework react --migration class_to_hooks
  automigrate dry-run ./my-project
  automigrate scan    ./my-project
  automigrate list-frameworks
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


def _resolve_framework_and_migration(
    project_path: str,
    framework: str | None,
    migration: str | None,
) -> tuple[str, str]:
    """Resolve (framework, migration_type), auto-detecting if needed."""
    from automigrate.adapters.registry import detect_framework, get_adapter

    if framework is None:
        console.print("[dim]No --framework specified — auto-detecting...[/dim]")
        adapter = detect_framework(project_path)
        if adapter is None:
            console.print(
                "[bold red]Could not auto-detect framework.[/bold red] "
                "Please specify --framework (e.g., --framework angular)."
            )
            sys.exit(1)
        framework = adapter.name
        console.print(f"[bold green]Detected:[/bold green] {adapter.display_name}")
    else:
        adapter = get_adapter(framework)

    # Resolve migration slug
    if migration is None:
        default_mig = adapter.get_default_migration()
        migration_type = default_mig.id
        console.print(
            f"[dim]No --migration specified — using default: "
            f"[bold]{default_mig.display_name}[/bold][/dim]"
        )
    else:
        # Normalise dashes to underscores (e.g., "control-flow" → "control_flow")
        migration_type = migration.replace("-", "_")
        if not adapter.get_migration(migration_type):
            supported = [m.id for m in adapter.get_migrations()]
            console.print(
                f"[bold red]Unknown migration {migration_type!r} for {framework}.[/bold red] "
                f"Supported: {supported}"
            )
            sys.exit(1)

    return framework, migration_type


def _run_agent(
    project_path: str,
    framework: str,
    migration_type: str,
    dry_run: bool,
    max_retries: int,
    output_dir: str = "reports",
) -> dict:
    """Scan the project, build a file queue, and run the LangGraph agent."""
    from automigrate.agent.graph import create_agent_graph
    from automigrate.agent.state import FileTask

    abs_path = str(Path(project_path).resolve())

    console.print(
        f"[bold cyan]Scanning[/bold cyan] {abs_path} "
        f"([bold]{framework}[/bold] / [bold]{migration_type}[/bold])…"
    )
    scan_result = scan_project(abs_path, migration_type=migration_type, framework=framework)

    if not scan_result.results:
        console.print(
            "[bold green]No migration targets found.[/bold green] "
            "Your project is already up to date!"
        )
        sys.exit(0)

    # Deduplicate: one FileTask per unique file path
    seen: dict[str, FileTask] = {}
    for r in scan_result.results:
        if r.file_path not in seen:
            seen[r.file_path] = FileTask(
                file_path=r.file_path,
                strategy="deterministic",
                complexity="simple",
            )

        task = seen[r.file_path]
        if r.classification == "ambiguous":
            task.strategy = "ambiguous"
        if r.complexity == "complex":
            task.complexity = "complex"
        elif r.complexity == "medium" and task.complexity == "simple":
            task.complexity = "medium"

    file_queue = list(seen.values())

    run_id = _build_run_id()
    console.print(
        f"[bold]Run ID:[/bold] {run_id}  |  "
        f"[bold]Files to migrate:[/bold] {len(file_queue)}  |  "
        f"[bold]Dry run:[/bold] {dry_run}"
    )

    initial_state = {
        "project_path": abs_path,
        "framework": framework,
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
        "output_dir": output_dir,
    }

    graph = create_agent_graph()

    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

    final_state = initial_state.copy()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("[cyan]Processing files...", total=len(file_queue))

        for step in graph.stream(initial_state):
            node_name = list(step.keys())[0]
            node_output = step[node_name]

            if "report" in node_output:
                final_state["report"] = node_output["report"]
            if "confidence_scores" in node_output:
                final_state.setdefault("confidence_scores", {}).update(
                    node_output["confidence_scores"]
                )

            if node_name in ("confidence_calc", "record_dry_run"):
                progress.advance(task_id)

    final_state["run_id"] = run_id
    final_state["output_dir"] = output_dir
    return final_state


def _print_summary(final_state: dict) -> None:
    """Print the live console summary after a run completes."""
    report = final_state.get("report")
    run_id = final_state.get("run_id", "unknown")
    output_dir = final_state.get("output_dir", "reports")
    run_dir = Path(output_dir) / run_id

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
                f"[bold green]Reforge run complete:[/bold green] {run_id}\n"
                f"  Framework: [bold]{final_state.get('framework', 'unknown')}[/bold] / "
                f"{final_state.get('migration_type', 'unknown')}\n"
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
@click.version_option(version="0.2.0")
def main():
    """Reforge — Universal Agentic Framework Migration System.

    Automatically detects your framework and applies AI-powered migrations.
    """
    pass


# ---------------------------------------------------------------------------
# list-frameworks
# ---------------------------------------------------------------------------

@main.command("list-frameworks")
def list_frameworks():
    """Show all supported frameworks and their available migrations."""
    from automigrate.adapters.registry import list_adapters

    table = Table(title="Supported Frameworks & Migrations", show_lines=True)
    table.add_column("Framework", style="bold cyan")
    table.add_column("Migration ID", style="magenta")
    table.add_column("Display Name")
    table.add_column("Description")
    table.add_column("Default", justify="center")

    for adapter_cls in list_adapters():
        adapter = adapter_cls()
        for migration in adapter.get_migrations():
            table.add_row(
                adapter.display_name,
                migration.id,
                migration.display_name,
                migration.description,
                "✓" if migration.default else "",
            )

    console.print(table)
    console.print(
        "\n[dim]Usage: automigrate migrate ./my-project "
        "--framework <framework> --migration <migration-id>[/dim]"
    )


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

@main.command()
@click.option("--framework", "-f", default=None, help="Framework to ingest docs for (all if omitted).")
def ingest(framework: str | None):
    """Ingest migration documentation for RAG context (for debugging/inspection)."""
    from automigrate.adapters.registry import list_adapters, get_adapter

    adapters = list_adapters()
    if framework:
        try:
            adapters = [type(get_adapter(framework))]
        except ValueError as e:
            console.print(f"[bold red]{e}[/bold red]")
            sys.exit(1)

    for adapter_cls in adapters:
        adapter = adapter_cls()
        console.print(f"[bold]{adapter.display_name}[/bold]")
        for migration in adapter.get_migrations():
            docs = adapter.get_migration_docs(migration.id)
            console.print(f"  {migration.id}: {len(docs)} chars of docs loaded")

    console.print("[bold green]Done.[/bold green] Docs are bundled with each adapter.")


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------

@main.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.option("--framework", "-f", default=None,
              help="Framework to migrate (auto-detected if not specified).")
@click.option("--migration", "-m", default=None,
              help="Migration type (default for framework if not specified).")
@click.option("--max-retries", default=3, show_default=True,
              help="Number of retry attempts per file before escalating.")
@click.option("--output-dir", default="reports", show_default=True,
              help="Directory to save reports to.")
def migrate(project_path: str, framework: str | None, migration: str | None,
            max_retries: int, output_dir: str):
    """Run the full migration pipeline (scan → transform → verify → test → report)."""
    resolved_framework, migration_type = _resolve_framework_and_migration(
        project_path, framework, migration
    )
    final_state = _run_agent(
        project_path, resolved_framework, migration_type,
        dry_run=False, max_retries=max_retries, output_dir=output_dir,
    )
    _print_summary(final_state)


# ---------------------------------------------------------------------------
# dry-run
# ---------------------------------------------------------------------------

@main.command("dry-run")
@click.argument("project_path", type=click.Path(exists=True))
@click.option("--framework", "-f", default=None, help="Framework (auto-detected if not specified).")
@click.option("--migration", "-m", default=None, help="Migration type slug.")
@click.option("--output-dir", default="reports", show_default=True,
              help="Directory to save reports to.")
def dry_run(project_path: str, framework: str | None, migration: str | None, output_dir: str):
    """Plan-only run: show what would change without modifying any files."""
    resolved_framework, migration_type = _resolve_framework_and_migration(
        project_path, framework, migration
    )
    final_state = _run_agent(
        project_path, resolved_framework, migration_type,
        dry_run=True, max_retries=0, output_dir=output_dir,
    )
    _print_summary(final_state)


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

@main.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.option("--framework", "-f", default=None, help="Framework (auto-detected if not specified).")
@click.option("--migration", "-m", default=None, help="Migration type slug.")
@click.option("--json-output", "-j", is_flag=True, help="Output raw JSON instead of table.")
def scan(project_path: str, framework: str | None, migration: str | None, json_output: bool):
    """Scan a project for migration targets (classification only, no transforms)."""
    resolved_framework, migration_type = _resolve_framework_and_migration(
        project_path, framework, migration
    )
    result = scan_project(project_path, migration_type=migration_type, framework=resolved_framework)

    if json_output:
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    console.print(
        Panel(
            f"[bold]Project:[/bold] {result.project_path}\n"
            f"[bold]Framework:[/bold] {result.framework}\n"
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
# transform (single-file, Angular-specific fine-grained control)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--pattern", "-p", default=None, help="Specific pattern ID to apply.")
@click.option("--write", "-w", is_flag=True, help="Write changes back to the file.")
@click.option("--diff-only", "-d", is_flag=True, help="Show only the diff.")
def transform(file_path: str, pattern: str | None, write: bool, diff_only: bool):
    """Apply deterministic transforms to a single file (Angular control-flow)."""
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
# report
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
        status = (
            "[green]✅ Approved[/green]"
            if not f.get("human_review_required")
            else "[yellow]⚠️  Review[/yellow]"
        )
        table.add_row(
            f["file"], f["strategy"],
            str(f["confidence_score"]),
            str(f.get("retry_count", 0)),
            status,
        )

    console.print(table)
    console.print(
        Panel(
            f"[bold]Framework:[/bold] {data.get('framework', 'n/a')}\n"
            f"[bold]Migration:[/bold] {data.get('migration_type', 'n/a')}\n"
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
