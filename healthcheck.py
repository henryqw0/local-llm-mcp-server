import asyncio
import os
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> None:
    server_command = os.getenv("MCP_SERVER_COMMAND", sys.executable)
    server_script = os.getenv("MCP_SERVER_SCRIPT", "my_server.py")

    server = StdioServerParameters(
        command=server_command,
        args=[server_script],
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = await session.list_tools()

            print(f"PASS: connected to MCP server '{init.serverInfo.name}'")
            print(f"PASS: discovered {len(tools.tools)} tools")
            for tool in tools.tools:
                print(f"- {tool.name}")


if __name__ == "__main__":
    asyncio.run(main())
