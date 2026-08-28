"""
Generic Transform Rule Primitives.

Framework-agnostic base classes for defining deterministic migration rules.
Each framework adapter creates its own RuleRegistry populated with rules that
use these shared types.

Usage:
    from automigrate.transforms.base_rules import (
        TransformRule, RuleRegistry, PatternComplexity
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class PatternComplexity(str, Enum):
    """How complex a matched pattern is — affects confidence scoring."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    AMBIGUOUS = "ambiguous"  # needs LLM fallback


@dataclass
class TransformRule:
    """A single deterministic transform rule.

    Attributes:
        id:             A string identifier unique within its framework adapter
                        (e.g., "ngif_simple", "class_to_arrow_fn").
        description:    Human-readable description of what this rule does.
        complexity:     Estimated complexity — used for confidence scoring.
        detect_pattern: Regex string that identifies this pattern in source code.
                        Compiled with re.DOTALL | re.MULTILINE.
        transform_fn:   Callable(match, full_source) -> replacement_string.
                        If None, the pattern is ambiguous and deferred to LLM.
    """

    id: str
    description: str
    complexity: PatternComplexity
    detect_pattern: str
    transform_fn: Callable[[re.Match, str], str] | None = None
    _compiled: re.Pattern | None = field(default=None, repr=False)

    @property
    def is_deterministic(self) -> bool:
        """True if this rule has a transform function (not LLM-delegated)."""
        return self.transform_fn is not None


class RuleRegistry:
    """Registry of transform rules, compiled and ready for use.

    Each framework adapter instantiates its own registry with framework-
    specific rules. The agent pipeline operates on the generic interface.
    """

    def __init__(self, rules: list[TransformRule] | None = None) -> None:
        self.rules: list[TransformRule] = rules or []
        self._compile_all()

    def _compile_all(self) -> None:
        for rule in self.rules:
            rule._compiled = re.compile(rule.detect_pattern, re.DOTALL)

    def add_rule(self, rule: TransformRule) -> None:
        """Add a rule and compile its pattern."""
        rule._compiled = re.compile(rule.detect_pattern, re.DOTALL)
        self.rules.append(rule)

    def find_matches(self, source: str) -> list[tuple[TransformRule, re.Match]]:
        """Find all rule matches in *source*, sorted by position (outermost first)."""
        matches: list[tuple[TransformRule, re.Match]] = []
        for rule in self.rules:
            assert rule._compiled is not None
            for m in rule._compiled.finditer(source):
                matches.append((rule, m))
        matches.sort(key=lambda x: x[1].start())
        return matches

    def classify(self, source: str) -> list[dict]:
        """Classify all pattern matches in *source*.

        Returns a list of dicts with:
            pattern_id, classification, complexity, line, column, snippet.
        """
        results = []
        for rule, m in self.find_matches(source):
            line = source[: m.start()].count("\n") + 1
            col = m.start() - source.rfind("\n", 0, m.start())
            results.append(
                {
                    "pattern_id": rule.id,
                    "classification": "deterministic" if rule.is_deterministic else "ambiguous",
                    "complexity": rule.complexity.value,
                    "line": line,
                    "column": col,
                    "snippet": m.group(0)[:120],
                }
            )
        return results

    def get_rule(self, rule_id: str) -> TransformRule | None:
        """Look up a rule by its string ID."""
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        return None
