from __future__ import annotations

import json

import pytest

from bot.config import Configuration


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove bot-related env vars so tests start from a clean state."""
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
