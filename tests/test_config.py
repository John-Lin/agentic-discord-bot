from __future__ import annotations

import json

import pytest

from bot.config import Configuration
from bot.config import env_flag


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isolate tests from the developer's on-disk .env file.

    Configuration.__init__ calls load_dotenv, which would otherwise read
    the repo-root .env and silently re-populate any env var the test had
    just cleared. Stub it out so tests see exactly what they set via
    monkeypatch.
    """
    monkeypatch.setattr("bot.config.load_dotenv", lambda *args, **kwargs: None)
    for key in ("DISCORD_BOT_TOKEN", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(key, raising=False)


class TestConfiguration:
    def test_reads_discord_bot_token(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "my-token")
        config = Configuration()
        assert config.discord_bot_token == "my-token"

    def test_discord_bot_token_none_when_missing(self):
        config = Configuration()
        assert config.discord_bot_token is None

    def test_reads_openai_api_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        config = Configuration()
        assert config.openai_api_key == "sk-test"

    def test_load_config_returns_default_when_file_missing(self, tmp_path):
        result = Configuration.load_config(str(tmp_path / "nonexistent.json"))
        assert result == {"mcpServers": {}}

    def test_load_config_parses_json_file(self, tmp_path):
        cfg = {"instructions": "Be helpful.", "mcpServers": {"srv": {"command": "uvx", "args": ["tool"]}}}
        config_file = tmp_path / "servers_config.json"
        config_file.write_text(json.dumps(cfg))
        result = Configuration.load_config(str(config_file))
        assert result == cfg

    def test_load_config_raises_on_invalid_json(self, tmp_path):
        config_file = tmp_path / "bad.json"
        config_file.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            Configuration.load_config(str(config_file))


class TestEnvFlag:
    def test_unset_is_false(self, monkeypatch):
        monkeypatch.delenv("MY_FLAG", raising=False)
        assert env_flag("MY_FLAG") is False

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
    def test_common_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv("MY_FLAG", value)
        assert env_flag("MY_FLAG") is False

    @pytest.mark.parametrize("value", ["FALSE", "No", "Off", "  0  "])
    def test_case_insensitive_and_whitespace(self, monkeypatch, value):
        monkeypatch.setenv("MY_FLAG", value)
        assert env_flag("MY_FLAG") is False

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on", "enabled", "anything"])
    def test_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("MY_FLAG", value)
        assert env_flag("MY_FLAG") is True
