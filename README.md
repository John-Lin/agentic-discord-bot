# agentic-discord-bot

A Discord bot powered by [agent-core](https://github.com/John-Lin/agent-core) that interacts with [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) servers. Supports two interchangeable providers:

- **OpenAI** (default) — via [OpenAI Agents SDK](https://github.com/openai/openai-agents-python); works with OpenAI and Azure OpenAI v1.
- **Claude** — via [claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/).

Switch providers by setting `"provider"` in `agent_config.json`.

See also: [agentic-slackbot](https://github.com/John-Lin/agentic-slackbot) and [agentic-telegram-bot](https://github.com/John-Lin/agentic-telegram-bot) — similar bots for Slack and Telegram.

## Features

- Responds to @mentions in guild channels and threads
- DM support with allowlist access control
- Per-(channel, user) conversation history — each user maintains an independent context per channel/thread
- Configurable guild access with per-channel and per-user filters
- Connects to any MCP server via `agent_config.json`
- Optional local shell: `ShellTool` (OpenAI, via `provider.shell`) or `Bash`/`Write`/`Edit`/… (Claude, via `provider.allowedTools`). Read-only built-ins (`Read`, `Glob`, `Grep`) are always on for Claude.
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

# Optional: override SQLite path for session storage (in-memory by default)
# SESSION_DB_PATH="./sessions.db"

# Optional: override the path to the instructions file (default ./instructions.md)
# AGENT_INSTRUCTIONS_PATH="./instructions.md"

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

Create an `agent_config.json` to choose a provider and connect MCP servers. If the file is absent, the bot starts with the default OpenAI provider and no tools.

`provider` is a tagged union keyed by `type` (`"openai"` or `"anthropic"`). `mcp` uses an opencode-style schema keyed by server name, with `type: "local" | "remote"`.

### OpenAI provider (default)

```json
{
  "provider": {
    "type": "openai",
    "model": "gpt-5.4",
    "apiType": "responses",
    "historyTurns": 10
  },
  "mcp": {
    "my-server": {
      "type": "local",
      "command": ["uvx", "my-mcp-server"]
    }
  }
}
```

All `provider` fields are optional (`model` defaults to `gpt-5.4`, `apiType` to `"responses"`, `historyTurns` to `10`). Each MCP entry also accepts `timeout` (seconds, default `30.0`) and `enabled` (default `true`).

### Claude provider

```json
{
  "provider": {
    "type": "anthropic",
    "model": "claude-sonnet-4-6",
    "allowedTools": ["WebFetch"]
  },
  "mcp": {
    "my-stdio": {
      "type": "local",
      "command": ["python", "-m", "srv"],
      "environment": {"FOO": "bar"}
    },
    "my-http": {
      "type": "remote",
      "url": "https://example.com/mcp",
      "headers": {"Authorization": "Bearer x"}
    }
  }
}
```

Requires `ANTHROPIC_API_KEY`. Read-only built-ins (`Read`, `Glob`, `Grep`) are always on; `allowedTools` extends that set with any tool that can mutate files or run commands (`Bash`, `Write`, `Edit`, `WebFetch`, …). Tool names are case-sensitive and validated by the SDK — an unrecognized name is silently dropped. Billing/rate-limit/`error_max_turns` errors are surfaced to the channel as a readable message via `AgentError`.

### Remote (HTTP) MCP servers

```json
{
  "mcp": {
    "my-server": {
      "type": "remote",
      "url": "https://mcp.example.com/mcp",
      "headers": {"Accept": "application/json, text/event-stream"}
    }
  }
}
```

### Local MCP servers (via `uv --directory`)

```json
{
  "mcp": {
    "my-server": {
      "type": "local",
      "command": ["uv", "--directory", "/path/to/my-server", "run", "my-entrypoint"]
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

OpenAI history length is controlled by `provider.historyTurns` in `agent_config.json` (default `10`). Claude history is managed on disk by `claude-agent-sdk` and resumed across restarts via a `chat_id -> session_id` mapping in SQLite (`SESSION_DB_PATH`).

## Local Shell (Optional)

Local shell tools are **disabled by default** and are configured in `agent_config.json` per provider.

### OpenAI — `provider.shell`

```json
{
  "provider": {
    "type": "openai",
    "shell": {
      "enabled": true,
      "skillsDir": "./skills"
    }
  }
}
```

`provider.shell.enabled` must be a bool (strings are rejected). `provider.shell.skillsDir` is optional and mounts a skills directory alongside the `ShellTool`.

### Claude — `provider.allowedTools`

Read-only built-ins (`Read`, `Glob`, `Grep`) are always on. Add mutating or exec-capable tools explicitly:

```json
{
  "provider": {
    "type": "anthropic",
    "allowedTools": ["Bash", "Write", "Edit", "WebFetch"]
  }
}
```

### Shell Skills (OpenAI only)

Each immediate subdirectory of `skillsDir` containing a `SKILL.md` file is registered as a skill and exposed to the agent as a hint (skills are advisory metadata — they do **not** sandbox command execution). If the directory is missing or contains no valid skills, the bot falls back to a bare shell and logs a warning.

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

# Claude provider (agent_config.json must set "provider": {"type": "anthropic"})
docker run -d \
  --name discordbot \
  -e DISCORD_BOT_TOKEN="" \
  -e ANTHROPIC_API_KEY="" \
  -v /path/to/instructions.md:/app/instructions.md \
  -v /path/to/agent_config.json:/app/agent_config.json \
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
  -v /path/to/agent_config.json:/app/agent_config.json \
  -v /path/to/access.json:/app/access.json \
  agentic-discord-bot
```
