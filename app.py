from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys

from agent_core import build_agent
from agents import enable_verbose_stdout_logging

from bot.auth import add_guild
from bot.auth import allow_user
from bot.auth import confirm_pairing
from bot.auth import get_dm_policy
from bot.auth import remove_guild
from bot.auth import remove_user
from bot.auth import set_dm_policy
from bot.config import Configuration
from bot.config import env_flag
from bot.discord_bot import DiscordMCPBot


def _configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    if env_flag("AGENT_VERBOSE_LOG"):
        enable_verbose_stdout_logging()


async def start_bot() -> None:
    _configure_logging()
    config = Configuration()

    server_config = config.load_config("servers_config.json")
    agent = build_agent("Discord Bot Agent", server_config)

    discord_bot = DiscordMCPBot(config.discord_bot_token, agent)

    try:
        await discord_bot.start()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("Shutting down...")
    except Exception as e:
        logging.error(f"Error: {e}", exc_info=True)
    finally:
        await discord_bot.close()
        await agent.cleanup()


def cmd_pair(args: argparse.Namespace) -> None:
    user_id = confirm_pairing(args.code)
    if user_id is None:
        print(f"Invalid or expired pairing code: {args.code}")
        sys.exit(1)
    print(f"Paired successfully! User ID {user_id} has been added.")


def cmd_allow(args: argparse.Namespace) -> None:
    if allow_user(args.user_id):
        print(f"User {args.user_id} allowed.")
    else:
        print(f"User {args.user_id} already allowed.")


def cmd_remove(args: argparse.Namespace) -> None:
    if remove_user(args.user_id):
        print(f"User {args.user_id} removed.")
    else:
        print(f"User {args.user_id} not found.")
        sys.exit(1)


def cmd_policy(args: argparse.Namespace) -> None:
    if args.policy is None:
        print(f"Current dmPolicy: {get_dm_policy()}")
        return
    try:
        set_dm_policy(args.policy)
    except ValueError as e:
        print(str(e))
        sys.exit(1)
    print(f"dmPolicy set to: {args.policy}")


def cmd_guild_add(args: argparse.Namespace) -> None:
    allowed_members = []
    if args.allow:
        allowed_members = [int(x) for x in args.allow.split(",")]
    channels = []
    if args.channel:
        channels = [int(x) for x in args.channel.split(",")]
    add_guild(args.guild_id, allowed_members=allowed_members, channels=channels)
    print(f"Guild {args.guild_id} added.")


def cmd_guild_remove(args: argparse.Namespace) -> None:
    if remove_guild(args.guild_id):
        print(f"Guild {args.guild_id} removed.")
    else:
        print(f"Guild {args.guild_id} not found.")
        sys.exit(1)


def _dispatch_access(
    args: argparse.Namespace,
    access_parser: argparse.ArgumentParser,
    guild_parser: argparse.ArgumentParser,
) -> None:
    if args.access_command == "pair":
        cmd_pair(args)
    elif args.access_command == "allow":
        cmd_allow(args)
    elif args.access_command == "remove":
        cmd_remove(args)
    elif args.access_command == "policy":
        cmd_policy(args)
    elif args.access_command == "guild":
        if args.guild_command == "add":
            cmd_guild_add(args)
        elif args.guild_command == "remove":
            cmd_guild_remove(args)
        else:
            guild_parser.print_help()
    else:
        access_parser.print_help()


def run() -> None:
    parser = argparse.ArgumentParser(description="Agentic Discord Bot")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Start the Discord bot")

    # access subcommands
    access_parser = subparsers.add_parser("access", help="Manage access control")
    access_sub = access_parser.add_subparsers(dest="access_command")

    # access pair
    pair_parser = access_sub.add_parser("pair", help="Confirm a pairing code from DM")
    pair_parser.add_argument("code", type=str, help="6-character pairing code")

    # access allow / remove
    allow_parser = access_sub.add_parser("allow", help="Allow a user in DMs")
    allow_parser.add_argument("user_id", type=int, help="Discord user ID")

    remove_parser = access_sub.add_parser("remove", help="Remove a user")
    remove_parser.add_argument("user_id", type=int, help="Discord user ID")

    # access policy
    policy_parser = access_sub.add_parser("policy", help="Show or set DM policy")
    policy_parser.add_argument(
        "policy",
        nargs="?",
        choices=["pairing", "allowlist", "disabled"],
        default=None,
        help="Set DM policy (omit to show current)",
    )

    # access guild subcommands
    guild_parser = access_sub.add_parser("guild", help="Manage guild access")
    guild_sub = guild_parser.add_subparsers(dest="guild_command")

    guild_add = guild_sub.add_parser("add", help="Add a guild")
    guild_add.add_argument("guild_id", type=int, help="Discord guild (server) ID")
    guild_add.add_argument("--allow", type=str, help="Comma-separated user IDs that can trigger the bot")
    guild_add.add_argument("--channel", type=str, help="Comma-separated channel IDs where bot responds")

    guild_rm = guild_sub.add_parser("remove", help="Remove a guild")
    guild_rm.add_argument("guild_id", type=int, help="Discord guild ID")

    args = parser.parse_args()

    if args.command == "access":
        _dispatch_access(args, access_parser, guild_parser)
    else:
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(start_bot())
