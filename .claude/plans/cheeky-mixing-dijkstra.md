# Implementation Plan: Fix All 22 Audit Issues for Autonomous Agent

## Context

A deep audit of the FastMCP AI Agent codebase (5,530 lines, 30+ files) found 22 issues preventing reliable autonomous operation. Three are P0 runtime crashers, several are high-severity functional bugs, and the rest are design/reliability improvements. This plan fixes all of them across 11 files (~230 lines changed).

### Key API Findings (from reading installed FastMCP 3.0 source)

- **`ctx.elicit()`** returns `AcceptedElicitation[T] | DeclinedElicitation | CancelledElicitation` — NOT a dict. Check with `isinstance(result, AcceptedElicitation)`. Types imported from `fastmcp.server.elicitation`.
- **`ResponseCachingMiddleware`** accepts `call_tool_settings=CallToolSettings(excluded_tools=["chat"])` to exclude specific tools from caching.

---

## Phase 1: Critical Fixes (P0 — will crash at runtime)

### Fix #1 — `_InMemoryShim` missing methods → `mcp/server.py`
**Lines 270-296**: Add missing no-op async methods so agent doesn't crash without Postgres:
- `log_decision(conversation_id, iteration, event_type, details)` → `pass`
- `get_daily_cost()` → `return 0.0`
- `get_conversation_cost(conversation_id)` → `return 0.0`

Add `from typing import Any` import.

### Fix #3 — `ctx.elicit()` broken → `core/agent.py`
**Lines 622-658**: Replace dict-style access with proper type checking:
```python
# OLD (broken):
confirmation = await ctx.elicit(message=..., response_type=dict)
if confirmation.get("action") != "accept":

# NEW (correct):
from fastmcp.server.elicitation import AcceptedElicitation
result = await ctx.elicit(message=..., response_type=None)
if not isinstance(result, AcceptedElicitation):
```
Use `result.action` for logging the decline/cancel reason.

### Fix #4 — Response caching breaks chat tool → `mcp/middleware.py`
**Lines 56-58**: Exclude the `chat` tool from call_tool caching:
```python
from fastmcp.server.middleware.caching import ResponseCachingMiddleware, CallToolSettings

mcp.add_middleware(
    ResponseCachingMiddleware(
        cache_storage=namespaced_store,
        call_tool_settings=CallToolSettings(excluded_tools=["chat"]),
    )
)
```
Keep list/resource/prompt caching — only tool-call caching for `chat` is problematic.

---

## Phase 2: High Severity (P1)

### Fix #2 — Plan generated but never used → `core/agent.py`
**Lines 183-190**: After generating the plan, inject it as a system message so the LLM actually follows it:
```python
if plan:
    plan_text = "Multi-step execution plan:\n"
    for step in plan:
        plan_text += f"{step.get('step','?')}. {step.get('action','')}"
        if step.get('tool_hint'): plan_text += f" (suggested tool: {step['tool_hint']})"
        plan_text += "\n"
    plan_text += "\nFollow this plan systematically."
    plan_msg = ChatMessage(role=ChatRole.SYSTEM, content=plan_text)
    messages.append(plan_msg)
    await store.append(cid, plan_msg)
```

### Fix #5 — Token counting model name mismatch → `core/tokenizer.py`
**Lines 35-43 and 88-91**: Strip provider prefix before tiktoken:
```python
base_model = model.split("/", 1)[-1] if "/" in model else model
enc = tiktoken.encoding_for_model(base_model)
```
Apply to both `count_messages_tokens()` and `count_text_tokens()`.

### Fix #6 — Cron jobs bypass confirmation → `core/agent.py` + `scheduler/service.py`
- Add `headless: bool = False` parameter to `run_agent()` signature
- Update confirmation gate: `if ctx and settings.require_confirmation and not headless and requires_confirmation(...)`
- In `scheduler/service.py:326`: pass `headless=True` to `run_agent()` call

### Fix #7 — Parallel tool execution fragility → `core/agent.py`
**Lines 574-581**: Change `asyncio.gather(*tasks, return_exceptions=False)` to `return_exceptions=True`. Loop through results, convert any `Exception` instances to error tuples `(tc, "[error] ...", False, 0)`.

### Fix #10 — No tool call timeout → `core/agent.py`
**Line 664**: Wrap `bridge.call_tool()` in `asyncio.wait_for()`:
```python
result_text = await asyncio.wait_for(
    bridge.call_tool(fn_name, fn_args),
    timeout=settings.tool_timeout,
)
```
Catch `asyncio.TimeoutError` → return error tuple. Also wrap the retry call (lines 677-680) the same way.

---

## Phase 3: Medium Severity (P2)

### Fix #8 — Slack status always False → `app.py`
**Line 113**: Change `"SlackMCP" in bridge.connected_servers` to `"slack" in bridge.internal_tool_sources`.

### Fix #9 — `.env.example` outdated → `.env.example`
Complete rewrite to include all Settings fields: Slack SDK tokens (`SLACK_BOT_TOKEN`, `SLACK_ENABLED`), Google Workspace, cron, cost guardrails, context window, sampling params, provider routing, reasoning tokens, Playwright full config.

### Fix #11 — `get_settings()` not cached → `config.py`
**Lines 483-485**: Add `@functools.lru_cache(maxsize=1)` decorator. Add `import functools`.

### Fix #12 — Compaction breaks tool-call pairing → `core/agent.py`
**Lines 446-449**: Before splitting into old/tail, walk the boundary backward to find a non-tool message:
```python
safe_tail_start = len(messages) - tail_count
while safe_tail_start > 1:
    msg = messages[safe_tail_start]
    if msg.role == ChatRole.TOOL or (msg.tool_calls and len(msg.tool_calls) > 0):
        safe_tail_start -= 1
    else:
        break
```

### Fix #13 — Stuck-loop detection too narrow → `core/agent.py`
**Line 152**: Replace `last_tool_key: str | None = None` with `recent_tool_calls: deque[str] = deque(maxlen=5)`. Update `_execute_single_tool` to check `if current_tool_key in recent_tool_calls` instead of `== last_tool_key`. Thread the deque through `_execute_tools_parallel` → `_execute_single_tool`.

### Fix #14 — No Redis health check → `mcp/server.py`
In `agent_lifespan()`, after loading settings: try a Redis ping, log warning if unreachable. Non-blocking — don't prevent startup.

### Fix #15 — Memory metadata not JSON-serialized → `storage/memory.py`
**Line 68**: Change `metadata or {}` to `json.dumps(metadata or {})` and add `::jsonb` cast to the SQL `$4` parameter. Add `import json` at top.

### Fix #16 — Settings at import time → `mcp/server.py`
**Line 300**: Replace `_init_settings = get_settings()` with a lazy `_get_init_settings()` function. Update `FastMCP()` constructor and `@mcp.tool()` decorator to call `_get_init_settings()`.

---

## Phase 4: Low Severity (P3)

### Fix #19 — Context window not adaptive → `config.py`
Add a `_MODEL_CONTEXT_WINDOWS` dict mapping base model names to context sizes. Add `effective_context_window` property. Update `agent.py:170` to use `settings.effective_context_window`.

### Fix #20 — Internal tool source detection fragile → `bridge/manager.py`
Add `_internal_tool_source_map: dict[str, str]` tracking tool→source during `register_internal_tools()`. Replace `internal_tool_sources` property to use this map directly instead of prefix-matching.

### Fix #21 — IVFFlat index on empty tables → `storage/schema.sql`
**Line 117**: Change `USING ivfflat ... WITH (lists = 100)` to `USING hnsw (embedding vector_cosine_ops)`. HNSW works well from 0 to millions of rows.

---

## Deferred (not in this implementation)
- **#17**: Tests (separate large task)
- **#18**: `mcp.json` (user-specific configuration)
- **#22**: System prompt versioning (complex enhancement)

---

## Files Modified (implementation order)

| # | File | Fixes | Est. Lines |
|---|------|-------|-----------|
| 1 | `src/fast_mcp_agent/config.py` | #11, #19 | ~30 |
| 2 | `src/fast_mcp_agent/core/tokenizer.py` | #5 | ~10 |
| 3 | `src/fast_mcp_agent/mcp/server.py` | #1, #14, #16 | ~45 |
| 4 | `src/fast_mcp_agent/mcp/middleware.py` | #4 | ~8 |
| 5 | `src/fast_mcp_agent/core/agent.py` | #2, #3, #6, #7, #10, #12, #13 | ~130 |
| 6 | `src/fast_mcp_agent/scheduler/service.py` | #6 | ~3 |
| 7 | `src/fast_mcp_agent/bridge/manager.py` | #20 | ~15 |
| 8 | `src/fast_mcp_agent/app.py` | #8 | ~1 |
| 9 | `src/fast_mcp_agent/storage/memory.py` | #15 | ~3 |
| 10 | `src/fast_mcp_agent/storage/schema.sql` | #21 | ~2 |
| 11 | `.env.example` | #9 | Rewrite |

**Total**: ~250 lines across 11 files

---

## Verification

1. **Lint**: `uv run ruff check src/` — zero new violations
2. **Type check**: `uv run mypy src/` — zero new errors
3. **Startup smoke test**: `uv run uvicorn fast_mcp_agent.app:app --host 0.0.0.0 --port 8000` — server starts, `/health` returns 200
4. **Without Postgres**: Start without `NEON_DATABASE_URL` — verify no crash (tests `_InMemoryShim` fix)
5. **Status endpoint**: `GET /api/status` — verify `slack_connected` field reflects actual state
6. **Agent loop**: Send a chat message through MCP — verify plan injection, tool timeout, no caching of responses
