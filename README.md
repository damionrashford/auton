# auton

An autonomous AI agent you run locally. Give it a task and it works through it — running shell commands, reading and writing files, making HTTP requests, remembering things across sessions, and more. Connect it to Slack, Telegram, or WhatsApp to talk to it from anywhere.

No npm packages required. Just Node.js and an API key.

---

## Requirements

- **Node.js 18 or later** (for native `fetch` support)
- An **OpenAI API key** — or any OpenAI-compatible API (Anthropic via proxy, Ollama, Groq, etc.)

Check your Node version:

```bash
node --version
```

---

## Setup

Open `config.json` and fill in your API key at minimum:

```json
{
  "llm": {
    "apiKey": "sk-...",
    "apiUrl": "https://api.openai.com/v1",
    "model": "gpt-4o"
  }
}
```

Everything else in the file has working defaults and can be left alone until you need it.

---

## Running the agent

### One-shot: give it a single task

```bash
node agent.js "summarize the files in my Documents folder"
```

The agent will think through the task, use whatever tools it needs, and stop when it's done. Output prints to the terminal as it works.

### Daemon: let it run continuously

```bash
node agent.js
```

With no arguments, the agent runs as a persistent background process. Every 30 seconds it checks for scheduled tasks and active goals, then acts on them. Use this when you want it to keep working on something over time or handle scheduled jobs.

---

## Talking to it through messaging apps

`comms.js` connects the agent to Slack, Telegram, and/or WhatsApp. Configure whichever channels you want in `config.json`, then run:

```bash
node comms.js
```

It will start all configured channels at once. If a channel's credentials aren't in the config, it's simply skipped.

---

### Slack

Requires **Socket Mode**, which means no public URL needed — the bot connects outbound.

**What you need:**
- A Slack app with Socket Mode enabled
- Bot Token (starts with `xoxb-`)
- App-Level Token with `connections:write` scope (starts with `xapp-`)
- Bot scopes: `chat:write`, `app_mentions:read`, `im:history`, `reactions:write`, `reactions:read`

**config.json:**
```json
"slack": {
  "botToken": "xoxb-YOUR-BOT-TOKEN",
  "appToken": "xapp-YOUR-APP-TOKEN"
}
```

**How to use it in Slack:**
- `/ask your question here` — slash command in any channel
- `@YourBot message` — mention the bot in a channel
- Send it a direct message

---

### Telegram

Requires a bot created via [@BotFather](https://t.me/BotFather). No public URL needed — it polls for updates.

**What you need:**
- A bot token from BotFather

**config.json:**
```json
"telegram": {
  "botToken": "YOUR_TELEGRAM_BOT_TOKEN"
}
```

**How to use it in Telegram:**
- Send any message directly to the bot
- In a group, mention the bot: `@YourBot your message`
- `/start` — confirms the bot is online
- `/help` — lists available commands
- `/clear` — clears the agent's memory for your user

The bot also handles photos, documents, voice messages, locations, and stickers — it acknowledges receiving them and can respond accordingly.

---

### WhatsApp

Uses the Meta Cloud API and requires a **publicly accessible URL** for the webhook. If you're running locally, a tool like [ngrok](https://ngrok.com) can expose it.

**What you need:**
- A Meta developer account and app with WhatsApp enabled
- Access token, phone number ID, and a verify token (any string you choose)

**config.json:**
```json
"whatsapp": {
  "accessToken": "YOUR_META_ACCESS_TOKEN",
  "phoneNumberId": "YOUR_PHONE_NUMBER_ID",
  "verifyToken": "any-secret-string",
  "port": 3000
}
```

The webhook server starts on port 3000 by default. Set your webhook URL in the Meta dashboard to `https://your-domain.com/` with the same verify token.

---

## What the agent can do

These are the built-in tools the agent can call on its own when working through a task:

| Tool | What it does |
|---|---|
| `shell` | Runs a shell command and returns the output |
| `read_file` | Reads a file from disk |
| `write_file` | Writes or creates a file (creates directories as needed) |
| `http` | Makes an HTTP request (GET, POST, etc.) |
| `store` / `recall` | Saves and retrieves values in persistent memory |
| `goal` | Sets, lists, and marks goals complete |
| `schedule` | Sets up recurring tasks |
| `skill` | Loads and uses agent skills |
| `mcp_connect` / `mcp_disconnect` | Connects to MCP servers for additional tools |

---

## Memory

The agent has persistent memory that survives restarts. It can store arbitrary key/value pairs and recall them later. This is how it remembers things you've told it across separate sessions.

Memory is stored in `state.json` alongside your other files. You can inspect or edit it directly if needed.

---

## Goals

Goals are tasks you want the agent to work toward over time. In daemon mode, the agent picks up its highest-priority active goal each cycle and makes progress on it.

You can set a goal by asking the agent to do so:

```bash
node agent.js "set a goal to monitor my Downloads folder and move PDF files to ~/Documents/PDFs every hour"
```

Goals have three priority levels: `high`, `medium`, and `low`. The agent works on high-priority goals first.

---

## Scheduled tasks

In daemon mode, the agent can run tasks on a recurring schedule. Intervals are written as `30s`, `5m`, `2h`, `1d`, etc.

Example — ask the agent to schedule something:

```bash
node agent.js "schedule a task every 1h to check if any process is using more than 80% CPU and log it to ~/cpu-log.txt"
```

Schedules persist across restarts via `state.json`.

---

## Agent skills

Skills are packaged instructions that extend what the agent knows how to do — things like specific workflows, domain knowledge, or step-by-step procedures.

Skills are discovered from two locations:
- `./skills/` — project-level skills (this directory)
- `~/.agents/skills/` — user-level skills shared across projects

Each skill is a folder with a `SKILL.md` file inside. The agent can list available skills, load one when relevant, and use any scripts or resources bundled with it.

To install a skill from a git repository:
```bash
node agent.js "install skill from https://github.com/example/some-skill"
```

---

## MCP servers

MCP (Model Context Protocol) lets you connect the agent to external tools and services — databases, APIs, local applications — using a standard protocol.

To connect an MCP server, tell the agent about it and it will persist the connection for future sessions:

```bash
# stdio-based server
node agent.js "connect mcp server named 'mydb' using command 'npx my-db-mcp-server'"

# HTTP/SSE-based server
node agent.js "connect mcp server named 'myapi' at url http://localhost:8080/mcp"
```

Once connected, the server's tools appear automatically alongside the built-in tools. Connections are saved in `state.json` and restored on next startup.

---

## Configuration reference

All settings live in `config.json`. Environment variables can be used as fallbacks for the LLM settings (`API_KEY`, `API_URL`, `MODEL`).

| Setting | Default | Description |
|---|---|---|
| `llm.apiKey` | — | Your API key (required) |
| `llm.apiUrl` | `https://api.openai.com/v1` | API base URL |
| `llm.model` | `gpt-4o` | Model to use |
| `agent.maxTurns` | `25` | Max tool calls per task before stopping |
| `agent.daemonInterval` | `30` | Seconds between daemon cycles |
| `slack.botToken` | — | Slack bot token |
| `slack.appToken` | — | Slack app-level token (Socket Mode) |
| `telegram.botToken` | — | Telegram bot token |
| `whatsapp.accessToken` | — | Meta access token |
| `whatsapp.phoneNumberId` | — | WhatsApp phone number ID |
| `whatsapp.verifyToken` | — | Webhook verify token (you choose this) |
| `whatsapp.port` | `3000` | Port for the WhatsApp webhook server |

---

## Using a different AI provider

The agent works with any OpenAI-compatible API. Change `apiUrl` and `model` to point to another provider:

**Groq:**
```json
"llm": {
  "apiKey": "gsk_...",
  "apiUrl": "https://api.groq.com/openai/v1",
  "model": "llama-3.3-70b-versatile"
}
```

**Ollama (local):**
```json
"llm": {
  "apiKey": "ollama",
  "apiUrl": "http://localhost:11434/v1",
  "model": "llama3.2"
}
```

---

## State file

Everything the agent remembers — memory, goals, schedules, MCP connections — is stored in `state.json` in this directory. It's created automatically on first run.

If you want to reset the agent completely, delete `state.json`. If you want to inspect or manually edit its memory or goals, it's plain JSON.
