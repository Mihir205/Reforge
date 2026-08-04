"""
MCP Server — exposes migration primitives as callable MCP tools.

This is the entry point for the MCP server. It registers all tools
(scan_project, apply_ast_transform, etc.) and starts the server.

In Phase 1, only scan_project and apply_ast_transform are wired up.
Additional tools (static_validation, run_test_suite, verification_agent,
secrets_scan, create_review_ticket) are added in later phases.
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
    ]


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
