# agentic-discord-bot

A Discord bot powered by [agent-core](https://github.com/John-Lin/agent-core) that interacts with [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) servers. Supports two interchangeable providers:

- **OpenAI** (default) — via [OpenAI Agents SDK](https://github.com/openai/openai-agents-python); works with OpenAI and Azure OpenAI v1.
- **Claude** — via [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/).

Switch providers by setting `"provider"` in `servers_config.json`.

See also: [agentic-slackbot](https://github.com/John-Lin/agentic-slackbot) and [agentic-telegram-bot](https://github.com/John-Lin/agentic-telegram-bot) — similar bots for Slack and Telegram.

## Features

- Responds to @mentions in guild channels and threads
- DM support with allowlist access control
- Per-(channel, user) conversation history — each user maintains an independent context per channel/thread
- Configurable guild access with per-channel and per-user filters
- Connects to any MCP server via `servers_config.json`
- Optional local shell: `ShellTool` (OpenAI) or `Bash`/`Read`/`Glob`/`Grep` (Claude), controlled by `SHELL_ENABLED`
- Supports OpenAI, Azure OpenAI v1, and Anthropic Claude

## Install Dependencies

```bash
uv sync
```

## Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a new application.
2. Under **Bot**, enable the following **Privileged Gateway Intents**:
   - **Message Content Intent** (required to read message text)
3. Under **OAuth2 → URL Generator**, select scopes `bot` and permissions:
   - Read Messages/View Channels
   - Send Messages
   - Read Message History
4. Use the generated URL to invite the bot to your server.
5. Copy the bot token from the **Bot** page.

## Environment Variables

Create a `.env` file in the root directory. Set the key(s) for the provider you plan to use:

```
DISCORD_BOT_TOKEN=""

# OpenAI provider (default)
OPENAI_API_KEY=""

# Claude provider
# ANTHROPIC_API_KEY=""

# Local shell (disabled by default)
# SHELL_ENABLED=1
# SHELL_SKILLS_DIR="./skills"  # OpenAI only; mount skills alongside the shell

# Optional verbose OpenAI Agents SDK logging (OpenAI only)
# AGENT_VERBOSE_LOG=1
```

If you are using Azure OpenAI (v1 API):

```
DISCORD_BOT_TOKEN=""
OPENAI_API_KEY=""
OPENAI_BASE_URL="https://<resource-name>.openai.azure.com/openai/v1/"
```

## Agent Instructions

Create an `instructions.md` file in the project root with the agent system prompt:

```markdown
You are a helpful financial assistant. Help users look up stock data,
news, and market information. Always include ticker symbols.
Respond in the user's language. Keep responses concise.
```

An example is provided in `instructions.md.example`. The bot will fail to start if this file is missing.

## Provider & MCP Server Configuration (Optional)

Create a `servers_config.json` to choose a provider and connect MCP servers. If the file is absent, the bot starts with the default OpenAI provider and no tools.

### OpenAI provider (default)

```json
{
  "provider": "openai",
  "model": "gpt-5.4",
  "mcpServers": {
    "my-server": {
      "command": "uvx",
      "args": ["my-mcp-server"]
    }
  }
}
```

`provider` defaults to `"openai"`; `model` defaults to `gpt-5.4`. Each MCP server also accepts `timeout` (seconds, default `30.0`) and `enabled` (default `true`).

### Claude provider

```json
{
  "provider": "claude",
  "model": "claude-sonnet-4-6",
  "maxTurns": 10,
  "allowedTools": ["WebFetch"],
  "mcpServers": {
    "my-stdio": {
      "command": "python",
      "args": ["-m", "srv"]
    },
    "my-http": {
      "url": "https://example.com/mcp",
      "headers": {"Authorization": "Bearer x"}
    }
  }
}
```

Requires `ANTHROPIC_API_KEY`. `allowedTools` extends the built-in set (`Bash`/`Read`/`Glob`/`Grep` when `SHELL_ENABLED=1`) with additional Claude tools such as `WebFetch`, `Write`, `Edit`. Billing/rate-limit/`error_max_turns` errors are surfaced to the channel as a readable message.

### HTTP MCP servers (OpenAI, Streamable HTTP)

```json
{
  "mcpServers": {
    "my-server": {
      "url": "https://mcp.example.com/mcp",
      "headers": {
        "Accept": "application/json, text/event-stream"
      }
    }
  }
}
```

### Local MCP servers (OpenAI, via `uv --directory`)

```json
{
  "mcpServers": {
    "my-server": {
      "command": "uv",
      "args": ["--directory", "/path/to/my-server", "run", "my-entrypoint"]
    }
  }
}
```

## Running the Bot

```bash
uv run bot
```

## Access Control

All access is managed via `access.json` (auto-created, gitignored).

### DM Policy

| Policy | Behaviour |
|---|---|
| `pairing` (default) | Unknown users receive a 6-character pairing code via DM |
| `allowlist` | Only users in the allowlist can DM the bot |
| `disabled` | All DMs are silently dropped |

```bash
# Show current policy
uv run bot access policy

# Set policy
uv run bot access policy <pairing|allowlist|disabled>
```

When `dmPolicy` is `pairing`, confirm the code in your terminal:

```bash
uv run bot access pair <CODE>
```

### Users

Manage which users can DM the bot:

```bash
uv run bot access allow <USER_ID>
uv run bot access remove <USER_ID>
```

To find a user's ID in Discord, enable **Developer Mode** (Settings → Advanced), then right-click the user and select **Copy User ID**.

### Guilds

Guilds (servers) are blocked by default. Add a guild to allow the bot to respond there:

```bash
# Add a guild (bot responds to @mentions from any member)
uv run bot access guild add <GUILD_ID>

# Restrict to specific channels
uv run bot access guild add <GUILD_ID> --channel 111,222

# Restrict to specific members (no @mention needed for these users)
uv run bot access guild add <GUILD_ID> --allow 333,444

# Combine both
uv run bot access guild add <GUILD_ID> --channel 111,222 --allow 333,444

# Remove a guild
uv run bot access guild remove <GUILD_ID>
```

To find IDs in Discord, enable **Developer Mode**, then right-click the server icon for the guild ID or right-click a channel for the channel ID.

**Trigger logic in guilds:**

- Any member can trigger the bot by @mentioning it.
- Members listed in `--allow` can trigger the bot without @mention.
- If `--channel` is set, the bot only responds in those channels.

## Conversation History

Each user has an independent conversation history per channel or thread. Replying to the bot's message continues the same conversation. Starting a thread creates a fresh context for that thread.

History is capped at the last N turns per conversation (default 10, configurable via `maxTurns` in `servers_config.json`).

## Local Shell (Optional)

Local shell tools are **disabled by default**. Enable with:

```
SHELL_ENABLED=1
```

Behaviour depends on the provider:

- **OpenAI**: attaches a `ShellTool` (bare local shell). Optionally mount a skills directory with `SHELL_SKILLS_DIR`.
- **Claude**: allows the SDK's built-in `Bash`, `Read`, `Glob`, `Grep` tools. Extra Claude tools (e.g. `WebFetch`, `Write`, `Edit`) are declared via `"allowedTools"` in `servers_config.json`. `SHELL_SKILLS_DIR` is ignored.

### Shell Skills (OpenAI only)

You can mount a skills directory alongside the shell. Each immediate subdirectory containing a `SKILL.md` file is registered as a skill and exposed to the agent as a hint (skills are advisory metadata — they do **not** sandbox command execution).

```
SHELL_ENABLED=1
SHELL_SKILLS_DIR="./skills"
```

`SHELL_SKILLS_DIR` is ignored unless `SHELL_ENABLED` is set and the OpenAI provider is in use. If the directory is missing or contains no valid skills, the bot falls back to a bare shell and logs a warning.

The `SKILL.md` file should have YAML frontmatter with `name` and `description` fields:

```markdown
---
name: my-skill
description: A brief description of what this skill does
---

Detailed instructions for the agent...
```

## Docker

```bash
docker build -t agentic-discord-bot .

# OpenAI provider
docker run -d \
  --name discordbot \
  -e DISCORD_BOT_TOKEN="" \
  -e OPENAI_API_KEY="" \
  -v /path/to/instructions.md:/app/instructions.md \
  -v /path/to/access.json:/app/access.json \
  agentic-discord-bot

# Claude provider (servers_config.json must set "provider": "claude")
docker run -d \
  --name discordbot \
  -e DISCORD_BOT_TOKEN="" \
  -e ANTHROPIC_API_KEY="" \
  -v /path/to/instructions.md:/app/instructions.md \
  -v /path/to/servers_config.json:/app/servers_config.json \
  -v /path/to/access.json:/app/access.json \
  agentic-discord-bot
```

To use MCP servers with OpenAI, also mount the config:

```bash
docker run -d \
  --name discordbot \
  -e DISCORD_BOT_TOKEN="" \
  -e OPENAI_API_KEY="" \
  -v /path/to/instructions.md:/app/instructions.md \
  -v /path/to/servers_config.json:/app/servers_config.json \
  -v /path/to/access.json:/app/access.json \
  agentic-discord-bot
```
