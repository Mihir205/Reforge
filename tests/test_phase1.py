"""
Tests for the Angular Control Flow transform rules.

Verifies that each deterministic transform rule produces correct output
for representative input patterns.
"""

from __future__ import annotations

import pytest

from automigrate.transforms.angular_control_flow.rules import (
    PatternId,
    RuleRegistry,
    registry,
)
from automigrate.mcp_server.tools.apply_ast_transform import apply_ast_transform_to_string


class TestRuleRegistryDetection:
    """Test that the registry correctly detects patterns in templates."""

    def test_simple_ngif_detected(self):
        template = '<div *ngIf="isVisible"><p>Hello</p></div>'
        matches = registry.classify(template)
        assert len(matches) >= 1
        pattern_ids = [m["pattern_id"] for m in matches]
        assert "ngif_simple" in pattern_ids

    def test_ngif_else_detected(self):
        template = (
            '<div *ngIf="isLoggedIn; else loginPrompt"><p>Welcome</p></div>\n'
            '<ng-template #loginPrompt><p>Please log in.</p></ng-template>'
        )
        matches = registry.classify(template)
        pattern_ids = [m["pattern_id"] for m in matches]
        assert "ngif_else" in pattern_ids

    def test_ngif_async_pipe_classified_ambiguous(self):
        template = '<div *ngIf="data$ | async as data"><p>{{ data }}</p></div>'
        matches = registry.classify(template)
        assert len(matches) >= 1
        for m in matches:
            if m["pattern_id"] == "ngif_async_pipe":
                assert m["classification"] == "ambiguous"
                break
        else:
            pytest.fail("ngif_async_pipe pattern not detected")

    def test_simple_ngfor_detected(self):
        template = '<li *ngFor="let item of items">{{ item }}</li>'
        matches = registry.classify(template)
        pattern_ids = [m["pattern_id"] for m in matches]
        assert "ngfor_simple" in pattern_ids

    def test_ngfor_trackby_detected(self):
        template = '<div *ngFor="let item of items; trackBy: trackById">{{ item }}</div>'
        matches = registry.classify(template)
        pattern_ids = [m["pattern_id"] for m in matches]
        assert "ngfor_trackby" in pattern_ids

    def test_ngswitch_detected(self):
        template = (
            '<div [ngSwitch]="color">\n'
            '  <p *ngSwitchCase="\'red\'">Red</p>\n'
            '  <p *ngSwitchDefault>Other</p>\n'
            '</div>'
        )
        matches = registry.classify(template)
        pattern_ids = [m["pattern_id"] for m in matches]
        assert "ngswitch" in pattern_ids


class TestSimpleTransforms:
    """Test that deterministic transforms produce correct output."""

    def test_simple_ngif_transform(self):
        template = '<div *ngIf="isVisible"><p>Hello</p></div>'
        result = apply_ast_transform_to_string(template, pattern_id="ngif_simple")
        assert result.success
        assert "*ngIf" not in result.transformed_content
        assert "@if (isVisible)" in result.transformed_content
        assert "<p>Hello</p>" in result.transformed_content

    def test_ngif_else_transform(self):
        template = (
            '<div *ngIf="isLoggedIn; else loginPrompt">\n'
            '  <p>Welcome back!</p>\n'
            '</div>\n'
            '<ng-template #loginPrompt>\n'
            '  <p>Please log in.</p>\n'
            '</ng-template>'
        )
        result = apply_ast_transform_to_string(template, pattern_id="ngif_else")
        assert result.success
        assert "@if (isLoggedIn)" in result.transformed_content
        assert "@else" in result.transformed_content
        assert "Please log in." in result.transformed_content
        # The ng-template should be cleaned up
        assert "ng-template" not in result.transformed_content

    def test_simple_ngfor_transform(self):
        template = '<li *ngFor="let item of items">{{ item.name }}</li>'
        result = apply_ast_transform_to_string(template, pattern_id="ngfor_simple")
        assert result.success
        assert "@for (item of items; track item)" in result.transformed_content
        assert "{{ item.name }}" in result.transformed_content

    def test_ngfor_trackby_transform(self):
        template = '<div *ngFor="let item of items; trackBy: trackById">{{ item }}</div>'
        result = apply_ast_transform_to_string(template, pattern_id="ngfor_trackby")
        assert result.success
        assert "@for (item of items; track trackById($index, item))" in result.transformed_content

    def test_ngfor_with_index_transform(self):
        template = '<div *ngFor="let item of items; let i = index">{{ i }}: {{ item }}</div>'
        result = apply_ast_transform_to_string(template, pattern_id="ngfor_trackby")
        assert result.success
        assert "let i = $index" in result.transformed_content

    def test_ambiguous_pattern_skipped(self):
        template = '<div *ngIf="data$ | async as data"><p>{{ data }}</p></div>'
        result = apply_ast_transform_to_string(template)
        assert result.success
        assert "ngif_async_pipe" in result.patterns_skipped_ambiguous
        # The template should be unchanged for the ambiguous part
        assert "*ngIf" in result.transformed_content

    def test_diff_generated(self):
        template = '<div *ngIf="isVisible"><p>Hello</p></div>'
        result = apply_ast_transform_to_string(template)
        assert result.diff  # Should have content
        assert "---" in result.diff
        assert "+++" in result.diff


class TestNgSwitchTransform:
    """Test *ngSwitch transforms."""

    def test_basic_ngswitch(self):
        template = (
            '<div [ngSwitch]="status">\n'
            '  <p *ngSwitchCase="\'active\'">Active</p>\n'
            '  <p *ngSwitchCase="\'inactive\'">Inactive</p>\n'
            '  <p *ngSwitchDefault>Unknown</p>\n'
            '</div>'
        )
        result = apply_ast_transform_to_string(template, pattern_id="ngswitch")
        assert result.success
        assert "@switch (status)" in result.transformed_content
        assert "@case ('active')" in result.transformed_content
        assert "@case ('inactive')" in result.transformed_content
        assert "@default" in result.transformed_content


class TestScanProject:
    """Test the scan_project tool."""

    def test_scan_fixture_project(self, tmp_path):
        """Create a minimal fixture and scan it."""
        # Create a template file
        template_dir = tmp_path / "src" / "app"
        template_dir.mkdir(parents=True)
        template_file = template_dir / "test.component.html"
        template_file.write_text(
            '<div *ngIf="show"><p>Hello</p></div>\n'
            '<li *ngFor="let x of items">{{ x }}</li>\n'
        )

        from automigrate.mcp_server.tools.scan_project import scan_project

        result = scan_project(str(tmp_path))
        assert result.total_files_scanned == 1
        assert result.total_patterns_found >= 2
        assert result.deterministic_count >= 2

    def test_scan_nonexistent_project(self):
        from automigrate.mcp_server.tools.scan_project import scan_project

        with pytest.raises(FileNotFoundError):
            scan_project("/nonexistent/path")
