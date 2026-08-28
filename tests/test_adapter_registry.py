"""
Tests for the framework adapter registry and adapters.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from automigrate.adapters.registry import (
    list_adapters,
    detect_framework,
    get_adapter,
    get_adapter_for_migration,
)
from automigrate.adapters.base import FrameworkAdapter
from automigrate.transforms.base_rules import RuleRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_angular_project(tmp_path: Path) -> Path:
    pkg = {
        "name": "my-angular-app",
        "dependencies": {"@angular/core": "^17.0.0"},
    }
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    (tmp_path / "angular.json").write_text("{}")
    return tmp_path


def make_react_project(tmp_path: Path) -> Path:
    pkg = {
        "name": "my-react-app",
        "dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"},
        "scripts": {"test": "react-scripts test"},
    }
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    return tmp_path


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

def test_list_adapters_returns_non_empty():
    adapters = list_adapters()
    assert len(adapters) >= 2
    names = [cls.name for cls in adapters]
    assert "angular" in names
    assert "react" in names


def test_get_adapter_angular():
    adapter = get_adapter("angular")
    assert adapter.name == "angular"
    assert adapter.display_name == "Angular"


def test_get_adapter_react():
    adapter = get_adapter("react")
    assert adapter.name == "react"


def test_get_adapter_unknown_raises():
    with pytest.raises(ValueError, match="No adapter found"):
        get_adapter("cobol")


def test_get_adapter_for_migration_valid():
    adapter = get_adapter_for_migration("angular", "control_flow")
    assert adapter.name == "angular"


def test_get_adapter_for_migration_invalid():
    with pytest.raises(ValueError, match="does not support migration type"):
        get_adapter_for_migration("angular", "nonexistent_migration")


# ---------------------------------------------------------------------------
# Auto-detection tests
# ---------------------------------------------------------------------------

def test_detect_framework_angular(tmp_path):
    make_angular_project(tmp_path)
    adapter = detect_framework(str(tmp_path))
    assert adapter is not None
    assert adapter.name == "angular"


def test_detect_framework_react(tmp_path):
    make_react_project(tmp_path)
    adapter = detect_framework(str(tmp_path))
    assert adapter is not None
    assert adapter.name == "react"


def test_detect_framework_unknown(tmp_path):
    # Empty project — no recognisable files
    adapter = detect_framework(str(tmp_path))
    assert adapter is None


def test_angular_takes_priority_over_react(tmp_path):
    """If a project has both @angular/core and react, Angular wins (checked first)."""
    pkg = {
        "dependencies": {
            "@angular/core": "^17.0.0",
            "react": "^18.0.0",
        }
    }
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    adapter = detect_framework(str(tmp_path))
    assert adapter is not None
    assert adapter.name == "angular"


# ---------------------------------------------------------------------------
# AngularAdapter tests
# ---------------------------------------------------------------------------

class TestAngularAdapter:
    def setup_method(self):
        self.adapter = get_adapter("angular")

    def test_migrations_list(self):
        migrations = self.adapter.get_migrations()
        ids = [m.id for m in migrations]
        assert "control_flow" in ids
        assert "standalone_components" in ids

    def test_default_migration(self):
        default = self.adapter.get_default_migration()
        assert default.id == "control_flow"

    def test_get_migration_by_id(self):
        m = self.adapter.get_migration("control_flow")
        assert m is not None
        assert m.id == "control_flow"

    def test_get_migration_unknown_returns_none(self):
        assert self.adapter.get_migration("nonexistent") is None

    def test_file_patterns_control_flow(self):
        patterns = self.adapter.get_file_patterns("control_flow")
        assert ".html" in patterns

    def test_rule_registry_control_flow_has_rules(self):
        reg = self.adapter.get_rule_registry("control_flow")
        assert isinstance(reg, RuleRegistry)
        assert len(reg.rules) > 0

    def test_rule_registry_standalone_is_empty(self):
        reg = self.adapter.get_rule_registry("standalone_components")
        assert isinstance(reg, RuleRegistry)
        assert len(reg.rules) == 0

    def test_migration_docs_control_flow_not_empty(self):
        docs = self.adapter.get_migration_docs("control_flow")
        assert len(docs) > 100
        assert "@if" in docs

    def test_llm_system_prompt_has_context_placeholder(self):
        prompt = self.adapter.get_llm_system_prompt("control_flow")
        assert "{context}" in prompt

    def test_llm_examples_control_flow(self):
        examples = self.adapter.get_llm_examples("control_flow")
        assert len(examples) > 0
        user, assistant = examples[0]
        assert "*ngIf" in user
        assert "@if" in assistant

    def test_failure_hints_has_all_categories(self):
        hints = self.adapter.get_failure_hints("control_flow")
        for key in ["syntax_failure", "test_failure", "unknown"]:
            assert key in hints

    def test_skip_dirs_contains_node_modules(self):
        assert "node_modules" in self.adapter.get_skip_dirs()

    def test_detect_angular_project(self, tmp_path):
        make_angular_project(tmp_path)
        assert self.adapter.detect(str(tmp_path))

    def test_detect_non_angular_project(self, tmp_path):
        (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "^18"}}))
        assert not self.adapter.detect(str(tmp_path))


# ---------------------------------------------------------------------------
# ReactAdapter tests
# ---------------------------------------------------------------------------

class TestReactAdapter:
    def setup_method(self):
        self.adapter = get_adapter("react")

    def test_migrations_list(self):
        ids = [m.id for m in self.adapter.get_migrations()]
        assert "class_to_hooks" in ids

    def test_default_migration(self):
        assert self.adapter.get_default_migration().id == "class_to_hooks"

    def test_file_patterns(self):
        patterns = self.adapter.get_file_patterns("class_to_hooks")
        assert ".jsx" in patterns
        assert ".tsx" in patterns

    def test_rule_registry_is_empty(self):
        reg = self.adapter.get_rule_registry("class_to_hooks")
        assert isinstance(reg, RuleRegistry)
        assert len(reg.rules) == 0  # LLM-only for now

    def test_migration_docs_class_to_hooks(self):
        docs = self.adapter.get_migration_docs("class_to_hooks")
        assert len(docs) > 100
        assert "useState" in docs

    def test_llm_system_prompt(self):
        prompt = self.adapter.get_llm_system_prompt("class_to_hooks")
        assert "{context}" in prompt
        assert "useState" in prompt

    def test_llm_examples(self):
        examples = self.adapter.get_llm_examples("class_to_hooks")
        assert len(examples) > 0
        user, assistant = examples[0]
        assert "class" in user
        assert "useState" in assistant

    def test_detect_react_project(self, tmp_path):
        make_react_project(tmp_path)
        assert self.adapter.detect(str(tmp_path))

    def test_does_not_detect_angular_as_react(self, tmp_path):
        make_angular_project(tmp_path)
        assert not self.adapter.detect(str(tmp_path))


# ---------------------------------------------------------------------------
# base_rules tests
# ---------------------------------------------------------------------------

class TestBaseRules:
    def test_rule_registry_empty(self):
        reg = RuleRegistry()
        assert reg.rules == []

    def test_rule_registry_classify_empty_source(self):
        reg = RuleRegistry()
        results = reg.classify("<div>Hello</div>")
        assert results == []

    def test_rule_registry_get_rule_not_found(self):
        reg = RuleRegistry()
        assert reg.get_rule("nonexistent") is None

    def test_angular_rule_registry_classifies_ngif(self):
        """Angular rule registry should classify *ngIf as deterministic."""
        from automigrate.transforms.angular_control_flow.rules import registry
        results = registry.classify('<div *ngIf="isVisible">Hello</div>')
        assert len(results) > 0
        assert results[0]["classification"] == "deterministic"
        assert "ngif" in results[0]["pattern_id"]
