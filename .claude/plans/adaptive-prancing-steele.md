# Replace OpenRouter with xAI Python SDK

## Context

The application currently uses OpenRouter (httpx-based REST client in `core/llm.py`) as the LLM provider. We are **removing OpenRouter entirely** and replacing it with the official xAI Python SDK (`xai-sdk`). This eliminates the middleman, uses xAI's native gRPC protocol, and gives access to xAI-specific features: server-side tools (web search, X search, code execution), native tokenizer API, Collections API for embeddings, reasoning models, and built-in OpenTelemetry.

## xAI SDK API Surface (from GitHub research)

```python
from xai_sdk import AsyncClient
from xai_sdk.chat import system, user, tool, tool_result
from xai_sdk.tools import web_search, x_search, code_execution
from xai_sdk.search import SearchParameters

client = AsyncClient()  # reads XAI_API_KEY from env

# Chat with tools
chat = client.chat.create(
    model="grok-4.1-fast",
    messages=[system("...")],
    tools=[tool(name="...", description="...", parameters={...})],
    reasoning_effort="low",  # or "high"
)
chat.append(user("..."))
response = await chat.sample()        # non-streaming
async for response, chunk in chat.stream():  # streaming

# Response fields
response.content          # text
response.tool_calls       # list of tool calls
response.reasoning_content  # reasoning tokens
response.usage.prompt_tokens
response.usage.completion_tokens
response.usage.reasoning_tokens
response.usage.total_tokens
response.citations        # from search

# Tokenizer
tokens = await client.tokenize.tokenize_text("hello", model="grok-3")

# Embeddings (Collections API)
collection = await client.collections.create(name="...", model_name="grok-embedding-small")
await client.collections.upload_document(collection_id, name="...", data=b"...")
results = await client.collections.search(query="...", collection_ids=[...])

# Models API
models = await client.models.list_language_models()
embedding_models = await client.models.list_embedding_models()
```

## All Touchpoints to Change

### 1. `core/llm.py` — REWRITE (the big one)

Current: `LLMClient` wraps httpx, builds OpenRouter payloads, handles retry/streaming/embeddings.

New: `LLMClient` wraps `xai_sdk.AsyncClient`. Methods to rewrite:

| Current Method | New Implementation |
|---|---|
| `__init__(settings)` | Store settings, create `AsyncClient(api_key=...)` |
| `start()` | No-op (SDK handles connection) |
| `stop()` | No-op (SDK handles cleanup) |
| `_build_payload(messages, tools, stream, conversation_id)` | **Remove** — SDK builds payloads internally |
| `chat_completion(messages, tools, conversation_id)` | Create `chat`, append messages, call `chat.sample()`, convert response to dict |
| `chat_completion_stream(messages, tools, conversation_id)` | Create `chat`, call `chat.stream()`, yield chunks |
| `_request_with_retry(payload)` | **Remove** — SDK handles gRPC retries |
| `embed(texts, model)` | **Replace** — use xAI tokenizer or Collections API |

Key differences:
- SDK uses `xai_sdk.chat.system/user/tool/tool_result` message constructors, NOT dicts
- SDK manages conversation state via `chat.create()` + `chat.append()` + `chat.sample()`
- Response object has `.content`, `.tool_calls`, `.usage` as attributes (not dict keys)
- Need to convert between our `ChatMessage` model and SDK message types

### 2. `core/agent.py` — UPDATE response parsing

The agent loop currently parses OpenRouter's JSON dict format:
```python
data = await llm.chat_completion(messages, tools, conversation_id=cid)
choice = data.get("choices", [{}])[0]
msg = choice.get("message", {})
raw_tool_calls = msg.get("tool_calls")
```

Must change to parse xAI SDK response objects:
```python
response = await llm.chat_completion(messages, tools, conversation_id=cid)
# response is now a normalized dict (LLMClient converts SDK response)
```

**Approach**: Keep `LLMClient.chat_completion()` returning a dict in the same format the agent loop expects. The conversion happens inside LLMClient, not in the agent loop. This minimizes changes to agent.py.

### 3. `core/tokenizer.py` — REPLACE tiktoken with xAI tokenizer

Current: Uses `tiktoken` (OpenAI's tokenizer) with fallback to `cl100k_base`.

New options:
- **Option A**: Use `client.tokenize.tokenize_text(text, model="grok-4.1-fast")` — native xAI tokenizer, exact counts
- **Option B**: Keep tiktoken as a fast local fallback (no network call) for compaction threshold checks

**Recommendation**: Use xAI tokenizer for accuracy but cache locally. For hot-path compaction checks, keep tiktoken as fast approximation since exact counts aren't critical there.

### 4. `storage/memory.py` — REPLACE OpenRouter embeddings

Current: `MemoryStore` calls `llm.embed(texts)` which hits OpenRouter's `/embeddings` endpoint.

New: Two options:
- **Option A**: Use xAI Collections API (`client.collections`) — managed RAG with `grok-embedding-small`. Upload documents, search via API. Replaces pgvector entirely.
- **Option B**: Keep pgvector, use xAI's embedding model via the REST API (xAI has an OpenAI-compatible endpoint at `https://api.x.ai/v1/embeddings`)

**Recommendation**: Option B for now — keep pgvector, use xAI's OpenAI-compatible embedding endpoint. This is the smallest change. Collections API can be a future upgrade.

### 5. `config.py` — REPLACE OpenRouter fields with xAI fields

Remove ~30 OpenRouter-specific fields. Add:

```python
# ── xAI ──────────────────────────────────────────────────────
xai_api_key: str = Field(default="", description="xAI API key.")
xai_model: str = Field(default="grok-4.1-fast", description="Primary model.")
xai_reasoning_effort: str = Field(default="", description="low or high.")
xai_max_tokens: int | None = Field(default=None)
xai_temperature: float | None = Field(default=None)
xai_embedding_model: str = Field(default="grok-embedding-small")
```

Remove: ALL `openrouter_*` fields (api_key, model, base_url, embedding_model, fallback_models, temperature, top_p, top_k, frequency_penalty, presence_penalty, repetition_penalty, min_p, top_a, max_tokens, seed, provider_sort, provider_order, provider_ignore, provider_allow_fallbacks, provider_require_parameters, provider_data_collection, reasoning_effort, reasoning_max_tokens, reasoning_exclude, transforms_middle_out, plugin_web_search, plugin_response_healing, max_retries, retry_base_delay, request_timeout).

### 6. `models.py` — UPDATE UsageStats

Current `UsageStats.from_response()` parses OpenRouter's dict format. Needs to parse xAI SDK response usage.

### 7. `pyproject.toml` — SWAP dependencies

Remove: `httpx` (only used by LLMClient), `tiktoken` (optional, can keep for fast local counts)
Add: `xai-sdk>=1.0.0`

### 8. `.env.example` — UPDATE

Replace `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL`, all `OPENROUTER_*` with:
```
XAI_API_KEY=xai-...
XAI_MODEL=grok-4.1-fast
```

### 9. `mcp/server.py` — MINOR (LLMClient init unchanged)

`llm = LLMClient(settings)` / `await llm.start()` / `await llm.stop()` — same interface, different internals.

### 10. `telemetry/spans.py` — OPTIONAL

xAI SDK has built-in OpenTelemetry. Could remove our manual spans or keep them as supplementary.

### 11. Other files with `openrouter` references

- `storage/schema.sql` — `usage_logs.model` column stores model name, no change needed
- `agents/orchestrator.py` — references `settings.openrouter_model`, change to `settings.xai_model`
- `CLAUDE.md`, `README.md`, `MEMORY.md` — update documentation

## Implementation Order

### Stage 1: Config + Dependencies
- Remove OpenRouter fields from `config.py`, add xAI fields
- Swap `httpx`→`xai-sdk` in `pyproject.toml`
- Update `.env.example`

### Stage 2: Rewrite LLMClient
- Replace `core/llm.py` entirely with xAI SDK wrapper
- Keep the same public interface: `chat_completion()`, `chat_completion_stream()`, `embed()`
- Convert xAI SDK responses to the same dict format agent.py expects
- Handle tool calling format conversion (SDK `tool()` ↔ our OpenAI-format schemas)

### Stage 3: Update Tokenizer
- Replace tiktoken with xAI tokenizer API in `core/tokenizer.py`
- Keep tiktoken as fast fallback for compaction checks

### Stage 4: Update Embeddings
- Change `embed()` in LLMClient to use xAI's OpenAI-compatible endpoint
- Or use SDK's collections API if embeddings are directly available

### Stage 5: Fix All References
- `config.py` property `effective_context_window` — update model map
- `agents/orchestrator.py` — `settings.openrouter_model` → `settings.xai_model`
- `models.py` `UsageStats.from_response()` — parse xAI format
- `core/agent.py` — verify response parsing still works with normalized dicts

### Stage 6: Update Docs
- `CLAUDE.md`, `README.md`, `MEMORY.md`, `.env.example`

## Critical Design Decision

**Keep the response format normalized.** The new `LLMClient.chat_completion()` still returns a dict that matches the OpenAI chat completion format:
```python
{
    "choices": [{"message": {"content": "...", "tool_calls": [...]}, "finish_reason": "stop"}],
    "model": "grok-4.1-fast",
    "usage": {"prompt_tokens": N, "completion_tokens": N, ...}
}
```

This way `core/agent.py` needs minimal changes — it already parses this format. The conversion from xAI SDK response objects to this dict happens inside LLMClient.

## Files Summary

### Rewrite (1)
- `src/fast_mcp_agent/core/llm.py` — full rewrite with xai_sdk.AsyncClient

### Heavy Modify (3)
- `src/fast_mcp_agent/config.py` — remove ~30 openrouter fields, add ~6 xai fields
- `src/fast_mcp_agent/core/tokenizer.py` — replace tiktoken with xAI tokenizer
- `src/fast_mcp_agent/models.py` — update UsageStats parsing

### Light Modify (5)
- `src/fast_mcp_agent/core/agent.py` — update `settings.openrouter_model` refs
- `src/fast_mcp_agent/agents/orchestrator.py` — same
- `src/fast_mcp_agent/storage/memory.py` — update embed call if needed
- `pyproject.toml` — swap deps
- `.env.example` — new env vars

### Docs (3)
- `CLAUDE.md`, `README.md`, `MEMORY.md`

## Verification

```bash
uv run ruff check src/
uv run python -c "from fast_mcp_agent.mcp.server import mcp; print('Import OK')"
# Start server, verify it connects to xAI, run a chat request
```
