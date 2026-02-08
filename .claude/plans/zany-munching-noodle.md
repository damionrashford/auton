# Webhook Integration Plan

## Context

Auton currently has no way to send or receive HTTP webhooks. The Communication agent can message via Slack, Gmail, and Google Chat — but cannot POST data to external APIs or receive inbound events from services like GitHub, Stripe, or custom integrations. This plan adds full webhook send/receive support following the established patterns (Slack, Blockchain integrations as templates).

**No new dependencies needed** — httpx is already in the project, and Python's built-in `hmac`/`hashlib` handles signature verification.

## Design Decisions

- **No new agent role** — webhook tools go on the **COMMUNICATION** agent (webhooks are a communication channel)
- **Tool prefix**: `webhook_*` (6 tools: 3 write, 3 read)
- **Inbound receiver**: FastAPI `POST /webhooks/{webhook_id}` endpoint with HMAC-SHA256 verification
- **Inbound processing**: Fire-and-forget `asyncio.create_task` re-entering the agent loop (same pattern as `scheduler/service.py:_execute_job`)
- **Outbound retries**: Exponential backoff, configurable max attempts, tracked in Postgres

## Files to Create (3)

### `src/auton/webhooks/__init__.py`
Package exports: `WebhookService`, `WEBHOOK_TOOLS`, `handle_webhook_tool`

### `src/auton/webhooks/client.py`
`WebhookService` class following `SlackService`/`BlockchainService` pattern:
- `start()` / `stop()` / `is_connected` lifecycle
- `send_webhook(url, payload, method, headers, conversation_id)` — outbound POST/PUT/PATCH with retry + delivery logging
- `get_webhook(url, params, headers)` — read-only GET (no retry, no logging)
- `create_subscription(webhook_url, description, signing_secret, agent_role)` — register inbound endpoint in DB
- `delete_subscription(webhook_id)` — remove from DB
- `list_subscriptions()` / `list_deliveries(conversation_id, limit)` — query DB
- `verify_signature(payload, signature, secret)` — static HMAC-SHA256 check
- Internal: `_log_delivery()`, `_update_delivery()` — Postgres tracking

Uses `httpx.AsyncClient` (same pattern as `core/llm.py:48-55`).

### `src/auton/webhooks/tools.py`
6 tool schemas + `handle_webhook_tool()` handler:

| Tool | Type | Confirmation |
|------|------|-------------|
| `webhook_send` | POST/PUT/PATCH to external URL | Yes (WRITE) |
| `webhook_get` | GET from URL | No (READ) |
| `webhook_create_subscription` | Register inbound endpoint | Yes (WRITE) |
| `webhook_delete_subscription` | Remove endpoint | Yes (WRITE) |
| `webhook_list_subscriptions` | List endpoints | No (READ) |
| `webhook_list_deliveries` | Delivery history | No (READ) |

## Files to Modify (11)

### `src/auton/storage/schema.sql` — 3 new tables
After `agent_delegations` table:
- `webhook_subscriptions` (id, webhook_url, description, signing_secret, agent_role, enabled, metadata, timestamps)
- `webhook_deliveries` (id, conversation_id FK, url, method, payload, headers, status_code, response_body, attempt, status, error, timestamps)
- `webhook_events` (id, webhook_id FK, payload, headers, signature_valid, agent_conversation_id FK, processed, error, timestamps)

Additive `CREATE TABLE IF NOT EXISTS` — auto-applied by `run_migrations()`.

### `src/auton/config.py` — 5 new fields
After Slack config block (~line 237):
- `webhook_enabled: bool = True`
- `webhook_signing_secret: str = ""`
- `webhook_timeout: float = 30.0`
- `webhook_max_retries: int = 3`
- `webhook_retry_backoff: float = 2.0`

### `src/auton/core/safety.py` — 3 tools added to WRITE_TOOLS
Add `webhook_send`, `webhook_create_subscription`, `webhook_delete_subscription` to the `WRITE_TOOLS` frozenset.

### `src/auton/agents/registry.py` — COMMUNICATION gets webhook access
Add `"webhook_*"` to `allowed_tool_patterns` for `AgentRole.COMMUNICATION` (~line 134).

### `src/auton/mcp/server.py` — webhook service init in lifespan
After blockchain init (~line 269), before cron dependency injection:
- Import `WebhookService`, `WEBHOOK_TOOLS`, `handle_webhook_tool`
- Create service with config values + db_pool
- `await webhook_service.start()`
- `bridge.register_internal_tools(WEBHOOK_TOOLS, handler, "webhook")`
- Conditional on `settings.webhook_enabled`

### `src/auton/app.py` — inbound webhook receiver endpoint
Add `POST /webhooks/{webhook_id}` route + `_process_webhook_event()` background helper:
1. Fetch subscription from DB
2. Verify HMAC-SHA256 signature (`X-Webhook-Signature: sha256=...`)
3. Log event in `webhook_events`
4. `asyncio.create_task(_process_webhook_event(...))` — non-blocking
5. Return 202 Accepted immediately

`_process_webhook_event()` follows `scheduler/service.py:_execute_job()` pattern:
- Get dependencies from DI singletons
- Build `AgentConfig(role=subscription.agent_role)`
- Call `run_agent(user_message=..., headless=True)`
- Update event status in DB

### `src/auton/agents/prompts.py` — 3 locations
1. `ORCHESTRATOR_PROMPT` — add webhook to Communication capabilities
2. `ORCHESTRATOR_PROMPT` — add delegation tips ("send webhook" -> `delegate_to_communication`)
3. `COMMUNICATION_AGENT_PROMPT` — add Webhook Tools section describing all 6 tools

### `.env.example` — 5 env vars
After Slack section: `WEBHOOK_ENABLED`, `WEBHOOK_SIGNING_SECRET`, `WEBHOOK_TIMEOUT`, `WEBHOOK_MAX_RETRIES`, `WEBHOOK_RETRY_BACKOFF`

### `CLAUDE.md` — 3 additions
1. Tool prefix conventions: add `webhook_` prefix
2. Other Subsystems: add `webhooks/` description
3. Configuration groups: add Webhooks group

### `AGENTS.md` — 2 additions
1. Tool Access Patterns table: add `webhook_` prefix row
2. COMMUNICATION per-role access: add `webhook_*` tools

### `README.md` — 2 additions
1. Internal Tools table: add Webhooks row (6 tools, `webhook_*`)
2. Communication agent: mention webhook capabilities

## Implementation Order

1. Schema (`schema.sql`) — tables must exist first
2. Config (`config.py`) — settings needed by service
3. Service (`webhooks/client.py`) — core logic
4. Tools (`webhooks/tools.py`) — agent-facing schemas
5. Package init (`webhooks/__init__.py`) — exports
6. Safety (`core/safety.py`) — gate write ops
7. Registry (`agents/registry.py`) — grant COMMUNICATION access
8. Server lifespan (`mcp/server.py`) — init + register
9. Receiver endpoint (`app.py`) — inbound webhook handling
10. Prompts (`agents/prompts.py`) — teach agents about webhooks
11. Env template (`.env.example`) — config template
12. Docs (`CLAUDE.md`, `AGENTS.md`, `README.md`) — documentation

## Verification

```bash
# 1. Lint passes
uv run ruff check src/

# 2. Type check passes
uv run mypy src/

# 3. Server starts without errors
uv run uvicorn auton.app:app --host 0.0.0.0 --port 8000

# 4. Health check
curl http://localhost:8000/health

# 5. Test outbound webhook (via MCP chat tool or Slack)
# Ask: "Send a webhook POST to https://httpbin.org/post with payload {\"test\": true}"
# -> Should trigger confirmation, then deliver

# 6. Test inbound webhook
# First: create subscription via agent
# Then: curl -X POST http://localhost:8000/webhooks/{id} \
#   -H "Content-Type: application/json" \
#   -H "X-Webhook-Signature: sha256=..." \
#   -d '{"event": "test"}'
# -> Should return 202 and trigger agent processing
```

## Downstream Effects

- **Safety system**: 3 new tools in WRITE_TOOLS → confirmation dialogs in Slack/MCP
- **Orchestrator**: Now knows to delegate webhook tasks to COMMUNICATION agent
- **Database**: 3 new tables auto-created on startup (no manual migration)
- **Config**: 5 new env vars (all have safe defaults, no breakage if unset)
- **No breaking changes**: All webhook features are additive and opt-in
