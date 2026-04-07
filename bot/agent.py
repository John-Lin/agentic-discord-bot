from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from agents import Agent
from agents import Runner
from agents import ShellCommandRequest
from agents import ShellTool
from agents import ShellToolLocalEnvironment
from agents import ShellToolLocalSkill
from agents import TResponseInputItem
from agents.mcp import MCPServerStdio
from agents.mcp import MCPServerStreamableHttp
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel
from agents.tracing import set_tracing_disabled
from openai import AsyncOpenAI

INSTRUCTIONS_FILE = Path("instructions.md")

MAX_TURNS = 10
MCP_SESSION_TIMEOUT_SECONDS = 30.0
SHELL_TIMEOUT = 30.0
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

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


def _load_instructions() -> str:
    """Load agent instructions from ``instructions.md`` in the working directory.

    Fails fast with a clear error if the file is missing, so misconfiguration
    is caught immediately at startup.
    """
    try:
        return INSTRUCTIONS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Instructions file not found: {INSTRUCTIONS_FILE.resolve()}. "
            "Create or mount instructions.md with the agent system prompt."
        ) from e


def _parse_skill_description(content: str) -> str:
    """Return the description field from a SKILL.md YAML frontmatter, or ""."""
    if not content.startswith("---"):
        return ""
    end = content.find("\n---", 3)
    if end == -1:
        return ""
    for line in content[3:end].splitlines():
        if line.startswith("description:"):
            value = line[len("description:") :].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            return value
    return ""


def _load_shell_skills() -> list[ShellToolLocalSkill]:
    """Discover local shell skills under SKILLS_DIR.

    Each immediate subdirectory of SKILLS_DIR containing a SKILL.md is mounted
    as a ShellToolLocalSkill. The skill name is the directory name; the
    description is read from the SKILL.md YAML frontmatter.
    """
    if not SKILLS_DIR.is_dir():
        return []
    skills: list[ShellToolLocalSkill] = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_md.is_file():
            continue
        try:
            content = skill_md.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            logging.warning("Skipping unreadable skill file: %s", skill_md, exc_info=True)
            continue
        skills.append(
            ShellToolLocalSkill(
                name=skill_dir.name,
                description=_parse_skill_description(content),
                path=str(skill_dir),
            )
        )
    return skills


async def _shell_executor(request: ShellCommandRequest) -> str:
    """Run each shell command from the request and return combined output.

    Honours action.timeout_ms when set, otherwise falls back to SHELL_TIMEOUT.
    stderr is merged into stdout for simplicity.
    """
    action = request.data.action
    timeout = (action.timeout_ms / 1000.0) if action.timeout_ms is not None else SHELL_TIMEOUT

    outputs: list[str] = []
    for command in action.commands:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as e:
            outputs.append(f"Failed to run command: {command}: {e}")
            break
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace")
            if proc.returncode:
                output += f"\n[exit code: {proc.returncode}]"
            outputs.append(output)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            outputs.append(f"Command timed out after {timeout}s: {command}")
            break
    return "\n".join(outputs)


class OpenAIAgent:
    """A wrapper for OpenAI Agent with MCP server and local shell skill support."""

    def __init__(
        self,
        name: str,
        instructions: str,
        mcp_servers: list | None = None,
        tools: list | None = None,
    ) -> None:
        self.agent = Agent(
            name=name,
            instructions=instructions,
            model=_get_model(),
            mcp_servers=(mcp_servers if mcp_servers is not None else []),
            tools=(tools if tools is not None else []),
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
            if "url" in mcp_srv:
                mcp_servers.append(
                    MCPServerStreamableHttp(
                        client_session_timeout_seconds=MCP_SESSION_TIMEOUT_SECONDS,
                        params={
                            "url": mcp_srv["url"],
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
        tools: list[Any] = []
        if os.getenv("SHELL_SKILLS_ENABLED"):
            skills = _load_shell_skills()
            if skills:
                environment = ShellToolLocalEnvironment(type="local", skills=skills)
                tools.append(ShellTool(executor=_shell_executor, environment=environment))

        instructions = _load_instructions()
        return cls(name, instructions=instructions, mcp_servers=mcp_servers, tools=tools)

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
