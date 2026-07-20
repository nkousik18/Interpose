"""Minimal MCP client: launches server.py as a subprocess, connects over the stdio
transport, discovers its tools, and calls `echo`. Proves the whole MCP round trip works
before any Sentinel-specific code exists.
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = Path(__file__).parent / "server.py"


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"Discovered tools: {[t.name for t in tools.tools]}")

            result = await session.call_tool("echo", {"text": "hello, sentinel"})
            print(f"Tool result: {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())
