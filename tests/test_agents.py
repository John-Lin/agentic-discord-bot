from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import create_autospec
from unittest.mock import patch

import pytest
from agents.models.interface import Model
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel

from bot.agent import MAX_TURNS
from bot.agent import OpenAIAgent
from bot.agent import _get_model


@pytest.fixture(autouse=True)
def _mock_model(monkeypatch):
    """Prevent tests from constructing a real OpenAI client."""
    monkeypatch.setattr("bot.agent._get_model", lambda: create_autospec(Model))


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
