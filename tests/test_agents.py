from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import create_autospec
from unittest.mock import patch

import pytest
from agents import ShellTool
from agents.models.interface import Model
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel

from bot.agent import MAX_TURNS
from bot.agent import OpenAIAgent
from bot.agent import _get_model
from bot.agent import _parse_skill_description
from bot.agent import _shell_executor


@pytest.fixture
def _stub_instructions(monkeypatch):
    """Stub out instructions.md loading for from_dict tests."""
    monkeypatch.setattr("bot.agent._load_instructions", lambda: "stub instructions")


@pytest.fixture(autouse=True)
def _mock_model(monkeypatch):
    """Prevent tests from constructing a real OpenAI client and isolate shell env vars."""
    monkeypatch.setattr("bot.agent._get_model", lambda: create_autospec(Model))
    monkeypatch.delenv("SHELL_ENABLED", raising=False)
    monkeypatch.delenv("SHELL_SKILLS_DIR", raising=False)


class TestGetModel:
    def test_returns_responses_model_by_default(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_TYPE", raising=False)

        with patch("bot.agent.AsyncOpenAI", return_value=MagicMock()):
            model = _get_model()
        assert isinstance(model, OpenAIResponsesModel)

    def test_returns_chat_completions_model_when_api_type_is_chat_completions(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_TYPE", "chat_completions")

        with patch("bot.agent.AsyncOpenAI", return_value=MagicMock()):
            model = _get_model()
        assert isinstance(model, OpenAIChatCompletionsModel)


class TestPerConversationHistory:
    def test_separate_conversations_have_independent_history(self):
        """Different (channel_id, user_id) keys maintain separate histories."""
        agent = OpenAIAgent(name="test", instructions="test-prompt")
        key1 = (100, 1)
        key2 = (100, 2)
        agent.append_user_message(key1, "hello from user 1")
        agent.append_user_message(key2, "hello from user 2")

        msgs1 = agent.get_messages(key1)
        msgs2 = agent.get_messages(key2)

        assert len(msgs1) == 1
        assert len(msgs2) == 1
        assert msgs1[0]["content"] == "hello from user 1"
        assert msgs2[0]["content"] == "hello from user 2"

    def test_same_thread_accumulates_messages(self):
        agent = OpenAIAgent(name="test", instructions="test-prompt")
        key = (100, 1)
        agent.append_user_message(key, "first")
        agent.append_user_message(key, "second")

        msgs = agent.get_messages(key)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "first"
        assert msgs[1]["content"] == "second"

    def test_unknown_conversation_returns_empty(self):
        agent = OpenAIAgent(name="test", instructions="test-prompt")
        assert agent.get_messages((999, 999)) == []

    def test_set_messages_replaces_history(self):
        agent = OpenAIAgent(name="test", instructions="test-prompt")
        key = (100, 1)
        agent.append_user_message(key, "old")
        new_msgs = [{"role": "user", "content": "replaced"}]
        agent.set_messages(key, new_msgs)
        assert agent.get_messages(key) == new_msgs

    def test_set_messages_does_not_affect_other_conversations(self):
        agent = OpenAIAgent(name="test", instructions="test-prompt")
        key1 = (100, 1)
        key2 = (100, 2)
        agent.append_user_message(key1, "chat 1")
        agent.append_user_message(key2, "chat 2")
        agent.set_messages(key1, [])
        assert agent.get_messages(key1) == []
        assert len(agent.get_messages(key2)) == 1

    def test_different_channels_same_user_are_independent(self):
        """Same user in different channels should have independent histories."""
        agent = OpenAIAgent(name="test", instructions="test-prompt")
        key_ch1 = (100, 1)
        key_ch2 = (200, 1)
        agent.append_user_message(key_ch1, "in channel 100")
        agent.append_user_message(key_ch2, "in channel 200")

        assert agent.get_messages(key_ch1)[0]["content"] == "in channel 100"
        assert agent.get_messages(key_ch2)[0]["content"] == "in channel 200"


class TestInstructions:
    def test_custom_instructions(self):
        agent = OpenAIAgent(name="test", instructions="Be a Discord bot.")
        assert agent.agent.instructions == "Be a Discord bot."

    def test_from_dict_loads_instructions_from_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "instructions.md").write_text("From file prompt.", encoding="utf-8")
        agent = OpenAIAgent.from_dict("test", {"mcpServers": {}})
        assert agent.agent.instructions == "From file prompt."

    def test_from_dict_fails_fast_when_instructions_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(FileNotFoundError, match="Instructions file not found"):
            OpenAIAgent.from_dict("test", {"mcpServers": {}})


class TestHistoryTruncation:
    def test_default_max_turns(self):
        assert MAX_TURNS == 10

    def test_truncate_keeps_recent_turns(self):
        agent = OpenAIAgent(name="test", instructions="test-prompt")
        key = (100, 1)
        for i in range(30):
            agent.set_messages(
                key,
                agent.get_messages(key)
                + [
                    {"role": "user", "content": f"user-{i}"},
                    {"role": "assistant", "content": f"assistant-{i}"},
                ],
            )

        agent.truncate_history(key)
        msgs = agent.get_messages(key)

        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs) == MAX_TURNS
        assert user_msgs[0]["content"] == "user-20"
        assert user_msgs[-1]["content"] == "user-29"

    def test_no_truncation_when_under_limit(self):
        agent = OpenAIAgent(name="test", instructions="test-prompt")
        key = (100, 1)
        for i in range(3):
            agent.set_messages(
                key,
                agent.get_messages(key)
                + [
                    {"role": "user", "content": f"user-{i}"},
                    {"role": "assistant", "content": f"assistant-{i}"},
                ],
            )

        agent.truncate_history(key)
        msgs = agent.get_messages(key)
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs) == 3


@pytest.mark.usefixtures("_stub_instructions")
class TestShellToolConfiguration:
    def _get_shell_tools(self, agent: OpenAIAgent) -> list[ShellTool]:
        return [t for t in agent.agent.tools if isinstance(t, ShellTool)]

    def _configure_env(self, monkeypatch, *, enabled: bool, skills_dir: Path | None = None) -> None:
        if enabled:
            monkeypatch.setenv("SHELL_ENABLED", "1")
        else:
            monkeypatch.delenv("SHELL_ENABLED", raising=False)
        if skills_dir is not None:
            monkeypatch.setenv("SHELL_SKILLS_DIR", str(skills_dir))
        else:
            monkeypatch.delenv("SHELL_SKILLS_DIR", raising=False)

    def _make_skill(self, parent: Path, name: str, description: str = "desc") -> Path:
        skill_dir = parent / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n")
        return skill_dir

    def test_disabled_by_default(self, tmp_path, monkeypatch):
        """SHELL_ENABLED unset means no ShellTool, even if SHELL_SKILLS_DIR is set."""
        self._make_skill(tmp_path, "my-skill")
        self._configure_env(monkeypatch, enabled=False, skills_dir=tmp_path)

        agent = OpenAIAgent.from_dict("test", {"mcpServers": {}})

        assert self._get_shell_tools(agent) == []

    def test_orphaned_skills_dir_without_shell_enabled_warns(self, tmp_path, monkeypatch, caplog):
        self._configure_env(monkeypatch, enabled=False, skills_dir=tmp_path)

        with caplog.at_level("WARNING", logger="root"):
            agent = OpenAIAgent.from_dict("test", {"mcpServers": {}})

        assert self._get_shell_tools(agent) == []
        assert any(
            "SHELL_SKILLS_DIR" in record.message and "SHELL_ENABLED" in record.message for record in caplog.records
        )

    def test_shell_enabled_without_skills_dir_adds_bare_shell(self, tmp_path, monkeypatch):
        self._configure_env(monkeypatch, enabled=True, skills_dir=None)

        agent = OpenAIAgent.from_dict("test", {"mcpServers": {}})

        shell_tools = self._get_shell_tools(agent)
        assert len(shell_tools) == 1
        assert shell_tools[0].environment == {"type": "local"}

    def test_shell_enabled_with_skills_dir_mounts_skills(self, tmp_path, monkeypatch):
        skill_dir = self._make_skill(tmp_path, "my-skill", description="A test skill")
        self._configure_env(monkeypatch, enabled=True, skills_dir=tmp_path)

        agent = OpenAIAgent.from_dict("test", {"mcpServers": {}})

        shell_tool = self._get_shell_tools(agent)[0]
        skill = shell_tool.environment["skills"][0]
        assert skill["name"] == "my-skill"
        assert skill["description"] == "A test skill"
        assert skill["path"] == str(skill_dir)

    def test_skills_dir_missing_falls_back_to_bare_shell_with_warning(self, tmp_path, monkeypatch, caplog):
        self._configure_env(monkeypatch, enabled=True, skills_dir=tmp_path / "nonexistent")

        with caplog.at_level("WARNING", logger="root"):
            agent = OpenAIAgent.from_dict("test", {"mcpServers": {}})

        shell_tools = self._get_shell_tools(agent)
        assert len(shell_tools) == 1
        assert shell_tools[0].environment == {"type": "local"}
        assert any("yielded no skills" in record.message for record in caplog.records)

    def test_multiple_skills_all_mounted(self, tmp_path, monkeypatch):
        self._make_skill(tmp_path, "skill-a")
        self._make_skill(tmp_path, "skill-b")
        self._configure_env(monkeypatch, enabled=True, skills_dir=tmp_path)

        agent = OpenAIAgent.from_dict("test", {"mcpServers": {}})

        shell_tool = self._get_shell_tools(agent)[0]
        assert len(shell_tool.environment["skills"]) == 2

    def test_directory_without_skill_md_is_skipped(self, tmp_path, monkeypatch):
        (tmp_path / "not-a-skill").mkdir()
        self._make_skill(tmp_path, "real-skill")
        self._configure_env(monkeypatch, enabled=True, skills_dir=tmp_path)

        agent = OpenAIAgent.from_dict("test", {"mcpServers": {}})

        shell_tool = self._get_shell_tools(agent)[0]
        skills = shell_tool.environment["skills"]
        assert len(skills) == 1
        assert skills[0]["name"] == "real-skill"

    def test_mcp_servers_and_shell_skills_coexist(self, tmp_path, monkeypatch):
        self._make_skill(tmp_path, "s")
        self._configure_env(monkeypatch, enabled=True, skills_dir=tmp_path)

        config = {"mcpServers": {"my-mcp": {"command": "uvx", "args": ["something"]}}}
        agent = OpenAIAgent.from_dict("test", config)

        assert len(agent.agent.mcp_servers) == 1
        assert len(self._get_shell_tools(agent)) == 1

    def test_unreadable_utf8_skill_file_is_skipped(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad-skill"
        bad.mkdir()
        (bad / "SKILL.md").write_bytes(b"\xff\xfe\x00\x00")
        self._make_skill(tmp_path, "good-skill", description="good")
        self._configure_env(monkeypatch, enabled=True, skills_dir=tmp_path)

        agent = OpenAIAgent.from_dict("test", {"mcpServers": {}})

        shell_tool = self._get_shell_tools(agent)[0]
        skills = shell_tool.environment["skills"]
        assert len(skills) == 1
        assert skills[0]["name"] == "good-skill"

    def test_oserror_reading_skill_file_is_skipped(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad-skill"
        bad.mkdir()
        bad_file = bad / "SKILL.md"
        bad_file.write_text("---\nname: bad\ndescription: bad\n---\n")
        self._make_skill(tmp_path, "good-skill", description="good")
        self._configure_env(monkeypatch, enabled=True, skills_dir=tmp_path)

        original_read_text = Path.read_text

        def _read_text(self: Path, *args, **kwargs):
            if self == bad_file:
                raise OSError("permission denied")
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", _read_text)

        agent = OpenAIAgent.from_dict("test", {"mcpServers": {}})

        shell_tool = self._get_shell_tools(agent)[0]
        skills = shell_tool.environment["skills"]
        assert len(skills) == 1
        assert skills[0]["name"] == "good-skill"


class TestParseSkillDescription:
    def test_unquoted_description(self):
        content = "---\nname: my-skill\ndescription: A test skill\n---\nBody text."
        assert _parse_skill_description(content) == "A test skill"

    def test_double_quoted_description(self):
        content = '---\nname: my-skill\ndescription: "A quoted skill"\n---\n'
        assert _parse_skill_description(content) == "A quoted skill"

    def test_single_quoted_description(self):
        content = "---\nname: my-skill\ndescription: 'Single quoted'\n---\n"
        assert _parse_skill_description(content) == "Single quoted"

    def test_no_frontmatter(self):
        content = "Just a plain markdown file."
        assert _parse_skill_description(content) == ""

    def test_no_description_field(self):
        content = "---\nname: my-skill\n---\nBody."
        assert _parse_skill_description(content) == ""

    def test_unclosed_frontmatter(self):
        content = "---\nname: my-skill\ndescription: never closed"
        assert _parse_skill_description(content) == ""

    def test_empty_description(self):
        content = "---\nname: my-skill\ndescription:\n---\n"
        assert _parse_skill_description(content) == ""

    def test_description_with_colon_in_value(self):
        content = "---\ndescription: Run this: do stuff\n---\n"
        assert _parse_skill_description(content) == "Run this: do stuff"


def _make_shell_request(commands: list[str], timeout_ms: int | None = None):
    """Build a minimal object matching the ShellCommandRequest interface."""
    from types import SimpleNamespace

    action = SimpleNamespace(commands=commands, timeout_ms=timeout_ms)
    data = SimpleNamespace(action=action)
    return SimpleNamespace(data=data)


class TestShellExecutor:
    @pytest.mark.anyio
    async def test_single_command_returns_stdout(self):
        request = _make_shell_request(["echo hello"])
        result = await _shell_executor(request)
        assert result.strip() == "hello"

    @pytest.mark.anyio
    async def test_multiple_commands_combined(self):
        request = _make_shell_request(["echo first", "echo second"])
        result = await _shell_executor(request)
        assert "first" in result
        assert "second" in result
        assert result.index("first") < result.index("second")

    @pytest.mark.anyio
    async def test_stderr_merged_into_stdout(self):
        request = _make_shell_request(["echo err >&2"])
        result = await _shell_executor(request)
        assert result.strip() == "err"

    @pytest.mark.anyio
    async def test_command_timeout_kills_process(self):
        request = _make_shell_request(["sleep 30"], timeout_ms=100)
        result = await _shell_executor(request)
        assert "timed out" in result.lower()

    @pytest.mark.anyio
    async def test_nonzero_exit_code_appends_exit_code(self):
        request = _make_shell_request(["echo failing && exit 1"])
        result = await _shell_executor(request)
        assert "failing" in result
        assert "[exit code: 1]" in result

    @pytest.mark.anyio
    async def test_zero_exit_code_no_suffix(self):
        request = _make_shell_request(["echo ok"])
        result = await _shell_executor(request)
        assert "exit code" not in result

    @pytest.mark.anyio
    async def test_timeout_ms_none_uses_default(self):
        """When timeout_ms is None, SHELL_TIMEOUT is used (command completes fine)."""
        request = _make_shell_request(["echo ok"], timeout_ms=None)
        result = await _shell_executor(request)
        assert result.strip() == "ok"

    @pytest.mark.anyio
    async def test_timeout_stops_remaining_commands(self):
        """After a timeout, subsequent commands are not executed."""
        request = _make_shell_request(["sleep 30", "echo should-not-run"], timeout_ms=100)
        result = await _shell_executor(request)
        assert "timed out" in result.lower()
        assert "should-not-run" not in result

    @pytest.mark.anyio
    async def test_subprocess_oserror_returns_error_message(self, monkeypatch):
        """When create_subprocess_shell raises OSError, return error text instead of crashing."""
        import asyncio as _asyncio

        async def _failing_shell(*args, **kwargs):
            raise OSError("fork failed")

        monkeypatch.setattr(_asyncio, "create_subprocess_shell", _failing_shell)

        request = _make_shell_request(["echo hello"])
        result = await _shell_executor(request)
        assert "fork failed" in result
