"""Minimal MCP server: one tool, `echo`, that returns whatever text it's given.

Purpose: the smallest possible thing that proves the MCP Python SDK works end-to-end,
before any Interpose-specific code exists. See concepts/01-what-is-mcp.md.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hello-echo")


@mcp.tool()
def echo(text: str) -> str:
    """Return the input text unchanged."""
    return text


if __name__ == "__main__":
    mcp.run(transport="stdio")
