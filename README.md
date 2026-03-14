# MCP Server Learning Guide

This project shows a minimal MCP setup:
- Server: `my_server.py`
- Client: `agent.py`
- Transport: `stdio` (client starts server as a child process)

## 1) Tool Definitions

`my_server.py` exposes these tools:
- `add_ints(a, b)`
- `multiply_ints(a, b)`
- `echo_text(text)`
- `get_server_time()`

Each tool is registered with `@mcp.tool(...)` and has a clear input/output contract.

## 2) Schemas And Validation

Schemas are generated from type hints and `pydantic.Field(...)`.

Example in this project:
- `echo_text` uses `min_length=1`, `max_length=2000`

If invalid input is sent, the server returns a structured tool error (`isError: true`), which `agent.py` demonstrates.

## 3) Client/Server Handshake

`agent.py` uses the required MCP flow:
1. Start transport (`stdio_client`)
2. Create session (`ClientSession`)
3. Initialize (`await session.initialize()`)
4. Discover tools (`await session.list_tools()`)
5. Call tools (`await session.call_tool(...)`)

## 4) Transport Choice

Current project uses `stdio`.

Use `stdio` when:
- Running locally
- Client can spawn server process
- You want the simplest setup

Use HTTP/SSE/streamable transport when:
- Server must run remotely
- Multiple clients connect over network
- You need service-style deployment/observability

## 5) Error Handling

Current behavior:
- Valid calls return `isError: false`
- Invalid payloads return `isError: true` with validation details

Recommended production pattern:
- Validate at tool boundary
- Return clear user-facing error text
- Log detailed internal context without leaking secrets

## 6) Dependencies

## Windows (PowerShell)

```powershell
cd "C:\Users\Home\Desktop\MCP PROJECT"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install mcp pydantic
```

If you also want LLM experiments in this repo:

```powershell
pip install openai
```

Optional freeze:

```powershell
pip freeze > requirements.txt
```

## 7) Run Locally

Run the demo client:

```powershell
cd "C:\Users\Home\Desktop\MCP PROJECT"
.\.venv\Scripts\Activate.ps1
python agent.py
```

This automatically starts `my_server.py` via `stdio`.

## 8) Environment Variables

Server supports:
- `MCP_SERVER_NAME` (default: `demo`)
- `MCP_TIMEZONE` (default: `UTC`)

Client supports:
- `MCP_SERVER_COMMAND` (default: current Python executable)
- `MCP_SERVER_SCRIPT` (default: `my_server.py`)

PowerShell example:

```powershell
$env:MCP_SERVER_NAME="calc-demo"
$env:MCP_TIMEZONE="Asia/Dubai"
python agent.py
```

## 9) Process Manager + Logs (Deployment Basics)

With `stdio`, the server lifecycle is tied to the client process. For service deployment, prefer a network transport and run server as a long-lived process.

If you still run it as a long-lived process on Linux, `systemd` pattern:

```ini
[Unit]
Description=MCP Demo Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/mcp-project
Environment=MCP_SERVER_NAME=calc-demo
Environment=MCP_TIMEZONE=UTC
ExecStart=/opt/mcp-project/.venv/bin/python my_server.py
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Useful log commands:

```bash
sudo systemctl status mcp-demo
journalctl -u mcp-demo -f
```

## 10) Next Steps

1. Add domain tools (files, APIs, DB, etc.) with strict schemas.
2. Add request IDs and structured logging.
3. Move from `stdio` to network transport for real deployment.
4. Add tests for tool validation and error responses.
