import os
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP
from pydantic import Field


SERVER_NAME = os.getenv("MCP_SERVER_NAME", "demo")
SERVER_TZ = os.getenv("MCP_TIMEZONE", "UTC")

mcp = FastMCP(SERVER_NAME)


@mcp.tool(name="add_ints", description="Add two integers.")
def add_ints(
    a: int = Field(description="First integer"),
    b: int = Field(description="Second integer"),
) -> int:
    return a + b


@mcp.tool(name="multiply_ints", description="Multiply two integers.")
def multiply_ints(
    a: int = Field(description="First integer"),
    b: int = Field(description="Second integer"),
) -> int:
    return a * b


@mcp.tool(name="echo_text", description="Return the same text received from the client.")
def echo_text(
    text: str = Field(min_length=1, max_length=2000, description="Input text to echo back"),
) -> str:
    return text


@mcp.tool(name="get_server_time", description="Return the current server time in ISO 8601 format.")
def get_server_time() -> str:
    # Keep time output predictable for clients and logs.
    now = datetime.now(timezone.utc)
    return f"{now.isoformat()} ({SERVER_TZ})"


if __name__ == "__main__":
    mcp.run()
