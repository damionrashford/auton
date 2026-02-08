# FastMCP AI Agent

A multi-agent orchestrator-worker system built on the [Model Context Protocol](https://modelcontextprotocol.io/) (MCP). An orchestrator decomposes user requests and delegates to specialist agents -- each with filtered tool access, focused prompts, and isolated conversation state. Talk to it from Slack.

Built with [FastMCP 3.0](https://gofastmcp.com/), Python 3.11+, fully async.

---

## What It Does

You send a message in Slack. The orchestrator figures out what needs to happen, delegates to the right specialists, and replies with a synthesized answer.

```
"Research the latest DeFi yields on Base, then send a summary to #defi-research"

Orchestrator
  -> Research Agent: web_search + social_search + content_operations
  -> Blockchain Agent: cb_aave_portfolio (check current positions)
  -> Communication Agent: slack_send_message to #defi-research
  -> Synthesize all results into one reply
```

Each specialist only sees its own tools. The Research Agent cannot send Slack messages. The Blockchain Agent cannot browse the web. The orchestrator cannot execute anything directly -- it can only delegate.

---

## Agent Roles

| Role | Tools | Capabilities |
|------|-------|-------------|
| **Orchestrator** | `delegate_to_*`, `memory_recall` | Task decomposition, delegation, result synthesis |
| **Research** | 10 RivalSearchMCP tools + Playwright (read-only) + memory | Web search, social search, news, GitHub, academic papers, content extraction, document analysis (OCR), site mapping |
| **Browser** | All Playwright tools + memory | Click, type, fill forms, scroll, screenshots, PDF generation |
| **Communication** | Slack tools + Gmail + Google Chat + memory | Send/read messages, emails, threads, channels, file uploads |
| **Workspace** | All Google Workspace tools + memory | Calendar, Drive, Docs, Sheets, Slides, Forms, Tasks, Contacts, Apps Script |
| **Blockchain** | 19 Coinbase AgentKit tools + memory | Wallets, transfers, token swaps, DeFi (Aave V3), NFTs, Superfluid streaming, .base.eth domains, Pyth oracles |

---

## Architecture

```
Slack (Socket Mode)
  |
  v
SlackBoltUI
  |-- rate limiting (5/min per user)
  |-- bot self-check (prevent loops)
  |
  v
OrchestratorAgent.run()
  |
  |-- decompose_task()    LLM picks specialists
  |-- execute_tasks()     parallel or sequential
  |     |
  |     |-- run_agent(agent_config=RESEARCH, ...)
  |     |-- run_agent(agent_config=BROWSER, ...)
  |     |-- run_agent(agent_config=COMMUNICATION, ...)
  |     |-- run_agent(agent_config=WORKSPACE, ...)
  |     |-- run_agent(agent_config=BLOCKCHAIN, ...)
  |     |
  |     each agent:
  |       - filtered tool schemas (registry)
  |       - role-specific system prompt
  |       - isolated conversation
  |       - 3-path confirmation for writes
  |
  |-- synthesize_results()  LLM combines outputs
  |
  v
Reply in Slack thread
```

### External MCP Servers

| Server | Connection | Tools |
|--------|-----------|-------|
| [RivalSearchMCP](https://rivalsearchmcp.fastmcp.app) | Remote HTTP | 10 search/analysis tools (no prefix) |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | Local subprocess | Browser automation (`pw_` prefix) |
| [Google Workspace MCP](https://github.com/taylorwilsdon/google_workspace_mcp) | Local HTTP | Calendar, Drive, Docs, Sheets, etc. (`gw_` prefix) |

### Internal Tool Sources

| Source | Registration | Tools |
|--------|-------------|-------|
| Slack Bolt | `slack-sdk` + `slack-bolt` | 8 tools (`slack_*`) |
| Cron Scheduler | APScheduler | 3 tools (`cron_*`) |
| Memory | pgvector embeddings | 3 tools (`memory_*`) |
| Delegation | Orchestrator-only | 5 tools (`delegate_to_*`) |
| Blockchain | Coinbase AgentKit | 19 tools (`cb_*`) |

---

## Safety

Every write operation requires explicit user approval. Three confirmation paths:

1. **MCP Context** -- `ctx.elicit()` when accessed via MCP protocol directly
2. **Slack Callback** -- bot posts a confirmation message in the thread, polls for "yes"/"no" reply (60s timeout, defaults to deny)
3. **Block** -- if no confirmation mechanism is available, write operations are blocked entirely

All blockchain operations (`cb_*`) require confirmation unconditionally.

Google Workspace write operations are pattern-matched against dangerous keywords (create, delete, modify, send, share, transfer, batch, etc.).

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- Redis (required for caching and session state)
- Neon Postgres (optional, for persistent storage)

### Install

```bash
git clone https://github.com/your-username/fast-mcp-agent.git
cd fast-mcp-agent
uv sync
cp .env.example .env
# Edit .env with your API keys
```

### Configure

Minimum required in `.env`:

```bash
OPENROUTER_API_KEY=sk-or-...          # LLM access
RIVAL_SEARCH_URL=https://RivalSearchMCP.fastmcp.app/mcp
SLACK_BOT_TOKEN=xoxb-...              # Slack bot token
SLACK_APP_TOKEN=xapp-...              # Slack Socket Mode token
SLACK_ENABLED=true
```

Optional services:

```bash
NEON_DATABASE_URL=postgresql://...     # Persistent conversations + memory
GOOGLE_WORKSPACE_MCP_URL=http://localhost:8001/mcp
BLOCKCHAIN_ENABLED=true
CDP_API_KEY_ID=...                     # Coinbase AgentKit
CDP_API_KEY_SECRET=...
CDP_WALLET_SECRET=...
```

### Run

```bash
uv run uvicorn fast_mcp_agent.app:app --host 0.0.0.0 --port 8000
```

The server starts the MCP endpoint at `/mcp`, connects to all configured MCP servers, registers internal tools, initializes the orchestrator, and starts the Slack Bolt listener. Then @mention the bot or DM it in Slack.

### Slack Setup

1. Create app at [api.slack.com/apps](https://api.slack.com/apps)
2. Enable Socket Mode, get `SLACK_APP_TOKEN` (xapp-...)
3. Add Bot Token Scopes: `app_mentions:read`, `chat:write`, `channels:history`, `channels:read`, `im:history`, `im:read`, `im:write`, `search:read`, `reactions:write`, `users:read`, `files:write`
4. Subscribe to events: `app_mention`, `message.im`
5. Install to workspace, get `SLACK_BOT_TOKEN` (xoxb-...)

---

## Configuration

All configuration via environment variables. See [.env.example](.env.example) for the full template.

| Group | Key Fields |
|-------|-----------|
| LLM | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default: `x-ai/grok-4.1-fast`), fallbacks, sampling, reasoning |
| Playwright | `PLAYWRIGHT_MCP_PORT`, headless, browser, stealth, viewport |
| Google Workspace | `GOOGLE_WORKSPACE_MCP_URL`, `GOOGLE_WORKSPACE_MCP_ENABLED` |
| Slack | `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_ENABLED` |
| Blockchain | `BLOCKCHAIN_ENABLED`, `BLOCKCHAIN_NETWORK`, `CDP_API_KEY_ID`, `CDP_API_KEY_SECRET` |
| Storage | `NEON_DATABASE_URL`, `REDIS_HOST` |
| Agent | `MAX_ITERATIONS` (25), `TOOL_TIMEOUT` (120s), cost guardrails |
| Multi-Agent | Per-role iteration limits, delegation depth, orchestrator timeout |

---

## Database Schema

Neon Postgres with pgvector. Applied automatically on startup.

| Table | Purpose |
|-------|---------|
| `conversations` | Metadata + `parent_conversation_id` + `agent_role` for delegation chains |
| `messages` | Individual messages within conversations |
| `tool_call_logs` | Tool call audit log (name, args, result, duration, success) |
| `usage_logs` | Token usage and cost per conversation |
| `agent_memory` | pgvector embeddings (1536-dim) with semantic search |
| `agent_decision_logs` | Agent decisions for observability |
| `agent_delegations` | Delegation tracking (parent/child, status, cost, tools) |
| `cron_jobs` | Scheduled task definitions |
| `cron_job_runs` | Cron execution history |

---

## Extending

Adding a new specialist agent follows a repeatable pattern. See [CLAUDE.md](CLAUDE.md) for the full 10-step recipe.

The short version:

1. Create `src/fast_mcp_agent/<name>/` with `client.py` and `tools.py`
2. Add `AgentRole.<NAME>` and registry config
3. Add system prompt and `delegate_to_<name>` tool
4. Add safety rules and config fields
5. Initialize in server lifespan

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| MCP Framework | [FastMCP 3.0](https://gofastmcp.com/) |
| HTTP Framework | [FastAPI](https://fastapi.tiangolo.com/) |
| LLM Provider | [OpenRouter](https://openrouter.ai/) (default: Grok 4.1 Fast) |
| Search | [RivalSearchMCP](https://rivalsearchmcp.fastmcp.app) |
| Browser | [Playwright MCP](https://github.com/microsoft/playwright-mcp) |
| Google Workspace | [workspace-mcp](https://github.com/taylorwilsdon/google_workspace_mcp) |
| Blockchain | [Coinbase AgentKit](https://github.com/coinbase/agentkit) |
| Chat UI | [Slack Bolt](https://api.slack.com/bolt) (Socket Mode) |
| Database | [Neon Postgres](https://neon.tech/) + pgvector |
| Cache | Redis |
| Scheduling | APScheduler |
| Token Counting | tiktoken |
| Observability | OpenTelemetry (optional) |

---

## Project Structure

```
src/fast_mcp_agent/
  app.py                    FastAPI + FastMCP ASGI composition
  config.py                 Pydantic Settings (120+ fields)
  models.py                 Shared data models

  agents/
    roles.py                AgentRole enum, AgentConfig, DelegationTask
    registry.py             Tool filtering per role (glob patterns)
    orchestrator.py         Decompose, delegate, synthesize
    prompts.py              Role-specific system prompts
    tools.py                Delegation tools (delegate_to_*)

  core/
    agent.py                Agent loop (run_agent with AgentConfig)
    llm.py                  OpenRouter client
    safety.py               3-tier confirmation system
    tokenizer.py            Token counting
    prompts.py              Legacy system prompt (unused)

  bridge/
    manager.py              MCPBridge (tool routing + prompt access)
    playwright.py           Playwright subprocess manager

  mcp/
    server.py               FastMCP server + lifespan + chat tool
    dependencies.py         DI singletons
    middleware.py            Error, Timing, Logging, Caching

  storage/
    postgres.py             asyncpg pool + migrations
    conversations.py        NeonConversationStore + delegation tracking
    memory.py               pgvector semantic memory
    schema.sql              Full database schema

  slack/
    bolt_app.py             Slack Bolt UI (Socket Mode)
    client.py               Outbound Slack API wrapper
    tools.py                8 Slack tool schemas + handler

  blockchain/
    client.py               Coinbase AgentKit wrapper
    tools.py                19 blockchain tool schemas + handler

  scheduler/
    service.py              APScheduler cron service
    tools.py                Cron tool schemas

  telemetry/
    spans.py                OpenTelemetry helpers
```

---

## Development

```bash
uv sync --extra dev
uv run ruff check src/        # lint
uv run ruff format src/       # format
uv run mypy src/              # type check (strict)
uv run pytest                 # tests
```

---

## License

MIT
