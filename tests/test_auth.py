from __future__ import annotations

import pytest

import bot.auth as auth_mod
from bot.auth import add_guild
from bot.auth import allow_user
from bot.auth import get_dm_policy
from bot.auth import get_guild_config
from bot.auth import is_allowed
from bot.auth import list_guilds
from bot.auth import load_auth
from bot.auth import locked_auth
from bot.auth import remove_guild
from bot.auth import remove_user
from bot.auth import save_auth
from bot.auth import set_dm_policy


@pytest.fixture(autouse=True)
def auth_file(tmp_path, monkeypatch):
    """Use temporary files for every test."""
    monkeypatch.setattr("bot.auth.AUTH_FILE", tmp_path / "access.json")
    return tmp_path


class TestLoadSave:
    def test_load_returns_default_when_file_missing(self):
        data = load_auth()
        assert data == {
            "dmPolicy": "allowlist",
            "allowFrom": [],
            "guilds": {},
        }

    def test_save_and_load_roundtrip(self):
        data = {"dmPolicy": "allowlist", "allowFrom": ["123"], "guilds": {}}
        save_auth(data)
        assert load_auth() == data

    def test_load_backfills_missing_dm_policy(self):
        save_auth({"allowFrom": ["123"], "guilds": {}})
        data = load_auth()
        assert data["dmPolicy"] == "allowlist"

    def test_load_backfills_missing_guilds(self):
        save_auth({"dmPolicy": "allowlist", "allowFrom": []})
        data = load_auth()
        assert data["guilds"] == {}


class TestIsAllowed:
    def test_unknown_user_not_allowed(self):
        assert is_allowed(999) is False

    def test_allowed_user(self):
        save_auth({"dmPolicy": "allowlist", "allowFrom": ["123"], "guilds": {}})
        assert is_allowed(123) is True

    def test_allowed_user_compared_as_string(self):
        save_auth({"dmPolicy": "allowlist", "allowFrom": ["123"], "guilds": {}})
        assert is_allowed(123) is True
        assert is_allowed(456) is False


class TestAllowRemoveUser:
    def test_allow_user_adds_to_allow_from(self):
        result = allow_user(123)
        assert result is True
        assert is_allowed(123) is True

    def test_allow_user_stores_as_string(self):
        allow_user(123)
        data = load_auth()
        assert "123" in data["allowFrom"]

    def test_allow_user_returns_false_if_already_present(self):
        allow_user(123)
        assert allow_user(123) is False

    def test_remove_existing_user(self):
        save_auth({"dmPolicy": "allowlist", "allowFrom": ["123", "456"], "guilds": {}})
        assert remove_user(123) is True
        assert is_allowed(123) is False
        assert is_allowed(456) is True

    def test_remove_nonexistent_user(self):
        assert remove_user(999) is False

    def test_remove_user_idempotent(self):
        save_auth({"dmPolicy": "allowlist", "allowFrom": ["123"], "guilds": {}})
        assert remove_user(123) is True
        assert remove_user(123) is False


class TestDmPolicy:
    def test_default_policy_is_allowlist(self):
        assert get_dm_policy() == "allowlist"

    def test_set_policy_disabled(self):
        set_dm_policy("disabled")
        assert get_dm_policy() == "disabled"

    def test_set_policy_allowlist(self):
        set_dm_policy("disabled")
        set_dm_policy("allowlist")
        assert get_dm_policy() == "allowlist"

    def test_set_invalid_policy_raises(self):
        with pytest.raises(ValueError, match="invalid"):
            set_dm_policy("bogus")

    def test_policy_persisted(self):
        set_dm_policy("disabled")
        data = load_auth()
        assert data["dmPolicy"] == "disabled"


class TestGuildAccess:
    def test_add_guild_default_config(self):
        add_guild(123456789)
        config = get_guild_config(123456789)
        assert config is not None
        assert config["allowFrom"] == []
        assert config["channels"] == []

    def test_add_guild_with_allowed_members(self):
        add_guild(123456789, allowed_members=[111, 222])
        config = get_guild_config(123456789)
        assert config["allowFrom"] == ["111", "222"]

    def test_add_guild_with_channels(self):
        add_guild(123456789, channels=[999, 888])
        config = get_guild_config(123456789)
        assert config["channels"] == ["999", "888"]

    def test_get_guild_config_unknown_guild(self):
        assert get_guild_config(9999) is None

    def test_remove_guild(self):
        add_guild(123456789)
        removed = remove_guild(123456789)
        assert removed is True
        assert get_guild_config(123456789) is None

    def test_remove_guild_unknown(self):
        assert remove_guild(9999) is False

    def test_list_guilds_empty(self):
        assert list_guilds() == {}

    def test_list_guilds(self):
        add_guild(111111)
        add_guild(222222, channels=[999])
        guilds = list_guilds()
        assert len(guilds) == 2
        assert str(111111) in guilds
        assert str(222222) in guilds

    def test_add_guild_updates_existing(self):
        add_guild(123456789)
        add_guild(123456789, allowed_members=[111], channels=[999])
        config = get_guild_config(123456789)
        assert config["allowFrom"] == ["111"]
        assert config["channels"] == ["999"]


class TestLockedAuth:
    def test_locked_auth_loads_data(self):
        save_auth({"dmPolicy": "allowlist", "allowFrom": ["123"], "guilds": {}})
        with locked_auth() as data:
            assert data["allowFrom"] == ["123"]

    def test_locked_auth_saves_on_exit(self):
        with locked_auth() as data:
            data["allowFrom"].append("456")
        assert load_auth()["allowFrom"] == ["456"]

    def test_locked_auth_does_not_save_on_exception(self):
        save_auth({"dmPolicy": "allowlist", "allowFrom": ["123"], "guilds": {}})
        with pytest.raises(RuntimeError), locked_auth() as data:
            data["allowFrom"].append("999")
            raise RuntimeError("boom")
        assert load_auth()["allowFrom"] == ["123"]
