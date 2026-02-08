# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastMCP AI Agent — a multi-agent orchestrator-worker system built with FastMCP (FastAPI + Model Context Protocol). An orchestrator decomposes user requests and delegates to specialist agents (Research, Browser, Communication, Workspace, Blockchain), each with filtered tool access and focused prompts. Slack is the primary UI via Bolt Socket Mode. Python 3.11+, fully async, default LLM: Grok 4.1 Fast via xAI SDK (gRPC).

## Commands

```bash
# Install dependencies (uses uv package manager)
uv sync

# Install with dev tools
uv sync --extra dev

# Run dev server with hot reload
uv run uvicorn fast_mcp_agent.app:app --host 0.0.0.0 --port 8000 --reload

# Run as standalone FastMCP server
uv run fastmcp run

# Type checking (strict mode)
uv run mypy src/

# Lint
uv run ruff check src/

# Format
uv run ruff format src/

# Tests (pytest + pytest-asyncio)
uv run pytest
uv run pytest tests/test_agent.py -k "test_name"
```

Redis must be running locally. Neon Postgres, Slack, Google Workspace MCP, and Coinbase AgentKit are optional (graceful degradation).

## Architecture

### Multi-Agent System

The system uses an **Orchestrator-Worker** pattern. Every request flows through the orchestrator, which decomposes tasks and delegates to specialists:

```
User (Slack @mention or DM)
  → SlackBoltUI (Socket Mode)
    → OrchestratorAgent.run()
      → decompose_task() — LLM picks specialist agents
      → execute_tasks() — parallel/sequential delegation
        → Research Agent (RivalSearchMCP: 10 tools + Playwright read-only)
        → Browser Agent (Playwright: click, type, fill, scroll)
        → Communication Agent (Slack + Gmail + Google Chat)
        → Workspace Agent (Google Workspace: Calendar, Drive, Docs, Sheets, etc.)
        → Blockchain Agent (Coinbase AgentKit: wallets, DeFi, swaps, NFTs)
      → synthesize_results() — LLM combines specialist outputs
    → Reply in Slack thread
```

### Agent Roles (`agents/roles.py`)

`AgentRole` enum: ORCHESTRATOR, RESEARCH, BROWSER, COMMUNICATION, WORKSPACE, BLOCKCHAIN. Each role has an `AgentConfig` with `allowed_tool_patterns`, `denied_tool_patterns`, `max_iterations_override`, and an optional `confirmation_callback` for Slack-native write-op approval.

### Agent Registry (`agents/registry.py`)

Maps each role to its tool access patterns using glob matching (`*` wildcards). Denied patterns override allowed. Tool prefix conventions:
- RivalSearchMCP tools: no prefix (`web_search`, `social_search`, etc.)
- Playwright tools: always `pw_` prefix
- Google Workspace tools: always `gw_` prefix
- Slack tools: `slack_` prefix (internal)
- Blockchain tools: `cb_` prefix (internal)
- Delegation tools: `delegate_to_*` (orchestrator-only)

### Orchestrator (`agents/orchestrator.py`)

`OrchestratorAgent` has three phases:
1. **Decompose** — LLM analyzes request, outputs JSON array of `{target_role, instruction, context, parallel}`
2. **Execute** — spawns specialist agents via `run_agent(agent_config=...)`, parallel with `asyncio.gather` for independent tasks
3. **Synthesize** — LLM combines specialist results into unified response

Falls back to Research Agent directly for simple requests (empty decomposition).

Fetches RivalSearchMCP prompts (`comprehensive_research`, `multi_source_search`, `deep_content_analysis`, `academic_literature_review`) via `bridge.get_prompt()` and injects them as guided workflows for research tasks.

### Entry Point (`app.py`)

FastAPI app mounts the FastMCP server at `/mcp`. Uses `combine_lifespans` to merge FastAPI and MCP server lifecycles. Endpoints: `POST /mcp` (MCP protocol), `GET /health`, `GET /api/status`.

### Agent Loop (`core/agent.py`)

`run_agent()` requires an `AgentConfig` parameter (no default). Each iteration:
1. Recalls relevant memories from pgvector
2. Generates a multi-step plan for complex requests (>100 chars)
3. Calls xAI LLM with **filtered** tool schemas (based on agent role)
4. Executes tool calls (parallel for independent, sequential for browser/duplicates)
5. Checks cost/token guardrails and context window limits
6. Self-corrects: single retry, stuck-loop detection, strategy injection after 3+ failures
7. Compacts conversation via LLM summarization when approaching context limit

Confirmation gate has 3 paths: MCP `ctx.elicit()`, Slack callback (thread-based yes/no polling), or block if no mechanism available.

### MCP Bridge (`bridge/manager.py`)

`MCPBridge` connects to external MCP servers and manages internal tools:
- RivalSearchMCP (10 tools: `web_search`, `social_search`, `news_aggregation`, `github_search`, `scientific_research`, `content_operations`, `map_website`, `document_analysis`, `research_topic`, `research_agent`)
- Playwright MCP (always `pw_` prefixed)
- Google Workspace MCP — `taylorwilsdon/google_workspace_mcp` (always `gw_` prefixed)
- Internal tools: Slack (`slack_*`), Cron (`cron_*`), Memory (`memory_*`), Delegation (`delegate_to_*`), Blockchain (`cb_*`)

Also exposes `list_prompts()` and `get_prompt()` for fetching RivalSearchMCP's guided research workflows.

### MCP Server (`mcp/server.py`)

Single exposed tool: `chat(message, conversation_id)` routes through `OrchestratorAgent.run()`.

Lifespan initialization order:
1. Redis health check
2. Neon Postgres pool + migrations
3. Playwright MCP subprocess
4. LLM client (OpenRouter)
5. Conversation store (Neon or in-memory fallback)
6. MCPBridge connections (RivalSearch + Playwright + Google Workspace)
7. Slack outbound service + tools
8. Cron scheduler + tools
9. Memory store + tools
10. Blockchain (AgentKit) + tools
11. Cron dependency injection
12. Multi-agent orchestrator + delegation tools
13. DI singletons
14. Slack Bolt UI (Socket Mode listener)

Middleware stack: ErrorHandling → Timing → Logging → ResponseCaching (Redis-backed, `chat` excluded).

### Slack UI (`slack/bolt_app.py`)

Slack is the primary interface. `SlackBoltUI` uses Bolt async app with Socket Mode:
- Handles `app_mention` + `message.im` events
- Each Slack thread = one `conversation_id` for multi-turn continuity
- Rate limiting: 5 messages/minute per user
- Bot self-check prevents infinite loops
- Orphaned "thinking" messages always cleaned up via `finally` block
- Slack-native confirmation for write ops: posts confirmation request, polls for "yes"/"no" reply, 60s timeout defaults to deny

### Storage Layer (`storage/`)

- `postgres.py` — asyncpg pool creation and schema migrations
- `conversations.py` — `NeonConversationStore` with LRU in-memory cache (200 conversations) + Postgres. Tracks messages, tool calls, usage, decisions, delegations
- `memory.py` — `MemoryStore` using pgvector (1536-dim embeddings, HNSW cosine index)
- `memory_tools.py` — 3 tools: `memory_store`, `memory_recall`, `memory_forget`
- `schema.sql` — Tables: `conversations` (with `parent_conversation_id`, `agent_role`), `messages`, `tool_call_logs`, `usage_logs`, `agent_memory`, `agent_decision_logs`, `cron_jobs`, `cron_job_runs`, `agent_delegations`

### Safety (`core/safety.py`)

3-tier confirmation system:
- Explicit `WRITE_TOOLS` frozenset for Slack/Cron/Memory ops
- Pattern matching for `gw_*` tools (keywords in `_GW_DANGEROUS_KEYWORDS`: create, delete, update, send, share, move, modify, batch, transfer, remove, import, manage, clear, draft, run, set_publish)
- ALL `cb_*` blockchain tools require confirmation unconditionally

### LLM Client (`core/llm.py`)

`LLMClient` wraps xAI SDK (gRPC). Default model: `grok-4.1-fast` (2M context window). Features: async chat completion (streaming and non-streaming), tool/function calling via `xai_sdk.chat.tool`, reasoning models with configurable effort (low/high), response normalization to OpenAI dict format, `embed()` via REST endpoint (`https://api.x.ai/v1/embeddings`) for semantic memory.

### Blockchain (`blockchain/`)

Wraps Coinbase AgentKit SDK as internal tools (`cb_*` prefix). Uses `CdpEvmWalletProvider` for Base/Ethereum. Action providers: wallet, ERC-20, ERC-721, CDP API, CDP EVM wallet, Pyth oracle, WETH. 19 tools covering wallets, transfers, swaps, DeFi (Aave), NFTs, streaming (Superfluid), identity (.base.eth), price feeds.

### Other Subsystems

- `scheduler/` — `CronSchedulerService` using APScheduler, re-enters agent loop with `AgentConfig(role=RESEARCH)`, posts results to Slack notification channel
- `slack/client.py` — `SlackService` outbound API wrapper (8 Slack tools)
- `slack/tools.py` — tool schemas + handler with actionable error messages for common Slack API errors
- `browser/stealth.js` — anti-bot detection script injected by Playwright
- `telemetry/` — OpenTelemetry span helpers for LLM and tool calls

## Configuration (`config.py`)

Pydantic Settings with 87 fields. Major groups:

- **xAI LLM**: model (`grok-4.1-fast`), temperature, max_tokens, reasoning_effort, embedding_model
- **Multi-Agent**: `multi_agent_*_max_iterations` per role, `multi_agent_max_delegation_depth`, orchestrator timeout
- **Playwright MCP**: port, headless, browser, proxy, stealth, capabilities
- **Google Workspace MCP**: URL, enabled flag
- **Slack**: bot token, app token, signing secret, enabled
- **Blockchain**: `blockchain_enabled`, `blockchain_network`, `cdp_api_key_id`, `cdp_api_key_secret`, `cdp_wallet_secret`
- **Neon Postgres**: connection URL
- **Redis**: host, port, DB numbers
- **Agent behavior**: `max_iterations`, `max_tool_result_length`, `tool_timeout`, context window, compaction, cost/token guardrails

Copy `.env.example` to `.env` for the full template.

## Dependency Injection

Module-level singletons set during MCP server lifespan. 8 factories in `mcp/dependencies.py` provide: `get_bridge()`, `get_llm()`, `get_store()`, `get_settings_dep()`, `get_db_pool()`, `get_memory_store()`, `get_orchestrator()`, `get_registry()`. Injection via `set_singletons()`. Uses FastMCP's `Depends()` pattern.

## Code Style

- Python 3.11+ with strict mypy (`pyproject.toml` → `[tool.mypy] strict = true`)
- ruff: target Python 3.11, line length 100, rules: E, F, I, N, W, UP
- All I/O must be async — never block with synchronous I/O
- Build backend: hatchling

## Adding a New Agent Capability

Follow this recipe (same pattern used for Slack, Blockchain):

1. Create `src/fast_mcp_agent/<name>/` package with `client.py` (SDK wrapper) and `tools.py` (tool schemas + handler)
2. Add `AgentRole.<NAME>` to `agents/roles.py`
3. Add registry config in `agents/registry.py` with `allowed_tool_patterns` and `denied_tool_patterns`
4. Add `<NAME>_AGENT_PROMPT` to `agents/prompts.py` and register in `get_system_prompt()`
5. Add `delegate_to_<name>` to `agents/tools.py` DELEGATION_TOOLS + _ROLE_MAP
6. Update orchestrator prompt and decomposition prompt in `agents/prompts.py` and `agents/orchestrator.py`
7. Add safety rules in `core/safety.py`
8. Add config fields in `config.py`
9. Initialize in `mcp/server.py` lifespan (conditional on config)
10. Add dependency to `pyproject.toml` and env vars to `.env.example`

## Development MCP Servers (`.mcp.json`)

The project configures documentation MCP servers that Claude Code can use to look up API references for key dependencies. Use these instead of web search when you need library-specific docs.

| Server | Source | Use For |
|---|---|---|
| `fastmcp-Docs` | [gofastmcp.com/mcp](https://gofastmcp.com/mcp) | FastMCP 3.0 API — server construction, `ctx.elicit()`, lifespan, middleware, `Depends()`, `Client` |
| `playwright-mcp-Docs` | [gitmcp.io/microsoft/playwright-mcp](https://gitmcp.io/microsoft/playwright-mcp) | Playwright MCP server — tool schemas, browser capabilities, config options |
| `neon-Docs` | [gitmcp.io/neondatabase/neon](https://gitmcp.io/neondatabase/neon) | Neon Postgres — connection pooling, branching, migrations, `asyncpg` usage |
| `opentelemetry-python-Docs` | [gitmcp.io/open-telemetry/opentelemetry-python](https://gitmcp.io/open-telemetry/opentelemetry-python) | OpenTelemetry Python SDK — spans, traces, exporters, instrumentation |
| `python-slack-sdk-Docs` | [gitmcp.io/slackapi/python-slack-sdk](https://gitmcp.io/slackapi/python-slack-sdk) | Slack SDK — `AsyncWebClient`, Bolt async handlers, Socket Mode |
| `redis-py-Docs` | [gitmcp.io/redis/redis-py](https://gitmcp.io/redis/redis-py) | Redis — async client, session state (`py-key-value-aio`), caching patterns |
| `fastapi-Docs` | [gitmcp.io/fastapi/fastapi](https://gitmcp.io/fastapi/fastapi) | FastAPI — lifespan events, middleware, mounting sub-apps, dependency injection |
| `pydantic-Docs` | [gitmcp.io/pydantic/pydantic](https://gitmcp.io/pydantic/pydantic) | Pydantic / pydantic-settings — `BaseSettings`, `Field()`, validators, `model_dump()` |
| `apscheduler-Docs` | [gitmcp.io/agronholm/apscheduler](https://gitmcp.io/agronholm/apscheduler) | APScheduler — cron triggers, job stores, `CronSchedulerService` patterns |
| `httpx-Docs` | [gitmcp.io/encode/httpx](https://gitmcp.io/encode/httpx) | httpx — async HTTP client used for OpenRouter API calls, streaming SSE |
| `tiktoken-Docs` | [gitmcp.io/openai/tiktoken](https://gitmcp.io/openai/tiktoken) | tiktoken — token counting for context window management |
| `structlog-Docs` | [gitmcp.io/hynek/structlog](https://gitmcp.io/hynek/structlog) | structlog — structured logging used project-wide |

Each server exposes `search_documentation` and `fetch_documentation` tools (prefixed by server name, e.g. `mcp__fastmcp-Docs__search_documentation`). Prefer these for targeted API lookups over general web search.
