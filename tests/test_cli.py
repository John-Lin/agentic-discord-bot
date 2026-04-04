"""Tests for the CLI entry point in app.py."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from bot.auth import allow_user
from bot.auth import create_pairing_code
from bot.auth import get_dm_policy
from bot.auth import is_allowed
from bot.auth import load_auth
from bot.auth import save_auth


@pytest.fixture(autouse=True)
def auth_file(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.auth.AUTH_FILE", tmp_path / "access.json")
    monkeypatch.setattr("bot.auth.PENDING_FILE", tmp_path / ".access.pending.json")
    return tmp_path


def _run(args: list[str]) -> int:
    """Run the CLI with the given args; return exit code (0 if no SystemExit)."""
    import app

    with patch("sys.argv", ["bot"] + args):
        try:
            app.run()
            return 0
        except SystemExit as e:
            return int(e.code) if e.code is not None else 0


class TestAccessAllow:
    def test_allow_adds_user(self):
        _run(["access", "allow", "123"])
        assert is_allowed(123) is True

    def test_allow_reports_already_present(self, capsys):
        allow_user(123)
        _run(["access", "allow", "123"])
        out = capsys.readouterr().out
        assert "already" in out.lower()


class TestAccessRemove:
    def test_remove_existing_user(self):
        allow_user(123)
        code = _run(["access", "remove", "123"])
        assert code == 0
        assert is_allowed(123) is False

    def test_remove_nonexistent_user_exits_nonzero(self):
        code = _run(["access", "remove", "999"])
        assert code != 0


class TestAccessPair:
    def test_pair_valid_code(self):
        code = create_pairing_code(123, "john")
        exit_code = _run(["access", "pair", code])
        assert exit_code == 0
        assert is_allowed(123) is True

    def test_pair_invalid_code_exits_nonzero(self):
        code = _run(["access", "pair", "BADCODE"])
        assert code != 0

    def test_pair_prints_success(self, capsys):
        code = create_pairing_code(123, "john")
        _run(["access", "pair", code])
        out = capsys.readouterr().out
        assert "paired" in out.lower() or "success" in out.lower()


class TestAccessPolicy:
    def test_show_policy(self, capsys):
        _run(["access", "policy"])
        out = capsys.readouterr().out
        assert "pairing" in out

    def test_set_policy_disabled(self):
        _run(["access", "policy", "disabled"])
        assert get_dm_policy() == "disabled"

    def test_set_policy_allowlist(self):
        _run(["access", "policy", "disabled"])
        _run(["access", "policy", "allowlist"])
        assert get_dm_policy() == "allowlist"

    def test_set_policy_pairing(self):
        _run(["access", "policy", "disabled"])
        _run(["access", "policy", "pairing"])
        assert get_dm_policy() == "pairing"

    def test_set_invalid_policy_exits_nonzero(self):
        code = _run(["access", "policy", "bogus"])
        assert code != 0


class TestAccessGuildAdd:
    def test_add_guild(self):
        from bot.auth import get_guild_config

        _run(["access", "guild", "add", "111222333"])
        config = get_guild_config(111222333)
        assert config is not None
        assert config["allowFrom"] == []
        assert config["channels"] == []

    def test_add_guild_with_allow(self):
        from bot.auth import get_guild_config

        _run(["access", "guild", "add", "111222333", "--allow", "111,222"])
        config = get_guild_config(111222333)
        assert config["allowFrom"] == ["111", "222"]

    def test_add_guild_with_channel(self):
        from bot.auth import get_guild_config

        _run(["access", "guild", "add", "111222333", "--channel", "555,666"])
        config = get_guild_config(111222333)
        assert config["channels"] == ["555", "666"]


class TestAccessGuildRemove:
    def test_remove_guild(self):
        from bot.auth import add_guild
        from bot.auth import get_guild_config

        add_guild(111222333)
        code = _run(["access", "guild", "remove", "111222333"])
        assert code == 0
        assert get_guild_config(111222333) is None

    def test_remove_nonexistent_guild_exits_nonzero(self):
        code = _run(["access", "guild", "remove", "999999"])
        assert code != 0
