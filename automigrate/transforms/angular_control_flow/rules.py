"""
Angular Control Flow Transform Rules.

Deterministic regex-based transforms for Angular legacy structural directives
(*ngIf, *ngFor, *ngSwitch) to the new Control Flow syntax (@if, @for, @switch).

Each rule is a dataclass defining a pattern to match and a function to produce
the replacement. Rules are applied outermost-first via recursive descent so that
nested directives are handled correctly.

Design note: This module deliberately uses regex rather than a full AST parser
because Angular templates are not standard HTML (they contain {{ }}, pipes, etc.)
and third-party Angular template AST libraries are heavy dependencies. For the
deterministic path we need reliable pattern matching on well-known directive forms;
the regex approach handles the documented syntax patterns while the LLM fallback
(Phase 3) handles truly ambiguous cases.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Callable

# Re-export the generic base classes so existing imports keep working.
from automigrate.transforms.base_rules import (  # noqa: F401
    PatternComplexity,
    RuleRegistry,
    TransformRule,
)


class PatternId(str, Enum):
    """Unique identifiers for each supported Angular transform pattern."""

    NGIF_SIMPLE = "ngif_simple"
    NGIF_ELSE = "ngif_else"
    NGIF_THEN_ELSE = "ngif_then_else"
    NGFOR_SIMPLE = "ngfor_simple"
    NGFOR_TRACKBY = "ngfor_trackby"
    NGFOR_LOCALS = "ngfor_locals"
    NGSWITCH = "ngswitch"
    NGIF_ASYNC_PIPE = "ngif_async_pipe"  # ambiguous


# =============================================================================
#  Transform functions
# =============================================================================


def _transform_ngif_simple(match: re.Match, _template: str) -> str:
    """*ngIf="cond" → @if (cond) { <element>...</element> }"""
    condition = match.group("condition").strip()
    tag = match.group("tag")
    attrs = match.group("attrs") or ""
    inner = match.group("inner")
    # Remove the *ngIf directive from the attributes
    attrs = _remove_directive(attrs, r'\*ngIf="[^"]*"')
    attrs_str = f" {attrs.strip()}" if attrs.strip() else ""
    return f"@if ({condition}) {{\n  <{tag}{attrs_str}>{inner}</{tag}>\n}}"


def _transform_ngif_else(match: re.Match, template: str) -> str:
    """*ngIf="cond; else tmpl" → @if (cond) { ... } @else { ... }

    Also removes the referenced <ng-template #tmpl>...</ng-template>.
    """
    condition = match.group("condition").strip()
    else_ref = match.group("else_ref").strip()
    tag = match.group("tag")
    attrs = match.group("attrs") or ""
    inner = match.group("inner")

    attrs = _remove_directive(attrs, r'\*ngIf="[^"]*"')
    attrs_str = f" {attrs.strip()}" if attrs.strip() else ""

    # Find the referenced ng-template
    ng_template_content = _extract_ng_template(template, else_ref)

    return (
        f"@if ({condition}) {{\n"
        f"  <{tag}{attrs_str}>{inner}</{tag}>\n"
        f"}} @else {{\n"
        f"  {ng_template_content}\n"
        f"}}"
    )


def _transform_ngif_then_else(match: re.Match, template: str) -> str:
    """*ngIf="cond; then thenTpl; else elseTpl" → @if (cond) { ... } @else { ... }"""
    condition = match.group("condition").strip()
    then_ref = match.group("then_ref").strip()
    else_ref = match.group("else_ref").strip()

    then_content = _extract_ng_template(template, then_ref)
    else_content = _extract_ng_template(template, else_ref)

    return (
        f"@if ({condition}) {{\n"
        f"  {then_content}\n"
        f"}} @else {{\n"
        f"  {else_content}\n"
        f"}}"
    )


def _transform_ngfor_simple(match: re.Match, _template: str) -> str:
    """*ngFor="let item of items" → @for (item of items; track item) { ... }"""
    item_var = match.group("item").strip()
    collection = match.group("collection").strip()
    tag = match.group("tag")
    attrs = match.group("attrs") or ""
    inner = match.group("inner")

    attrs = _remove_directive(attrs, r'\*ngFor="[^"]*"')
    attrs_str = f" {attrs.strip()}" if attrs.strip() else ""

    return (
        f"@for ({item_var} of {collection}; track {item_var}) {{\n"
        f"  <{tag}{attrs_str}>{inner}</{tag}>\n"
        f"}}"
    )


def _transform_ngfor_trackby(match: re.Match, _template: str) -> str:
    """*ngFor="let item of items; let i = index; trackBy: fn" →
    @for (item of items; track fn($index, item); let i = $index) { ... }"""
    item_var = match.group("item").strip()
    collection = match.group("collection").strip()
    rest = match.group("rest").strip()
    tag = match.group("tag")
    attrs = match.group("attrs") or ""
    inner = match.group("inner")

    attrs = _remove_directive(attrs, r'\*ngFor="[^"]*"')
    attrs_str = f" {attrs.strip()}" if attrs.strip() else ""

    # Parse trackBy and local variables from `rest`
    track_expr, local_vars = _parse_ngfor_rest(rest, item_var)

    locals_str = ""
    if local_vars:
        locals_str = "; " + "; ".join(local_vars)

    return (
        f"@for ({item_var} of {collection}; track {track_expr}{locals_str}) {{\n"
        f"  <{tag}{attrs_str}>{inner}</{tag}>\n"
        f"}}"
    )


# =============================================================================
#  Helper functions
# =============================================================================

# Maps legacy NgFor local variable names → new Control Flow names
_NGFOR_LOCAL_MAP = {
    "index": "$index",
    "first": "$first",
    "last": "$last",
    "even": "$even",
    "odd": "$odd",
    "count": "$count",
}


def _remove_directive(attrs: str, directive_pattern: str) -> str:
    """Remove a structural directive from an attribute string."""
    return re.sub(directive_pattern, "", attrs).strip()


def _extract_ng_template(template: str, ref_name: str) -> str:
    """Extract the inner content of <ng-template #refName>...</ng-template>."""
    pattern = re.compile(
        rf'<ng-template\s+#{re.escape(ref_name)}\s*>(.*?)</ng-template>',
        re.DOTALL,
    )
    m = pattern.search(template)
    if m:
        return m.group(1).strip()
    return f"<!-- WARNING: ng-template #{ref_name} not found -->"


def _parse_ngfor_rest(rest: str, item_var: str) -> tuple[str, list[str]]:
    """Parse the '; ...' portion of an *ngFor, extracting trackBy and local vars.

    Returns (track_expression, [local_var_assignments]).
    """
    track_expr = item_var  # default: track by the item itself
    local_vars: list[str] = []

    # Split on semicolons, handling each clause
    clauses = [c.strip() for c in rest.split(";") if c.strip()]
    for clause in clauses:
        # trackBy: fnName
        track_match = re.match(r"trackBy:\s*(\w+)", clause)
        if track_match:
            fn_name = track_match.group(1)
            track_expr = f"{fn_name}($index, {item_var})"
            continue

        # let varName = localName
        let_match = re.match(r"let\s+(\w+)\s*=\s*(\w+)", clause)
        if let_match:
            var_name = let_match.group(1)
            local_name = let_match.group(2)
            new_local = _NGFOR_LOCAL_MAP.get(local_name, f"${local_name}")
            local_vars.append(f"let {var_name} = {new_local}")
            continue

    return track_expr, local_vars


# =============================================================================
#  Rule definitions
# =============================================================================

# Shared pattern fragments
_TAG = r"(?P<tag>[a-zA-Z][\w-]*)"
_INNER = r"(?P<inner>.*?)"

# Structural directive in opening tag pattern builder
def _make_element_pattern(directive_regex: str) -> str:
    """Build a regex that matches <tag *directive ...>...</tag>.

    The directive_regex is inserted as part of the attribute set.
    Captures: tag, attrs (other attributes), inner (element content), and
    whatever named groups are inside directive_regex.
    """
    return (
        rf"<{_TAG}"
        rf"(?P<attrs>[^>]*?)\s*{directive_regex}(?P=attrs_end)?"
        rf"\s*>"
        rf"{_INNER}"
        rf"</(?P=tag)>"
    )


# Because the generic element pattern is tricky to get right with arbitrary
# attribute ordering, we use targeted patterns per-directive.

_RULES: list[TransformRule] = [
    # --- *ngIf (then/else form) — must be matched before simpler forms ---
    TransformRule(
        id=PatternId.NGIF_THEN_ELSE,
        description="*ngIf with then and else template references",
        complexity=PatternComplexity.MEDIUM,
        detect_pattern=(
            r'<(?P<tag>[a-zA-Z][\w-]*)'
            r'(?P<attrs>[^>]*?)'
            r'\*ngIf="(?P<condition>[^";]+);\s*then\s+(?P<then_ref>\w+);\s*else\s+(?P<else_ref>\w+)"'
            r'(?P<attrs2>[^>]*?)'
            r'>'
            r'(?P<inner>.*?)'
            r'</(?P=tag)>'
        ),
        transform_fn=_transform_ngif_then_else,
    ),
    # --- *ngIf with else ---
    TransformRule(
        id=PatternId.NGIF_ELSE,
        description="*ngIf with else template reference",
        complexity=PatternComplexity.MEDIUM,
        detect_pattern=(
            r'<(?P<tag>[a-zA-Z][\w-]*)'
            r'(?P<attrs>[^>]*?)'
            r'\*ngIf="(?P<condition>[^";]+);\s*else\s+(?P<else_ref>\w+)"'
            r'(?P<attrs2>[^>]*?)'
            r'>'
            r'(?P<inner>.*?)'
            r'</(?P=tag)>'
        ),
        transform_fn=_transform_ngif_else,
    ),
    # --- *ngIf with async pipe (AMBIGUOUS) ---
    TransformRule(
        id=PatternId.NGIF_ASYNC_PIPE,
        description="*ngIf with async pipe alias — needs LLM fallback",
        complexity=PatternComplexity.AMBIGUOUS,
        detect_pattern=(
            r'<(?P<tag>[a-zA-Z][\w-]*)'
            r'(?P<attrs>[^>]*?)'
            r'\*ngIf="(?P<condition>[^"]*\|\s*async\s+as\s+\w+[^"]*)"'
            r'(?P<attrs2>[^>]*?)'
            r'>'
            r'(?P<inner>.*?)'
            r'</(?P=tag)>'
        ),
        transform_fn=None,  # Ambiguous — routed to LLM
    ),
    # --- Simple *ngIf ---
    TransformRule(
        id=PatternId.NGIF_SIMPLE,
        description="Simple *ngIf condition",
        complexity=PatternComplexity.SIMPLE,
        detect_pattern=(
            r'<(?P<tag>[a-zA-Z][\w-]*)'
            r'(?P<attrs>[^>]*?)'
            r'\*ngIf="(?P<condition>(?!.*\|\s*async\s+as\s+\w+)[^"]+)"'
            r'(?P<attrs2>[^>]*?)'
            r'>'
            r'(?P<inner>.*?)'
            r'</(?P=tag)>'
        ),
        transform_fn=_transform_ngif_simple,
    ),
    # --- *ngFor with trackBy or local variables ---
    TransformRule(
        id=PatternId.NGFOR_TRACKBY,
        description="*ngFor with trackBy and/or local variable bindings",
        complexity=PatternComplexity.MEDIUM,
        detect_pattern=(
            r'<(?P<tag>[a-zA-Z][\w-]*)'
            r'(?P<attrs>[^>]*?)'
            r'\*ngFor="let\s+(?P<item>\w+)\s+of\s+(?P<collection>[\w.]+);\s*(?P<rest>[^"]+)"'
            r'(?P<attrs2>[^>]*?)'
            r'>'
            r'(?P<inner>.*?)'
            r'</(?P=tag)>'
        ),
        transform_fn=_transform_ngfor_trackby,
    ),
    # --- Simple *ngFor ---
    TransformRule(
        id=PatternId.NGFOR_SIMPLE,
        description="Simple *ngFor without trackBy",
        complexity=PatternComplexity.SIMPLE,
        detect_pattern=(
            r'<(?P<tag>[a-zA-Z][\w-]*)'
            r'(?P<attrs>[^>]*?)'
            r'\*ngFor="let\s+(?P<item>\w+)\s+of\s+(?P<collection>[\w.]+)"'
            r'(?P<attrs2>[^>]*?)'
            r'>'
            r'(?P<inner>.*?)'
            r'</(?P=tag)>'
        ),
        transform_fn=_transform_ngfor_simple,
    ),
    # --- *ngSwitch ---
    TransformRule(
        id=PatternId.NGSWITCH,
        description="[ngSwitch] with *ngSwitchCase and *ngSwitchDefault",
        complexity=PatternComplexity.MEDIUM,
        detect_pattern=(
            r'<(?P<tag>[a-zA-Z][\w-]*)'
            r'(?P<attrs>[^>]*?)'
            r'\[ngSwitch\]="(?P<expression>[^"]+)"'
            r'(?P<attrs2>[^>]*?)'
            r'>'
            r'(?P<inner>.*?)'
            r'</(?P=tag)>'
        ),
        transform_fn=None,  # Implemented in transform_ngswitch below
    ),
]


def transform_ngswitch(match: re.Match, _template: str) -> str:
    """Transform [ngSwitch] with its *ngSwitchCase/*ngSwitchDefault children.

    This is more complex because it requires parsing child elements.
    """
    expression = match.group("expression").strip()
    inner = match.group("inner")

    cases: list[str] = []

    # Match *ngSwitchCase
    for case_match in re.finditer(
        r'<(?P<ctag>[a-zA-Z][\w-]*)'
        r'(?P<cattrs>[^>]*?)'
        r'\*ngSwitchCase="(?P<case_val>[^"]+)"'
        r'(?P<cattrs2>[^>]*?)'
        r'>'
        r'(?P<cinner>.*?)'
        r'</(?P=ctag)>',
        inner,
        re.DOTALL,
    ):
        case_val = case_match.group("case_val").strip()
        ctag = case_match.group("ctag")
        cattrs = case_match.group("cattrs") or ""
        cattrs2 = case_match.group("cattrs2") or ""
        cattrs = _remove_directive(cattrs + cattrs2, r'\*ngSwitchCase="[^"]*"')
        cattrs_str = f" {cattrs.strip()}" if cattrs.strip() else ""
        cinner = case_match.group("cinner")
        cases.append(
            f"  @case ({case_val}) {{\n"
            f"    <{ctag}{cattrs_str}>{cinner}</{ctag}>\n"
            f"  }}"
        )

    # Match *ngSwitchDefault
    default_match = re.search(
        r'<(?P<dtag>[a-zA-Z][\w-]*)'
        r'(?P<dattrs>[^>]*?)'
        r'\*ngSwitchDefault'
        r'(?P<dattrs2>[^>]*?)'
        r'>'
        r'(?P<dinner>.*?)'
        r'</(?P=dtag)>',
        inner,
        re.DOTALL,
    )
    if default_match:
        dtag = default_match.group("dtag")
        dattrs = default_match.group("dattrs") or ""
        dattrs2 = default_match.group("dattrs2") or ""
        dattrs = _remove_directive(dattrs + dattrs2, r'\*ngSwitchDefault')
        dattrs_str = f" {dattrs.strip()}" if dattrs.strip() else ""
        dinner = default_match.group("dinner")
        cases.append(
            f"  @default {{\n"
            f"    <{dtag}{dattrs_str}>{dinner}</{dtag}>\n"
            f"  }}"
        )

    cases_str = "\n".join(cases)
    return f"@switch ({expression}) {{\n{cases_str}\n}}"


# Wire up the ngSwitch transform function
for rule in _RULES:
    if rule.id == PatternId.NGSWITCH:
        rule.transform_fn = transform_ngswitch
        break


# Module-level singleton used by the Angular adapter (and legacy imports).
registry = RuleRegistry(rules=list(_RULES))
