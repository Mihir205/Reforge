"""
apply_ast_transform — MCP tool that applies deterministic AST transforms to a file.

Takes a file path and a pattern ID (or "all" to apply every applicable rule),
runs the matching deterministic transform, and returns the transformed content
along with a unified diff.

Design note: The transform engine is abstracted behind the RuleRegistry. This
tool doesn't care whether the underlying engine is regex-based, ast-grep,
jscodeshift, or tree-sitter — it just calls rule.transform_fn(match, template).
"""

from __future__ import annotations

import difflib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from automigrate.transforms.base_rules import RuleRegistry, TransformRule


@dataclass
class TransformResult:
    """Result of applying transforms to a single file."""

    file_path: str
    original_content: str
    transformed_content: str
    patterns_applied: list[str]
    patterns_skipped_ambiguous: list[str]
    diff: str
    success: bool
    error: str | None = None

    @property
    def was_modified(self) -> bool:
        return self.original_content != self.transformed_content

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "patterns_applied": self.patterns_applied,
            "patterns_skipped_ambiguous": self.patterns_skipped_ambiguous,
            "was_modified": self.was_modified,
            "diff": self.diff,
            "success": self.success,
            "error": self.error,
        }


def apply_ast_transform(
    file_path: str,
    pattern_id: str | None = None,
    rule_registry: RuleRegistry | None = None,
    write: bool = False,
) -> TransformResult:
    """Apply deterministic AST transforms to a file.

    Args:
        file_path: Path to the template file.
        pattern_id: Specific pattern to apply (e.g., "ngif_simple").
                    If None, all applicable deterministic rules are applied.
        rule_registry: Optional custom RuleRegistry.
        write: If True, write the transformed content back to the file.
               If False (default), return the result without modifying the file.

    Returns:
        A TransformResult with the original content, transformed content,
        list of applied patterns, and a unified diff.
    """
    if rule_registry is None:
        # Default: Angular registry for backwards compatibility with the CLI 'transform' command
        from automigrate.transforms.angular_control_flow.rules import registry as _ang_reg
        rule_registry = _ang_reg
    reg = rule_registry
    filepath = Path(file_path)

    try:
        original = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return TransformResult(
            file_path=str(filepath),
            original_content="",
            transformed_content="",
            patterns_applied=[],
            patterns_skipped_ambiguous=[],
            diff="",
            success=False,
            error=str(e),
        )

    transformed = original
    applied: list[str] = []
    skipped: list[str] = []

    # We apply transforms iteratively because each transform changes the
    # template, so we need to re-scan after each application.
    max_iterations = 50  # safety limit
    for _ in range(max_iterations):
        matches = reg.find_matches(transformed)
        if not matches:
            break

        applied_in_pass = False
        for rule, match in matches:
            # If a specific pattern was requested, skip others
            if pattern_id and rule.id.value != pattern_id:
                continue

            if not rule.is_deterministic:
                if rule.id.value not in skipped:
                    skipped.append(rule.id.value)
                continue

            # Apply the transform
            assert rule.transform_fn is not None
            try:
                replacement = rule.transform_fn(match, transformed)
            except Exception as e:
                return TransformResult(
                    file_path=str(filepath),
                    original_content=original,
                    transformed_content=transformed,
                    patterns_applied=applied,
                    patterns_skipped_ambiguous=skipped,
                    diff="",
                    success=False,
                    error=f"Transform {rule.id.value} failed: {e}",
                )

            # Replace the matched region
            transformed = transformed[: match.start()] + replacement + transformed[match.end() :]
            applied.append(rule.id.value)
            applied_in_pass = True
            break  # restart scanning from the beginning after each transform

        if not applied_in_pass:
            break

    # Also clean up orphaned ng-template blocks whose references have been inlined
    transformed = _cleanup_orphaned_ng_templates(transformed, original)

    # Generate unified diff
    diff = _generate_diff(original, transformed, str(filepath))

    if write and transformed != original:
        shutil.copy2(filepath, filepath.with_suffix(filepath.suffix + ".bak"))
        filepath.write_text(transformed, encoding="utf-8")

    return TransformResult(
        file_path=str(filepath),
        original_content=original,
        transformed_content=transformed,
        patterns_applied=applied,
        patterns_skipped_ambiguous=skipped,
        diff=diff,
        success=True,
    )


def apply_ast_transform_to_string(
    template: str,
    pattern_id: str | None = None,
    rule_registry: RuleRegistry | None = None,
) -> TransformResult:
    """Apply transforms to a template string (no file I/O).

    Useful for testing and for the agent pipeline where content is
    passed in-memory.
    """
    if rule_registry is None:
        from automigrate.transforms.angular_control_flow.rules import registry as _ang_reg
        rule_registry = _ang_reg
    reg = rule_registry
    original = template
    transformed = original
    applied: list[str] = []
    skipped: list[str] = []

    max_iterations = 50
    for _ in range(max_iterations):
        matches = reg.find_matches(transformed)
        if not matches:
            break

        applied_in_pass = False
        for rule, match in matches:
            if pattern_id and rule.id.value != pattern_id:
                continue

            if not rule.is_deterministic:
                if rule.id.value not in skipped:
                    skipped.append(rule.id.value)
                continue

            assert rule.transform_fn is not None
            replacement = rule.transform_fn(match, transformed)
            transformed = transformed[: match.start()] + replacement + transformed[match.end() :]
            applied.append(rule.id.value)
            applied_in_pass = True
            break

        if not applied_in_pass:
            break

    transformed = _cleanup_orphaned_ng_templates(transformed, original)
    diff = _generate_diff(original, transformed, "<string>")

    return TransformResult(
        file_path="<string>",
        original_content=original,
        transformed_content=transformed,
        patterns_applied=applied,
        patterns_skipped_ambiguous=skipped,
        diff=diff,
        success=True,
    )


def _cleanup_orphaned_ng_templates(transformed: str, original: str) -> str:
    """Remove <ng-template #ref> blocks that were inlined by *ngIf else transforms.

    We only remove templates whose #ref name appeared in a *ngIf else/then
    directive in the original but no longer appear in the transformed output
    as a reference.
    """
    # Find all ng-template refs in the original that were part of *ngIf else/then
    ref_pattern = re.compile(r'\*ngIf="[^"]*(?:else|then)\s+(\w+)[^"]*"', re.DOTALL)
    inlined_refs = set(ref_pattern.findall(original))

    for ref_name in inlined_refs:
        # Remove the ng-template block
        template_pattern = re.compile(
            rf'\s*<ng-template\s+#{re.escape(ref_name)}\s*>.*?</ng-template>\s*',
            re.DOTALL,
        )
        transformed = template_pattern.sub("\n", transformed)

    return transformed


def _generate_diff(original: str, transformed: str, filepath: str) -> str:
    """Generate a unified diff between original and transformed content."""
    original_lines = original.splitlines(keepends=True)
    transformed_lines = transformed.splitlines(keepends=True)
    diff_lines = difflib.unified_diff(
        original_lines,
        transformed_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        lineterm="",
    )
    return "".join(diff_lines)
