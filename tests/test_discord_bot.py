"""Tests for Discord bot message handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import discord
import pytest

from bot.discord_bot import DiscordMCPBot


@pytest.fixture
def agent():
    a = MagicMock()
    a.run = AsyncMock(return_value="hello from agent")
    return a


@pytest.fixture
def bot(agent):
    b = DiscordMCPBot(bot_token="fake-token", openai_agent=agent)
    b._client = MagicMock()
    b._client.user = MagicMock()
    b._client.user.id = 999
    return b


def _make_dm_message(user_id: int, channel_id: int, text: str, bot_user_id: int = 999) -> MagicMock:
    """Create a mock Discord DM message."""
    msg = MagicMock(spec=discord.Message)
    msg.content = text
    msg.channel = MagicMock(spec=discord.DMChannel)
    msg.channel.id = channel_id
    msg.channel.send = AsyncMock()
    msg.channel.typing = MagicMock()
    msg.channel.typing.return_value.__aenter__ = AsyncMock(return_value=None)
    msg.channel.typing.return_value.__aexit__ = AsyncMock(return_value=False)
    msg.author = MagicMock()
    msg.author.id = user_id
    msg.author.bot = False
    msg.guild = None
    msg.mentions = []
    msg.reference = None
    return msg


def _make_guild_message(
    user_id: int,
    channel_id: int,
    guild_id: int,
    text: str,
    bot_user_id: int = 999,
    mentioned: bool = False,
) -> MagicMock:
    """Create a mock Discord guild (server) message."""
    msg = MagicMock(spec=discord.Message)
    msg.content = text
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.id = channel_id
    msg.channel.send = AsyncMock()
    msg.channel.typing = MagicMock()
    msg.channel.typing.return_value.__aenter__ = AsyncMock(return_value=None)
    msg.channel.typing.return_value.__aexit__ = AsyncMock(return_value=False)
    msg.author = MagicMock()
    msg.author.id = user_id
    msg.author.bot = False
    msg.guild = MagicMock()
    msg.guild.id = guild_id

    bot_user = MagicMock()
    bot_user.id = bot_user_id
    msg.mentions = [bot_user] if mentioned else []
    msg.reference = None
    return msg


class TestIgnoreBotMessages:
    @pytest.mark.anyio
    async def test_ignores_messages_from_bots(self, bot):
        msg = _make_dm_message(user_id=1, channel_id=10, text="hi")
        msg.author.bot = True

        await bot.on_message(msg)

        bot.agent.run.assert_not_called()


class TestDmHandling:
    @pytest.mark.anyio
    async def test_dm_from_allowed_user_triggers_agent(self, bot):
        msg = _make_dm_message(user_id=1, channel_id=10, text="hello")

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="allowlist"),
            patch("bot.discord_bot.is_allowed", return_value=True),
        ):
            await bot.on_message(msg)

        bot.agent.run.assert_called_once_with((10, 1), "hello")

    @pytest.mark.anyio
    async def test_dm_from_unknown_user_silently_dropped_with_allowlist(self, bot):
        msg = _make_dm_message(user_id=99, channel_id=10, text="hello")

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="allowlist"),
            patch("bot.discord_bot.is_allowed", return_value=False),
        ):
            await bot.on_message(msg)

        bot.agent.run.assert_not_called()

    @pytest.mark.anyio
    async def test_dm_dropped_when_policy_disabled(self, bot):
        msg = _make_dm_message(user_id=1, channel_id=10, text="hello")

        with patch("bot.discord_bot.get_dm_policy", return_value="disabled"):
            await bot.on_message(msg)

        bot.agent.run.assert_not_called()

    @pytest.mark.anyio
    async def test_dm_sends_agent_reply(self, bot):
        msg = _make_dm_message(user_id=1, channel_id=10, text="hi")

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="allowlist"),
            patch("bot.discord_bot.is_allowed", return_value=True),
        ):
            await bot.on_message(msg)

        msg.channel.send.assert_called_once()
        assert "hello from agent" in msg.channel.send.call_args[0][0]


class TestDmPairing:
    @pytest.mark.anyio
    async def test_dm_pairing_sends_code_to_unknown_user(self, bot):
        msg = _make_dm_message(user_id=42, channel_id=10, text="hello")

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="pairing"),
            patch("bot.discord_bot.is_allowed", return_value=False),
            patch("bot.discord_bot.create_pairing_code", return_value="ABC123"),
        ):
            await bot.on_message(msg)

        bot.agent.run.assert_not_called()
        msg.channel.send.assert_called_once()
        sent_text = msg.channel.send.call_args[0][0]
        assert "ABC123" in sent_text
        assert "pair" in sent_text.lower()

    @pytest.mark.anyio
    async def test_dm_pairing_allowed_user_bypasses_pairing(self, bot):
        msg = _make_dm_message(user_id=1, channel_id=10, text="hello")

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="pairing"),
            patch("bot.discord_bot.is_allowed", return_value=True),
        ):
            await bot.on_message(msg)

        bot.agent.run.assert_called_once()

    @pytest.mark.anyio
    async def test_dm_pairing_passes_user_id_and_name(self, bot):
        msg = _make_dm_message(user_id=42, channel_id=10, text="hello")
        msg.author.name = "testuser"

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="pairing"),
            patch("bot.discord_bot.is_allowed", return_value=False),
            patch("bot.discord_bot.create_pairing_code", return_value="XYZ789") as mock_create,
        ):
            await bot.on_message(msg)

        mock_create.assert_called_once_with(42, "testuser")


class TestGuildHandling:
    @pytest.mark.anyio
    async def test_guild_message_without_mention_ignored(self, bot):
        msg = _make_guild_message(user_id=1, channel_id=10, guild_id=500, text="hello", mentioned=False)

        with patch("bot.discord_bot.get_guild_config", return_value={"allowFrom": [], "channels": []}):
            await bot.on_message(msg)

        bot.agent.run.assert_not_called()

    @pytest.mark.anyio
    async def test_guild_message_with_mention_triggers_agent(self, bot):
        msg = _make_guild_message(
            user_id=1, channel_id=10, guild_id=500, text="<@999> hello", mentioned=True, bot_user_id=999
        )

        with patch("bot.discord_bot.get_guild_config", return_value={"allowFrom": [], "channels": []}):
            await bot.on_message(msg)

        bot.agent.run.assert_called_once_with((10, 1), "<@999> hello")

    @pytest.mark.anyio
    async def test_unconfigured_guild_silently_ignored(self, bot):
        msg = _make_guild_message(user_id=1, channel_id=10, guild_id=500, text="hello", mentioned=True)

        with patch("bot.discord_bot.get_guild_config", return_value=None):
            await bot.on_message(msg)

        bot.agent.run.assert_not_called()

    @pytest.mark.anyio
    async def test_guild_channel_filter_blocks_unlisted_channel(self, bot):
        msg = _make_guild_message(
            user_id=1, channel_id=10, guild_id=500, text="<@999> hello", mentioned=True, bot_user_id=999
        )

        with patch("bot.discord_bot.get_guild_config", return_value={"allowFrom": [], "channels": ["999"]}):
            await bot.on_message(msg)

        bot.agent.run.assert_not_called()

    @pytest.mark.anyio
    async def test_guild_channel_filter_allows_listed_channel(self, bot):
        msg = _make_guild_message(
            user_id=1, channel_id=10, guild_id=500, text="<@999> hello", mentioned=True, bot_user_id=999
        )

        with patch("bot.discord_bot.get_guild_config", return_value={"allowFrom": [], "channels": ["10"]}):
            await bot.on_message(msg)

        bot.agent.run.assert_called_once()

    @pytest.mark.anyio
    async def test_guild_allow_from_user_can_trigger_without_mention(self, bot):
        """A user in allowFrom can trigger the bot without @mention."""
        msg = _make_guild_message(user_id=1, channel_id=10, guild_id=500, text="hello", mentioned=False)

        with patch("bot.discord_bot.get_guild_config", return_value={"allowFrom": ["1"], "channels": []}):
            await bot.on_message(msg)

        bot.agent.run.assert_called_once()

    @pytest.mark.anyio
    async def test_guild_allow_from_other_user_still_needs_mention(self, bot):
        msg = _make_guild_message(user_id=2, channel_id=10, guild_id=500, text="hello", mentioned=False)

        with patch("bot.discord_bot.get_guild_config", return_value={"allowFrom": ["1"], "channels": []}):
            await bot.on_message(msg)

        bot.agent.run.assert_not_called()

    @pytest.mark.anyio
    async def test_guild_sends_reply(self, bot):
        msg = _make_guild_message(
            user_id=1, channel_id=10, guild_id=500, text="<@999> hello", mentioned=True, bot_user_id=999
        )

        with patch("bot.discord_bot.get_guild_config", return_value={"allowFrom": [], "channels": []}):
            await bot.on_message(msg)

        msg.channel.send.assert_called_once()


class TestLongMessageSplitting:
    @pytest.mark.anyio
    async def test_long_response_sent_in_multiple_messages(self, bot):
        bot.agent.run = AsyncMock(return_value="x" * 5000)
        msg = _make_dm_message(user_id=1, channel_id=10, text="hi")

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="allowlist"),
            patch("bot.discord_bot.is_allowed", return_value=True),
        ):
            await bot.on_message(msg)

        assert msg.channel.send.call_count >= 2


class TestTypingIndicator:
    @pytest.mark.anyio
    async def test_typing_context_manager_used_during_response(self, bot):
        msg = _make_dm_message(user_id=1, channel_id=10, text="hi")

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="allowlist"),
            patch("bot.discord_bot.is_allowed", return_value=True),
        ):
            await bot.on_message(msg)

        msg.channel.typing.assert_called_once()

    @pytest.mark.anyio
    async def test_send_happens_while_typing_is_active(self, bot):
        """channel.send must be called before the typing context manager exits."""
        msg = _make_dm_message(user_id=1, channel_id=10, text="hi")

        call_log: list[str] = []

        async def tracking_aexit(*args):
            call_log.append("typing_exit")
            return False

        async def tracking_send(text):
            call_log.append("send")

        msg.channel.typing.return_value.__aexit__ = tracking_aexit
        msg.channel.send = tracking_send

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="allowlist"),
            patch("bot.discord_bot.is_allowed", return_value=True),
        ):
            await bot.on_message(msg)

        assert call_log.index("send") < call_log.index("typing_exit")


class TestReplyContext:
    @pytest.mark.anyio
    async def test_no_reference_passes_content_unchanged(self, bot):
        msg = _make_dm_message(user_id=1, channel_id=10, text="hello")
        msg.reference = None

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="allowlist"),
            patch("bot.discord_bot.is_allowed", return_value=True),
        ):
            await bot.on_message(msg)

        bot.agent.run.assert_called_once_with((10, 1), "hello")

    @pytest.mark.anyio
    async def test_resolved_reference_prepends_quoted_content(self, bot):
        msg = _make_dm_message(user_id=1, channel_id=10, text="what do you think?")

        ref_msg = MagicMock()
        ref_msg.author.display_name = "Alice"
        ref_msg.content = "今天天氣如何"

        msg.reference = MagicMock()
        msg.reference.resolved = ref_msg

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="allowlist"),
            patch("bot.discord_bot.is_allowed", return_value=True),
        ):
            await bot.on_message(msg)

        expected = "[Replying to Alice: 今天天氣如何]\nwhat do you think?"
        bot.agent.run.assert_called_once_with((10, 1), expected)

    @pytest.mark.anyio
    async def test_unresolved_reference_fetches_message(self, bot):
        msg = _make_dm_message(user_id=1, channel_id=10, text="agree")

        fetched_msg = MagicMock()
        fetched_msg.author.display_name = "Bob"
        fetched_msg.content = "Python is great"

        msg.reference = MagicMock()
        msg.reference.resolved = None
        msg.reference.message_id = 42
        msg.channel.fetch_message = AsyncMock(return_value=fetched_msg)

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="allowlist"),
            patch("bot.discord_bot.is_allowed", return_value=True),
        ):
            await bot.on_message(msg)

        msg.channel.fetch_message.assert_called_once_with(42)
        expected = "[Replying to Bob: Python is great]\nagree"
        bot.agent.run.assert_called_once_with((10, 1), expected)

    @pytest.mark.anyio
    async def test_fetch_not_found_falls_back_to_plain_content(self, bot):
        msg = _make_dm_message(user_id=1, channel_id=10, text="interesting")

        msg.reference = MagicMock()
        msg.reference.resolved = None
        msg.reference.message_id = 99
        msg.channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "not found"))

        with (
            patch("bot.discord_bot.get_dm_policy", return_value="allowlist"),
            patch("bot.discord_bot.is_allowed", return_value=True),
        ):
            await bot.on_message(msg)

        bot.agent.run.assert_called_once_with((10, 1), "interesting")


class TestGuildConfigFallback:
    @pytest.mark.anyio
    async def test_guild_config_missing_channels_key_does_not_crash(self, bot):
        """A guild config without 'channels' key should not raise KeyError."""
        msg = _make_guild_message(
            user_id=1, channel_id=10, guild_id=500, text="<@999> hello", mentioned=True, bot_user_id=999
        )

        with patch("bot.discord_bot.get_guild_config", return_value={"allowFrom": []}):
            await bot.on_message(msg)

        bot.agent.run.assert_called_once()

    @pytest.mark.anyio
    async def test_guild_config_missing_allow_from_key_does_not_crash(self, bot):
        """A guild config without 'allowFrom' key should not raise KeyError."""
        msg = _make_guild_message(
            user_id=1, channel_id=10, guild_id=500, text="<@999> hello", mentioned=True, bot_user_id=999
        )

        with patch("bot.discord_bot.get_guild_config", return_value={"channels": []}):
            await bot.on_message(msg)

        bot.agent.run.assert_called_once()
