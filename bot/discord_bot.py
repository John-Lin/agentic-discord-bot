from __future__ import annotations

import asyncio
import logging

import discord

from .agent import ConversationKey
from .agent import OpenAIAgent
from .auth import create_pairing_code
from .auth import get_dm_policy
from .auth import get_guild_config
from .auth import is_allowed
from .formatting import split_message
from .formatting import to_discord_markdown


class DiscordMCPBot:
    def __init__(self, bot_token: str | None, openai_agent: OpenAIAgent) -> None:
        if bot_token is None:
            raise ValueError("DISCORD_BOT_TOKEN is not set")

        self._token = bot_token
        self.agent = openai_agent

        intents = discord.Intents.default()
        intents.message_content = True

        self._client = discord.Client(intents=intents)
        self._client.event(self.on_message)

    async def start(self) -> None:
        await self._initialize_agent()
        await self._client.start(self._token)

    async def close(self) -> None:
        await self._client.close()

    async def _initialize_agent(self) -> None:
        await self.agent.connect()
        logging.info(f"Initialized agent {self.agent.name}")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if message.guild is None:
            await self._handle_dm(message)
        else:
            await self._handle_guild(message)

    async def _handle_dm(self, message: discord.Message) -> None:
        policy = await asyncio.to_thread(get_dm_policy)

        if policy == "disabled":
            return

        if await asyncio.to_thread(is_allowed, message.author.id):
            await self._respond(message)
            return

        # User not in allowFrom
        if policy == "allowlist":
            return  # Silent drop

        # policy == "pairing"
        code = await asyncio.to_thread(create_pairing_code, message.author.id, message.author.name)
        await message.channel.send(
            f"Your pairing code: {code}\n\n"
            f"Run this in your terminal to complete pairing:\n  uv run bot access pair {code}"
        )

    async def _handle_guild(self, message: discord.Message) -> None:
        guild_config = await asyncio.to_thread(get_guild_config, message.guild.id)
        if guild_config is None:
            return  # Guild not configured

        # Channel filter: if channels list is set, only respond in listed channels.
        allowed_channels = guild_config.get("channels", [])
        if allowed_channels and str(message.channel.id) not in allowed_channels:
            return

        allow_from = guild_config.get("allowFrom", [])
        if str(message.author.id) in allow_from:
            # User is explicitly whitelisted — no mention needed.
            await self._respond(message)
            return

        # Otherwise require @mention of the bot.
        bot_user = self._client.user
        if bot_user is not None and any(m.id == bot_user.id for m in message.mentions):
            await self._respond(message)

    async def _respond(self, message: discord.Message) -> None:
        key: ConversationKey = (message.channel.id, message.author.id)

        async with message.channel.typing():
            try:
                response = await self.agent.run(key, message.content)
            except Exception as e:
                logging.error(f"Error processing message: {e}", exc_info=True)
                await message.channel.send("I'm sorry, I encountered an error processing your request.")
                return

            formatted = to_discord_markdown(response)
            for chunk in split_message(formatted):
                await message.channel.send(chunk)
