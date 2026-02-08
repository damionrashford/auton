<div align="center">

# Auton

**Autonomous multi-agent orchestrator powered by Model Context Protocol**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastMCP 3.0](https://img.shields.io/badge/FastMCP-3.0-00D4AA)](https://gofastmcp.com/)
[![xAI Grok](https://img.shields.io/badge/xAI-Grok%204.1-000000)](https://x.ai)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An orchestrator decomposes user requests and delegates to specialist agents — each with filtered tool access, focused prompts, and isolated conversation state. Talk to it from Slack.

</div>

---

## Overview

```
"Research the latest DeFi yields on Base, then send a summary to #defi-research"

Orchestrator
  -> Research Agent    web_search + social_search + content_operations
  -> Blockchain Agent  cb_aave_portfolio (check current positions)
  -> Communication     slack_send_message to #defi-research
  -> Synthesize all results into one reply
```

Each specialist only sees its own tools. The Research Agent cannot send Slack messages. The Blockchain Agent cannot browse the web. The orchestrator cannot execute anything directly — it can only delegate.

---

## Agents

| Role | Tools | What It Does |
|:-----|:------|:-------------|
| **Orchestrator** | `delegate_to_*`, `memory_recall` | Task decomposition, delegation, result synthesis |
| **Research** | 10 search tools + Playwright read-only | Web, social, news, GitHub, academic papers, OCR, site mapping |
| **Browser** | Full Playwright suite | Click, type, fill forms, scroll, screenshots, PDF generation |
| **Communication** | Slack + Gmail + Google Chat | Messages, emails, threads, channels, file uploads |
| **Workspace** | Google Workspace | Calendar, Drive, Docs, Sheets, Slides, Forms, Tasks |
| **Blockchain** | 19 Coinbase AgentKit tools | Wallets, swaps, DeFi (Aave V3), NFTs, streaming, .base.eth |

---

## Architecture

```
Slack (Socket Mode)
  |
  v
SlackBoltUI ── rate limiting (5/min) + bot self-check
  |
  v
OrchestratorAgent.run()
  |
  |-- decompose_task()        LLM selects specialists
  |-- execute_tasks()         parallel or sequential
  |     |
  |     |-- Research Agent    (RivalSearchMCP + Playwright read-only)
  |     |-- Browser Agent     (Playwright full access)
  |     |-- Communication     (Slack + Gmail + Google Chat)
  |     |-- Workspace         (Google Calendar, Drive, Docs, Sheets)
  |     |-- Blockchain        (Coinbase AgentKit)
  |     |
  |     each agent: filtered tools, role prompt, isolated state
  |
  |-- synthesize_results()    LLM combines outputs
  |
  v
Reply in Slack thread
```

### External MCP Servers

| Server | Connection | Tools |
|:-------|:-----------|:------|
| [RivalSearchMCP](https://rivalsearchmcp.fastmcp.app) | Remote HTTP | 10 search/analysis tools |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | Local subprocess | Browser automation (`pw_*`) |
| [Google Workspace MCP](https://github.com/taylorwilsdon/google_workspace_mcp) | Local HTTP | Calendar, Drive, Docs, Sheets (`gw_*`) |

### Internal Tools

| Source | Tools |
|:-------|:------|
| Slack Bolt | 8 tools (`slack_*`) |
| Coinbase AgentKit | 19 tools (`cb_*`) |
| Cron Scheduler | 3 tools (`cron_*`) |
| Memory (pgvector) | 3 tools (`memory_*`) |
| Delegation | 5 tools (`delegate_to_*`) |

---

## Safety

Every write operation requires explicit user approval. Three confirmation paths:

| Path | Mechanism | Timeout |
|:-----|:----------|:--------|
| **MCP** | `ctx.elicit()` structured dialog | — |
| **Slack** | Thread-based yes/no poll | 60s (defaults to deny) |
| **Block** | No mechanism available | Blocked entirely |

- All `cb_*` blockchain tools require confirmation **unconditionally**
- `gw_*` tools matched against dangerous keyword patterns (create, delete, send, modify, transfer, etc.)
- Explicit `WRITE_TOOLS` frozenset for Slack, Cron, and Memory operations

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- Redis (caching and session state)
- Neon Postgres (optional — graceful fallback to in-memory)

### Install

```bash
git clone https://github.com/damionrashford/auton.git
cd auton
uv sync
cp .env.example .env
```

### Configure

Minimum required in `.env`:

```bash
XAI_API_KEY=xai-...                   # xAI API key
RIVAL_SEARCH_URL=https://RivalSearchMCP.fastmcp.app/mcp
SLACK_BOT_TOKEN=xoxb-...              # Slack bot token
SLACK_APP_TOKEN=xapp-...              # Socket Mode token
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
uv run uvicorn auton.app:app --host 0.0.0.0 --port 8000
```

The server starts the MCP endpoint at `/mcp`, connects to configured MCP servers, registers internal tools, initializes the orchestrator, and starts the Slack listener. Then `@mention` the bot or DM it.

### Slack Setup

1. Create app at [api.slack.com/apps](https://api.slack.com/apps)
2. Enable **Socket Mode** — get `SLACK_APP_TOKEN` (`xapp-...`)
3. Add Bot Token Scopes: `app_mentions:read`, `chat:write`, `channels:history`, `channels:read`, `im:history`, `im:read`, `im:write`, `search:read`, `reactions:write`, `users:read`, `files:write`
4. Subscribe to events: `app_mention`, `message.im`
5. Install to workspace — get `SLACK_BOT_TOKEN` (`xoxb-...`)

---

## Configuration

All configuration via environment variables. See [`.env.example`](.env.example) for the full template (87 fields).

| Group | Key Fields |
|:------|:-----------|
| **xAI LLM** | `XAI_API_KEY`, `XAI_MODEL` (default: `grok-4.1-fast`, 2M context) |
| **Playwright** | `PLAYWRIGHT_MCP_PORT`, headless, browser, stealth, viewport |
| **Google Workspace** | `GOOGLE_WORKSPACE_MCP_URL`, `GOOGLE_WORKSPACE_MCP_ENABLED` |
| **Slack** | `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_ENABLED` |
| **Blockchain** | `BLOCKCHAIN_ENABLED`, `BLOCKCHAIN_NETWORK`, CDP credentials |
| **Storage** | `NEON_DATABASE_URL`, `REDIS_HOST` |
| **Agent** | `MAX_ITERATIONS` (25), `TOOL_TIMEOUT` (120s), cost guardrails |
| **Multi-Agent** | Per-role iteration limits, delegation depth, orchestrator timeout |

---

## Database

Neon Postgres with pgvector. Schema applied automatically on startup.

| Table | Purpose |
|:------|:--------|
| `conversations` | Metadata + `parent_conversation_id` + `agent_role` for delegation chains |
| `messages` | Individual messages within conversations |
| `tool_call_logs` | Audit log — name, args, result, duration, success |
| `usage_logs` | Token usage and cost per conversation |
| `agent_memory` | pgvector embeddings (1536-dim) with HNSW cosine search |
| `agent_decision_logs` | Agent decisions for observability |
| `agent_delegations` | Delegation tracking — parent/child, status, cost, tools used |
| `cron_jobs` | Scheduled task definitions |
| `cron_job_runs` | Cron execution history |

---

## Project Structure

```
src/auton/
  app.py                    FastAPI + FastMCP ASGI composition
  config.py                 Pydantic Settings (87 fields)
  models.py                 Shared data models

  agents/
    roles.py                AgentRole enum, AgentConfig, DelegationTask
    registry.py             Tool filtering per role (glob patterns)
    orchestrator.py         Decompose -> delegate -> synthesize
    prompts.py              Role-specific system prompts
    tools.py                Delegation tools (delegate_to_*)

  core/
    agent.py                Agentic loop (run_agent)
    llm.py                  xAI SDK client (gRPC + REST embeddings)
    safety.py               3-tier confirmation system
    tokenizer.py            Token counting via tiktoken

  bridge/
    manager.py              MCPBridge — tool routing + prompt access
    playwright.py           Playwright subprocess manager

  mcp/
    server.py               FastMCP server, lifespan, chat tool
    dependencies.py         DI singletons
    middleware.py            Error, Timing, Logging, Caching

  storage/
    postgres.py             asyncpg pool + migrations
    conversations.py        NeonConversationStore + LRU cache
    memory.py               pgvector semantic memory
    memory_tools.py         memory_store, memory_recall, memory_forget
    schema.sql              Database schema (9 tables)

  slack/
    bolt_app.py             Slack Bolt UI (Socket Mode)
    client.py               Outbound Slack API wrapper
    tools.py                8 tool schemas + handler

  blockchain/
    client.py               Coinbase AgentKit wrapper
    tools.py                19 tool schemas + handler

  scheduler/
    service.py              APScheduler cron service
    tools.py                Cron tool schemas

  telemetry/
    spans.py                OpenTelemetry helpers
```

---

## Tech Stack

| | Technology |
|:--|:-----------|
| **Protocol** | [Model Context Protocol](https://modelcontextprotocol.io/) via [FastMCP 3.0](https://gofastmcp.com/) |
| **HTTP** | [FastAPI](https://fastapi.tiangolo.com/) |
| **LLM** | [xAI Grok 4.1 Fast](https://x.ai) (2M context) |
| **Search** | [RivalSearchMCP](https://rivalsearchmcp.fastmcp.app) |
| **Browser** | [Playwright MCP](https://github.com/microsoft/playwright-mcp) |
| **Workspace** | [Google Workspace MCP](https://github.com/taylorwilsdon/google_workspace_mcp) |
| **Blockchain** | [Coinbase AgentKit](https://github.com/coinbase/agentkit) |
| **Chat** | [Slack Bolt](https://api.slack.com/bolt) (Socket Mode) |
| **Database** | [Neon Postgres](https://neon.tech/) + pgvector |
| **Cache** | Redis |
| **Scheduling** | APScheduler |
| **Tokens** | tiktoken |
| **Observability** | OpenTelemetry (optional) |

---

## Extending

Adding a new specialist agent follows a 10-step recipe. See [AGENTS.md](AGENTS.md) for the full guide.

```
1. Create src/auton/<name>/ with client.py + tools.py
2. Add AgentRole + registry config
3. Add system prompt + delegation tool
4. Add safety rules + config fields
5. Initialize in server lifespan
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
