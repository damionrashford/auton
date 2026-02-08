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
"Research the latest DeFi yields on Base, create a 15% off discount on
 my Shopify store, then send a summary to #defi-research"

Orchestrator
  -> Research Agent    web_search + social_search + content_operations
  -> Blockchain Agent  cb_aave_portfolio (check current positions)
  -> Shopify Agent     shop_discount_create (15% off code)
  -> Communication     slack_send_message to #defi-research
  -> Synthesize all results into one reply
```

Each specialist only sees its own tools. The Research Agent cannot send Slack messages. The Blockchain Agent cannot browse the web. The Shopify Agent cannot access Google Workspace. The orchestrator cannot execute anything directly — it can only delegate.

---

## Agents

| Role | Tools | What It Does |
|:-----|:------|:-------------|
| **Orchestrator** | `delegate_to_*`, `memory_recall` | Task decomposition, delegation, result synthesis |
| **Research** | 10 search tools + Playwright read-only | Web, social, news, GitHub, academic papers, OCR, site mapping |
| **Browser** | Full Playwright suite | Click, type, fill forms, scroll, screenshots, PDF generation |
| **Communication** | Slack + Gmail + Google Chat + Webhooks | Messages, emails, HTTP webhooks, threads, channels |
| **Workspace** | Google Workspace | Calendar, Drive, Docs, Sheets, Slides, Forms, Tasks |
| **Blockchain** | 19 Coinbase AgentKit tools | Wallets, swaps, DeFi (Aave V3), NFTs, streaming, .base.eth |
| **Shopify** | 25 store management tools | Products, orders, customers, inventory, discounts, fulfillment |

---

## Architecture

```
Slack (Socket Mode)
  |
  v
SlackBoltUI ── rate limiting (5/min, async-locked) + bot self-check
  |
  v
AgentQueue ── bounded concurrency (default: 3 concurrent runs)
  |
  v
OrchestratorAgent.run()
  |
  |-- decompose_task()        LLM selects specialists
  |-- execute_tasks()         parallel or sequential
  |     |
  |     |-- Research Agent    (RivalSearchMCP + Playwright read-only)
  |     |-- Browser Agent     (Playwright full access)
  |     |-- Communication     (Slack + Gmail + Google Chat + Webhooks)
  |     |-- Workspace         (Google Calendar, Drive, Docs, Sheets)
  |     |-- Blockchain        (Coinbase AgentKit)
  |     |-- Shopify           (Admin + Storefront GraphQL API)
  |     |
  |     each agent: filtered tools, role prompt, isolated state
  |     confirmation_callback: per-request (no shared state)
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

| Source | Prefix | Tools |
|:-------|:-------|:------|
| Shopify Admin + Storefront API | `shop_*` | 25 tools (products, orders, customers, inventory, discounts, fulfillment, collections, metafields, storefront cart) |
| Coinbase AgentKit | `cb_*` | 19 tools (wallets, swaps, DeFi, NFTs, streaming) |
| Slack Bolt | `slack_*` | 8 tools (messages, channels, threads, reactions, files) |
| Webhooks | `webhook_*` | 6 tools (send, receive, subscriptions, deliveries) |
| Cron Scheduler | `cron_*` | 3 tools (create, delete, list jobs) |
| RAG Pipeline | `rag_*` | 6 tools (upload, search, search_doc, list, get, delete) |
| Memory (pgvector) | `memory_*` | 3 tools (store, recall, forget) |
| Delegation | `delegate_to_*` | 7 tools (one per specialist agent) |

**Total: 87 tools** across 7 specialist agents.

---

## Shopify Integration

The Shopify Agent provides full store management via the GraphQL Admin API (v2026-01) and Storefront API.

| Domain | Tools | Operations |
|:-------|:------|:-----------|
| **Products** | `shop_products_list`, `shop_product_get`, `shop_product_create`, `shop_product_update` | Search, view details, create, update |
| **Orders** | `shop_orders_list`, `shop_order_get`, `shop_order_update` | Search, view details, update tags/notes |
| **Customers** | `shop_customers_list`, `shop_customer_get`, `shop_customer_update` | Search, view details, update |
| **Inventory** | `shop_inventory_query`, `shop_inventory_adjust` | Check levels, adjust quantities |
| **Collections** | `shop_collections_list`, `shop_collection_create` | List, create |
| **Discounts** | `shop_discounts_list`, `shop_discount_create` | List, create percentage codes |
| **Fulfillment** | `shop_fulfillments_list`, `shop_fulfillment_create` | List orders, mark shipped |
| **Content** | `shop_metafields_query`, `shop_metafield_set`, `shop_pages_list` | Metafields, pages |
| **Storefront** | `shop_storefront_products`, `shop_storefront_cart_create` | Public search, cart creation |
| **Advanced** | `shop_info`, `shop_graphql` | Store info, arbitrary GraphQL |

Authentication uses admin-generated tokens (`shpat_...`) — no OAuth flow needed.

---

## RAG Pipeline

Upload documents of any type — PDFs, Word, Excel, Jupyter notebooks, images (OCR), code files, Markdown — and search them semantically from any agent.

| Component | Technology | Details |
|:----------|:-----------|:--------|
| **Embedding** | `bge-small-en-v1.5` via sentence-transformers | 384-dim, local CPU, <5ms per query, 8k chunks/sec batch |
| **Vector Store** | pgvector (HNSW cosine index) | Same Neon Postgres, new `document_chunks` table |
| **Parsing** | pymupdf, python-docx, openpyxl, nbformat | PDF, Word, Excel, Jupyter, CSV, images (OCR), 60+ extensions |
| **Chunking** | Recursive character splitter | 500 chars, 100 overlap, respects paragraph/sentence boundaries |

| Tool | Description |
|:-----|:------------|
| `rag_upload` | Upload a file (URL or path), parse, chunk, embed, store |
| `rag_search` | Semantic search across all documents |
| `rag_search_doc` | Search within a specific document |
| `rag_list` | List all uploaded documents |
| `rag_get` | Get full content of a document |
| `rag_delete` | Delete a document and its chunks |

Agents with RAG access: Research (full), Shopify (read), Communication (read), Workspace (read).

---

## Safety

Every write operation requires explicit user approval. Three confirmation paths:

| Path | Mechanism | Timeout |
|:-----|:----------|:--------|
| **MCP** | `ctx.elicit()` structured dialog | — |
| **Slack** | Thread-based yes/no poll | 60s (defaults to deny) |
| **Block** | No mechanism available | Blocked entirely |

Tool confirmation rules:

- All `cb_*` blockchain tools require confirmation **unconditionally**
- `shop_*` tools matched against dangerous keywords (create, update, delete, adjust, set)
- `gw_*` tools matched against dangerous keywords (create, delete, send, modify, transfer, etc.)
- Explicit `WRITE_TOOLS` frozenset for Slack, Cron, Webhook, and Memory operations

### Concurrency Safety

- **Bounded concurrency**: `AgentQueue` limits concurrent agent runs (default: 3) via `asyncio.Semaphore`
- **Per-request callbacks**: Confirmation callbacks flow as parameters, not shared instance state
- **Thread-safe rate limiting**: Slack rate tracker uses `asyncio.Lock`

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- Redis (caching, session state, task queue)
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
# Persistent storage + semantic memory
NEON_DATABASE_URL=postgresql://...

# Google Workspace
GOOGLE_WORKSPACE_MCP_URL=http://localhost:8001/mcp

# Blockchain (Coinbase AgentKit)
BLOCKCHAIN_ENABLED=true
CDP_API_KEY_ID=...
CDP_API_KEY_SECRET=...
CDP_WALLET_SECRET=...

# Shopify store management
SHOPIFY_ENABLED=true
SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
SHOPIFY_ADMIN_API_TOKEN=shpat_...
SHOPIFY_STOREFRONT_API_TOKEN=...
SHOPIFY_API_VERSION=2026-01

# RAG (document upload + semantic search)
RAG_ENABLED=true
RAG_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

### Run

```bash
uv run uvicorn auton.app:app --host 0.0.0.0 --port 8000
```

The server starts the MCP endpoint at `/mcp`, connects to configured MCP servers, registers internal tools, initializes the orchestrator with bounded concurrency, and starts the Slack listener. Then `@mention` the bot or DM it.

### Slack Setup

1. Create app at [api.slack.com/apps](https://api.slack.com/apps)
2. Enable **Socket Mode** — get `SLACK_APP_TOKEN` (`xapp-...`)
3. Add Bot Token Scopes: `app_mentions:read`, `chat:write`, `channels:history`, `channels:read`, `im:history`, `im:read`, `im:write`, `search:read`, `reactions:write`, `users:read`, `files:write`
4. Subscribe to events: `app_mention`, `message.im`
5. Install to workspace — get `SLACK_BOT_TOKEN` (`xoxb-...`)

---

## Configuration

All configuration via environment variables. See [`.env.example`](.env.example) for the full template.

| Group | Key Fields |
|:------|:-----------|
| **xAI LLM** | `XAI_API_KEY`, `XAI_MODEL` (default: `grok-4.1-fast`, 2M context) |
| **Playwright** | `PLAYWRIGHT_MCP_PORT`, headless, browser, stealth, viewport |
| **Google Workspace** | `GOOGLE_WORKSPACE_MCP_URL`, `GOOGLE_WORKSPACE_MCP_ENABLED` |
| **Slack** | `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_ENABLED` |
| **Shopify** | `SHOPIFY_ENABLED`, `SHOPIFY_STORE_DOMAIN`, `SHOPIFY_ADMIN_API_TOKEN`, `SHOPIFY_STOREFRONT_API_TOKEN` |
| **RAG** | `RAG_ENABLED`, `RAG_EMBEDDING_MODEL` (default: `BAAI/bge-small-en-v1.5`) |
| **Blockchain** | `BLOCKCHAIN_ENABLED`, `BLOCKCHAIN_NETWORK`, CDP credentials |
| **Webhooks** | `WEBHOOK_ENABLED`, `WEBHOOK_SIGNING_SECRET`, timeout, retries |
| **Storage** | `NEON_DATABASE_URL`, `REDIS_HOST` |
| **Queue** | `DOCKET_URL` (Redis), `MAX_CONCURRENT_AGENT_RUNS` (default: 3) |
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
  config.py                 Pydantic Settings (92+ fields)
  models.py                 Shared data models

  agents/
    roles.py                AgentRole enum (7 roles), AgentConfig, DelegationTask
    registry.py             Tool filtering per role (glob patterns)
    orchestrator.py         Decompose -> delegate -> synthesize
    prompts.py              Role-specific system prompts (7 agents)
    tools.py                Delegation tools (delegate_to_*, 7 tools)

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

  queue/
    worker.py               AgentQueue — bounded concurrency via semaphore

  rag/
    embedder.py             Local embedding (bge-small-en-v1.5, 384-dim, CPU)
    parser.py               Multi-format document parser (PDF, Word, Excel, etc.)
    chunker.py              Recursive character text splitter
    service.py              RAGService — ingest + search pipeline
    tools.py                6 RAG tool schemas + handler

  storage/
    postgres.py             asyncpg pool + migrations
    conversations.py        NeonConversationStore + LRU cache
    memory.py               pgvector semantic memory
    memory_tools.py         memory_store, memory_recall, memory_forget
    schema.sql              Database schema (9 tables)

  slack/
    bolt_app.py             Slack Bolt UI (Socket Mode, async rate limiter)
    client.py               Outbound Slack API wrapper
    tools.py                8 tool schemas + handler

  shopify/
    client.py               Shopify GraphQL API wrapper (httpx, Admin + Storefront)
    tools.py                25 tool schemas + GraphQL queries + handler

  blockchain/
    client.py               Coinbase AgentKit wrapper
    tools.py                19 tool schemas + handler

  webhooks/
    client.py               Outbound HTTP + inbound receiver
    tools.py                6 tool schemas + handler

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
| **E-commerce** | [Shopify GraphQL Admin API](https://shopify.dev/docs/api/admin-graphql) (v2026-01) |
| **RAG** | [sentence-transformers](https://sbert.net/) + [bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) |
| **Blockchain** | [Coinbase AgentKit](https://github.com/coinbase/agentkit) |
| **Chat** | [Slack Bolt](https://api.slack.com/bolt) (Socket Mode) |
| **Database** | [Neon Postgres](https://neon.tech/) + pgvector |
| **Cache** | Redis |
| **Queue** | [arq](https://github.com/samuelcolvin/arq) (async Redis) |
| **Scheduling** | APScheduler |
| **Tokens** | tiktoken |
| **Observability** | OpenTelemetry (optional) |

---

## Extending

Adding a new specialist agent follows a 10-step recipe. See [CLAUDE.md](CLAUDE.md) for the full guide.

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
