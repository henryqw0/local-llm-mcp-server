import asyncio
import json
import os
import sys
import time
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from openai import BadRequestError, NotFoundError, OpenAI


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")

llm = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="ollama",
)

SYSTEM_PROMPT = (
    "You are a helpful assistant. Use MCP tools only when they are actually useful. "
    "If the user's question can be answered from general reasoning or normal conversation, "
    "answer directly and do not mention missing or unavailable tools. "
    "If a tool is required, call it with valid arguments. "
    "After tool results are available, answer the user clearly."
)

FALLBACK_SYSTEM_PROMPT = (
    "Answer the user's question directly using normal reasoning. "
    "Do not mention tools unless the user explicitly asks about them."
)


def is_shell_command(text: str) -> bool:
    stripped = text.strip()
    lower = stripped.lower()

    shell_prefixes = (
        "& ",
        ".\\",
        "python ",
        "py ",
        "powershell",
        "cmd ",
        "set ",
        "$env:",
        "cd ",
        "dir",
        "ls",
        ".venv\\scripts\\activate",
    )
    return lower.startswith(shell_prefixes)


def get_initial_prompt() -> str:
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--ask":
        return " ".join(args[1:]).strip()
    return ""


def mcp_tools_to_openai(tools_result: Any) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in tools_result.tools
    ]


def parse_tool_args(raw_args: Any) -> dict[str, Any]:
    if isinstance(raw_args, dict):
        return raw_args
    if not raw_args:
        return {}
    return json.loads(raw_args)


def tool_result_to_text(result: Any) -> str:
    parts: list[str] = []
    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    if parts:
        return "\n".join(parts)
    if hasattr(result, "model_dump"):
        return json.dumps(result.model_dump(), ensure_ascii=True)
    return str(result)


async def run_chat_turn(
    session: ClientSession, conversation_history: list[dict[str, Any]], user_prompt: str
) -> None:
    mcp_tools = await session.list_tools()
    openai_tools = mcp_tools_to_openai(mcp_tools)
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, *conversation_history]
    messages.append({"role": "user", "content": user_prompt})

    try:
        print(f"Sending prompt to model '{OLLAMA_MODEL}'...")
        model_start = time.perf_counter()
        first_response = llm.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=messages,
            tools=openai_tools,
        )
        first_model_elapsed = time.perf_counter() - model_start
        print(f"First model response received in {first_model_elapsed:.2f}s.")
    except NotFoundError:
        print(
            f"Model '{OLLAMA_MODEL}' is not installed in Ollama. "
            "Install it with: ollama pull qwen3:4b"
        )
        return
    except BadRequestError:
        print(
            f"Model '{OLLAMA_MODEL}' could not process tool calls. "
            "Use a tool-capable model such as qwen3:4b."
        )
        return

    assistant_message = first_response.choices[0].message
    tool_calls = assistant_message.tool_calls or []

    if not tool_calls:
        direct_answer = (assistant_message.content or "").strip()
        if not direct_answer or "no tools available" in direct_answer.lower():
            print(f"Model did not use a tool. Asking '{OLLAMA_MODEL}' for a direct answer...")
            fallback_start = time.perf_counter()
            fallback_response = llm.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=[{"role": "system", "content": FALLBACK_SYSTEM_PROMPT}, *conversation_history, {"role": "user", "content": user_prompt}],
            )
            fallback_elapsed = time.perf_counter() - fallback_start
            direct_answer = (fallback_response.choices[0].message.content or "Model returned no content.").strip()
            print(f"Direct-answer fallback received in {fallback_elapsed:.2f}s.")

        conversation_history.append({"role": "user", "content": user_prompt})
        conversation_history.append({"role": "assistant", "content": direct_answer or "Model returned no content."})
        print(f"\nAssistant: {direct_answer or 'Model returned no content.'}")
        return

    print(f"Model requested {len(tool_calls)} tool call(s).")
    assistant_tool_message = (
        {
            "role": "assistant",
            "content": assistant_message.content or "",
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in tool_calls
            ],
        }
    )
    messages.append(assistant_tool_message)

    for tool_call in tool_calls:
        tool_args = parse_tool_args(tool_call.function.arguments)
        print(f"Calling MCP tool: {tool_call.function.name} with {tool_args}")
        tool_start = time.perf_counter()
        result = await session.call_tool(tool_call.function.name, tool_args)
        tool_elapsed = time.perf_counter() - tool_start
        result_text = tool_result_to_text(result)
        print(f"Tool result: {result_text}")
        print(f"Tool call completed in {tool_elapsed:.2f}s.")

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_text,
            }
        )

    print(f"Sending tool result(s) back to model '{OLLAMA_MODEL}' for the final answer...")
    final_model_start = time.perf_counter()
    final_response = llm.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=messages,
    )
    final_model_elapsed = time.perf_counter() - final_model_start
    final_answer = final_response.choices[0].message.content or "Model returned no final answer."
    conversation_history.append({"role": "user", "content": user_prompt})
    conversation_history.append(assistant_tool_message)
    conversation_history.extend(messages[-len(tool_calls):])
    conversation_history.append({"role": "assistant", "content": final_answer})
    print(f"Final model response received in {final_model_elapsed:.2f}s.")
    print(f"\nAssistant: {final_answer}")


async def main() -> None:
    server = StdioServerParameters(
        command=os.getenv("MCP_SERVER_COMMAND", sys.executable),
        args=[os.getenv("MCP_SERVER_SCRIPT", "my_server.py")],
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"Connected to MCP server: {init.serverInfo.name}")
            print("Chat mode is ready. Type '/reset' to clear history, or 'exit'/'quit' to stop.")
            print("Use '--ask \"your prompt\"' only if you want a one-shot first message.\n")
            conversation_history: list[dict[str, Any]] = []

            initial_prompt = get_initial_prompt()
            if initial_prompt:
                print(f"You: {initial_prompt}")
                await run_chat_turn(session, conversation_history, initial_prompt)

            while True:
                try:
                    user_prompt = input("\nYou: ").strip()
                except EOFError:
                    print("\nInput closed. Exiting chat.")
                    return

                if not user_prompt:
                    continue

                if is_shell_command(user_prompt):
                    print("Ignored shell command input. Type a chat message, or run shell commands in a separate terminal.")
                    continue

                if user_prompt.lower() == "/reset":
                    conversation_history.clear()
                    print("Conversation history cleared.")
                    continue

                if user_prompt.lower() in {"exit", "quit"}:
                    print("Exiting chat.")
                    return

                await run_chat_turn(session, conversation_history, user_prompt)


if __name__ == "__main__":
    asyncio.run(main())
