"""
MCP Server — exposes migration primitives as callable MCP tools.

All tools are registered here and available to MCP-compatible agent hosts:
  scan_project, apply_ast_transform, verification_agent, static_validation,
  secrets_scan, run_test_suite, create_review_ticket.
"""

from __future__ import annotations

import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from automigrate.mcp_server.tools.scan_project import scan_project
from automigrate.mcp_server.tools.apply_ast_transform import (
    apply_ast_transform,
    apply_ast_transform_to_string,
)
from automigrate.mcp_server.tools.verification_agent import run_verification_agent
from automigrate.mcp_server.tools.static_validation import run_static_validation
from automigrate.mcp_server.tools.secrets_scan import run_secrets_scan
from automigrate.mcp_server.tools.run_test_suite import run_test_suite
from automigrate.mcp_server.tools.create_review_ticket import create_review_ticket

logger = logging.getLogger(__name__)

# Create the MCP server instance
app = Server("automigrate")


# =============================================================================
#  Tool definitions
# =============================================================================

@app.list_tools()
async def list_tools() -> list[Tool]:
    """Advertise available tools to MCP clients."""
    return [
        Tool(
            name="scan_project",
            description=(
                "Scan a project directory for migration targets. "
                "Classifies each detected pattern as 'deterministic' or 'ambiguous'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {
                        "type": "string",
                        "description": "Absolute path to the project root directory.",
                    },
                    "migration_type": {
                        "type": "string",
                        "description": "Migration type to scan for.",
                        "default": "angular_control_flow",
                        "enum": ["angular_control_flow"],
                    },
                },
                "required": ["project_path"],
            },
        ),
        Tool(
            name="apply_ast_transform",
            description=(
                "Apply deterministic AST transforms to a template file. "
                "Returns the transformed content and a unified diff."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the template file to transform.",
                    },
                    "pattern_id": {
                        "type": "string",
                        "description": (
                            "Specific pattern ID to apply (e.g., 'ngif_simple'). "
                            "If omitted, all applicable deterministic rules are applied."
                        ),
                    },
                    "write": {
                        "type": "boolean",
                        "description": "If true, write the transformed content back to the file.",
                        "default": False,
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="verification_agent",
            description=(
                "Run lightweight rule-based checks on transformed content. "
                "Catches leftover legacy directives, unbalanced braces, and malformed new syntax."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file being verified."},
                    "transformed_content": {"type": "string", "description": "The transformed file content to check."},
                },
                "required": ["file_path", "transformed_content"],
            },
        ),
        Tool(
            name="static_validation",
            description=(
                "Run a static validation pipeline on a transformed file: "
                "AST syntax check → type check → lint."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file relative to project root."},
                    "project_path": {"type": "string", "description": "Absolute path to the project root."},
                },
                "required": ["file_path", "project_path"],
            },
        ),
        Tool(
            name="secrets_scan",
            description=(
                "Scan transformed content for accidentally introduced credentials, "
                "API keys, or tokens. A failure here always blocks the transform."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file being scanned."},
                    "content": {"type": "string", "description": "The transformed content to scan."},
                },
                "required": ["file_path", "content"],
            },
        ),
        Tool(
            name="run_test_suite",
            description=(
                "Run the project's test suite to confirm the transformation didn't break behavior. "
                "Returns pass/fail status and test logs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Absolute path to the project root."},
                    "file_filter": {"type": "string", "description": "Optional: run only tests related to this file."},
                },
                "required": ["project_path"],
            },
        ),
        Tool(
            name="create_review_ticket",
            description=(
                "Write a markdown review ticket for a file that failed or scored below the confidence threshold. "
                "Tickets are written to reports/run_<id>/review/."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "confidence_score": {"type": "number"},
                    "strategy": {"type": "string"},
                    "diff": {"type": "string"},
                    "validation_errors": {"type": "array", "items": {"type": "string"}},
                    "test_logs": {"type": "string"},
                    "run_id": {"type": "string", "default": "run_unknown"},
                },
                "required": ["file_path", "confidence_score", "strategy", "diff"],
            },
        ),
    ]


# =============================================================================
#  Tool call handlers
# =============================================================================

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocations from MCP clients."""
    try:
        if name == "scan_project":
            result = scan_project(
                project_path=arguments["project_path"],
                migration_type=arguments.get("migration_type", "angular_control_flow"),
            )
            return [TextContent(type="text", text=json.dumps(result.to_dict(), indent=2))]

        elif name == "apply_ast_transform":
            result = apply_ast_transform(
                file_path=arguments["file_path"],
                pattern_id=arguments.get("pattern_id"),
                write=arguments.get("write", False),
            )
            return [TextContent(type="text", text=json.dumps(result.to_dict(), indent=2))]

        elif name == "verification_agent":
            result = run_verification_agent(
                file_path=arguments["file_path"],
                transformed_content=arguments["transformed_content"],
            )
            return [TextContent(type="text", text=json.dumps(result.model_dump(), indent=2))]

        elif name == "static_validation":
            results = run_static_validation(
                file_path=arguments["file_path"],
                project_path=arguments["project_path"],
            )
            return [TextContent(type="text", text=json.dumps(
                {k: v.model_dump() for k, v in results.items()}, indent=2
            ))]

        elif name == "secrets_scan":
            result = run_secrets_scan(
                file_path=arguments["file_path"],
                content=arguments["content"],
            )
            return [TextContent(type="text", text=json.dumps(result.model_dump(), indent=2))]

        elif name == "run_test_suite":
            result = run_test_suite(
                project_path=arguments["project_path"],
                file_filter=arguments.get("file_filter"),
            )
            return [TextContent(type="text", text=json.dumps(result.model_dump(), indent=2))]

        elif name == "create_review_ticket":
            ticket_path = create_review_ticket(
                file_path=arguments["file_path"],
                confidence_score=arguments["confidence_score"],
                strategy=arguments["strategy"],
                diff=arguments["diff"],
                validation_errors=arguments.get("validation_errors", []),
                test_logs=arguments.get("test_logs", ""),
                run_id=arguments.get("run_id", "run_unknown"),
            )
            return [TextContent(type="text", text=json.dumps({"ticket_path": ticket_path}))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


# =============================================================================
#  Server entry point
# =============================================================================

async def main():
    """Start the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


