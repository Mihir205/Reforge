"""
CLI entry point for AutoMigrate.

Provides commands for scanning projects, applying transforms, and running
the full agent pipeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from automigrate.mcp_server.tools.scan_project import scan_project
from automigrate.mcp_server.tools.apply_ast_transform import apply_ast_transform

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """AutoMigrate — Agentic Framework Migration & Validation System."""
    pass


@main.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.option(
    "--migration-type",
    "-m",
    default="angular_control_flow",
    help="Migration type to scan for.",
)
@click.option("--json-output", "-j", is_flag=True, help="Output raw JSON instead of table.")
def scan(project_path: str, migration_type: str, json_output: bool):
    """Scan a project for migration targets."""
    result = scan_project(project_path, migration_type)

    if json_output:
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    # Pretty-print with Rich
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


@main.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--pattern", "-p", default=None, help="Specific pattern ID to apply.")
@click.option("--write", "-w", is_flag=True, help="Write changes back to the file.")
@click.option("--diff-only", "-d", is_flag=True, help="Show only the diff.")
def transform(file_path: str, pattern: str | None, write: bool, diff_only: bool):
    """Apply deterministic transforms to a file."""
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
