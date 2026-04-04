from __future__ import annotations

import fcntl
import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

AUTH_FILE: str | Path = "access.json"

VALID_DM_POLICIES = ("allowlist", "disabled")


def _default_auth() -> dict[str, Any]:
    return {"dmPolicy": "allowlist", "allowFrom": [], "guilds": {}}


def load_auth() -> dict[str, Any]:
    path = Path(AUTH_FILE)
    if not path.exists():
        return _default_auth()
    with open(path) as f:
        data = json.load(f)
    for key, default in _default_auth().items():
        data.setdefault(key, type(default)() if not isinstance(default, str) else default)
    return data


def save_auth(data: dict[str, Any]) -> None:
    with open(Path(AUTH_FILE), "w") as f:
        json.dump(data, f, indent=2)


@contextmanager
def locked_auth() -> Generator[dict[str, Any]]:
    """Load auth data under an exclusive file lock; save only on clean exit."""
    lock_path = Path(str(AUTH_FILE) + ".lock")
    lock_path.touch(exist_ok=True)
    with open(lock_path) as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            data = load_auth()
            yield data
            save_auth(data)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


# --- DM policy ---


def get_dm_policy() -> str:
    return load_auth()["dmPolicy"]


def set_dm_policy(policy: str) -> None:
    if policy not in VALID_DM_POLICIES:
        raise ValueError(f"invalid dmPolicy: {policy!r} (must be one of {VALID_DM_POLICIES})")
    with locked_auth() as data:
        data["dmPolicy"] = policy


# --- User allowlist ---


def is_allowed(user_id: int) -> bool:
    return str(user_id) in load_auth()["allowFrom"]


def allow_user(user_id: int) -> bool:
    """Add a user to allowFrom. Returns False if already present."""
    uid_str = str(user_id)
    with locked_auth() as data:
        if uid_str in data["allowFrom"]:
            return False
        data["allowFrom"].append(uid_str)
    return True


def remove_user(user_id: int) -> bool:
    uid_str = str(user_id)
    with locked_auth() as data:
        if uid_str not in data["allowFrom"]:
            return False
        data["allowFrom"].remove(uid_str)
    return True


# --- Guild access ---


def get_guild_config(guild_id: int) -> dict[str, Any] | None:
    return load_auth()["guilds"].get(str(guild_id))


def add_guild(
    guild_id: int,
    allowed_members: list[int] | None = None,
    channels: list[int] | None = None,
) -> None:
    with locked_auth() as data:
        data["guilds"][str(guild_id)] = {
            "allowFrom": [str(m) for m in (allowed_members or [])],
            "channels": [str(c) for c in (channels or [])],
        }


def remove_guild(guild_id: int) -> bool:
    with locked_auth() as data:
        if str(guild_id) not in data["guilds"]:
            return False
        del data["guilds"][str(guild_id)]
    return True


def list_guilds() -> dict[str, Any]:
    return load_auth()["guilds"]
