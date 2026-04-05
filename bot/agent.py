from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from agents import Agent
from agents import Runner
from agents import TResponseInputItem
from agents.mcp import MCPServerStdio
from agents.mcp import MCPServerStreamableHttp
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel
from agents.tracing import set_tracing_disabled
from openai import AsyncOpenAI

DEFAULT_INSTRUCTIONS = (
    "You are a helpful assistant in a Discord server. "
    "When referencing articles, websites, or resources, always include "
    "the URL as a markdown hyperlink, e.g. [title](https://example.com). "
    "Keep responses concise and well-structured."
)

MAX_TURNS = 10
MCP_SESSION_TIMEOUT_SECONDS = 30.0

set_tracing_disabled(True)

# Conversation key: (channel_id, user_id) — each user has an independent
# conversation history per channel/thread.
ConversationKey = tuple[int, int]


def _get_model() -> OpenAIResponsesModel | OpenAIChatCompletionsModel:
    """Create an OpenAI model from environment variables.

    Uses the standard OpenAI client, which works with both OpenAI and
    Azure OpenAI v1 API (via OPENAI_BASE_URL + OPENAI_API_KEY).

    OPENAI_API_TYPE controls which API the model uses:
      - "responses" (default): OpenAI Responses API — recommended by the SDK
      - "chat_completions": Chat Completions API
    """
    model_name = os.getenv("OPENAI_MODEL", "gpt-5.4")
    api_type = os.getenv("OPENAI_API_TYPE", "responses")
    client = AsyncOpenAI()

    if api_type == "chat_completions":
        return OpenAIChatCompletionsModel(model=model_name, openai_client=client)
    return OpenAIResponsesModel(model=model_name, openai_client=client)


class OpenAIAgent:
    """A wrapper for OpenAI Agent with MCP server support."""

    def __init__(
        self,
        name: str,
        mcp_servers: list | None = None,
        instructions: str = DEFAULT_INSTRUCTIONS,
    ) -> None:
        self.agent = Agent(
            name=name,
            instructions=instructions,
            model=_get_model(),
            mcp_servers=(mcp_servers if mcp_servers is not None else []),
        )
        self.name = name
        self._conversations: dict[ConversationKey, list[TResponseInputItem]] = {}
        self._locks: dict[ConversationKey, asyncio.Lock] = {}

    def get_messages(self, key: ConversationKey) -> list[TResponseInputItem]:
        return self._conversations.get(key, [])

    def set_messages(self, key: ConversationKey, messages: list[TResponseInputItem]) -> None:
        self._conversations[key] = messages

    def append_user_message(self, key: ConversationKey, message: str) -> None:
        if key not in self._conversations:
            self._conversations[key] = []
        self._conversations[key].append({"role": "user", "content": message})

    def truncate_history(self, key: ConversationKey) -> None:
        """Keep only the last MAX_TURNS turns of conversation history.

        A turn starts at each user message. All messages between two user
        messages (assistant replies, tool calls, tool results) belong to
        the preceding turn.
        """
        msgs = self.get_messages(key)
        user_indices = [i for i, m in enumerate(msgs) if m.get("role") == "user"]
        if len(user_indices) <= MAX_TURNS:
            return
        cut = user_indices[-MAX_TURNS]
        self._conversations[key] = msgs[cut:]

    @classmethod
    def from_dict(cls, name: str, config: dict[str, Any]) -> OpenAIAgent:
        mcp_servers: list[MCPServerStreamableHttp | MCPServerStdio] = []
        for mcp_srv in config.get("mcpServers", {}).values():
            if "httpUrl" in mcp_srv:
                mcp_servers.append(
                    MCPServerStreamableHttp(
                        client_session_timeout_seconds=MCP_SESSION_TIMEOUT_SECONDS,
                        params={
                            "url": mcp_srv["httpUrl"],
                            "headers": mcp_srv.get("headers", {}),
                        },
                    )
                )
            else:
                mcp_servers.append(
                    MCPServerStdio(
                        client_session_timeout_seconds=MCP_SESSION_TIMEOUT_SECONDS,
                        params={
                            "command": mcp_srv["command"],
                            "args": mcp_srv.get("args", []),
                            "env": mcp_srv.get("env"),
                        },
                    )
                )
        instructions = config.get("instructions", DEFAULT_INSTRUCTIONS)
        return cls(name, mcp_servers, instructions=instructions)

    async def connect(self) -> None:
        for mcp_server in self.agent.mcp_servers:
            try:
                await mcp_server.connect()
                logging.info(f"Server {mcp_server.name} connected")
            except Exception:
                logging.warning(
                    f"MCP server {mcp_server.name} failed to connect — bot will run without its tools",
                    exc_info=True,
                )

    async def run(self, key: ConversationKey, message: str) -> str:
        """Run the agent for a conversation key.

        A per-conversation async lock ensures that when two messages arrive for
        the same (channel_id, user_id) in quick succession, they are processed
        sequentially. Different conversations still run in parallel.
        """
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            history = self.get_messages(key) + [{"role": "user", "content": message}]
            result = await Runner.run(self.agent, input=history)
            self.set_messages(key, result.to_input_list())
            self.truncate_history(key)
            return str(result.final_output)

    async def cleanup(self) -> None:
        for mcp_server in self.agent.mcp_servers:
            try:
                await mcp_server.cleanup()
                logging.info(f"Server {mcp_server.name} cleaned up")
            except Exception as e:
                logging.error(f"Error during cleanup of server {mcp_server.name}: {e}")
