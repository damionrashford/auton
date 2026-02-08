# Agents

Multi-agent orchestrator-worker system. An orchestrator decomposes user requests and delegates to specialist agents, each with filtered tool access, focused prompts, and safety constraints.

## Architecture

```
User (Slack @mention or DM)
  → SlackBoltUI (Socket Mode)
    → OrchestratorAgent.run()
      → decompose_task() — LLM picks specialist agents (max 5 subtasks)
      → execute_tasks() — parallel/sequential delegation via asyncio.gather
        → Research Agent (RivalSearchMCP: 10 tools + Playwright read-only)
        → Browser Agent (Playwright: click, type, fill, scroll)
        → Communication Agent (Slack + Gmail + Google Chat)
        → Workspace Agent (Google Workspace: Calendar, Drive, Docs, Sheets, etc.)
        → Blockchain Agent (Coinbase AgentKit: wallets, DeFi, swaps, NFTs)
      → synthesize_results() — LLM combines specialist outputs
    → Reply in Slack thread
```

## Agent Roles

6 roles defined in `agents/roles.py` as `AgentRole` enum:

| Role | Description | Confirmation Required |
|------|-------------|----------------------|
| `ORCHESTRATOR` | Decomposes tasks and delegates to specialists | No |
| `RESEARCH` | Web search, social media, news, GitHub, scientific research, content analysis | No |
| `BROWSER` | Interactive browser automation (click, type, fill, scroll) | Yes |
| `COMMUNICATION` | Slack messaging, Gmail, Google Chat | Yes |
| `WORKSPACE` | Google Calendar, Drive, Docs, Sheets, Tasks | Yes |
| `BLOCKCHAIN` | Coinbase wallets, DeFi, swaps, NFTs, streaming, identity | Yes |

Each role has an `AgentConfig` with:
- `allowed_tool_patterns` / `denied_tool_patterns` — glob matching (`*` wildcards), denied overrides allowed
- `max_iterations_override` — per-role iteration limits
- `confirmation_callback` — optional Slack-native write-op approval
- `parent_conversation_id` / `delegation_context` — for multi-agent tracing

## Tool Access Patterns

Defined in `agents/registry.py`. Tool prefix conventions:

| Prefix | Source | Example |
|--------|--------|---------|
| *(none)* | RivalSearchMCP | `web_search`, `social_search`, `research_agent` |
| `pw_` | Playwright MCP | `pw_navigate`, `pw_click`, `pw_fill` |
| `gw_` | Google Workspace MCP | `gw_send_gmail_message`, `gw_create_event` |
| `slack_` | Internal Slack | `slack_send_message`, `slack_upload_file` |
| `cb_` | Internal Blockchain | `cb_get_wallet_details`, `cb_trade` |
| `webhook_` | Internal Webhooks | `webhook_send`, `webhook_get`, `webhook_create_subscription` |
| `cron_` | Internal Scheduler | `cron_create_job`, `cron_delete_job` |
| `memory_` | Internal Memory | `memory_store`, `memory_recall`, `memory_forget` |
| `delegate_to_*` | Internal Delegation | `delegate_to_research`, `delegate_to_browser` |

### Per-Role Access

**ORCHESTRATOR** — `delegate_to_*`, `memory_recall`

**RESEARCH** — 10 RivalSearchMCP tools, 3 Playwright read-only (`pw_navigate`, `pw_snapshot`, `pw_screenshot`), `memory_store`, `memory_recall`. Denied: `pw_click`, `pw_type`, `pw_fill`, `slack_*`, `gw_*`, `cron_*`, `delegate_to_*`

**BROWSER** — `pw_*`, `browser_*`, `memory_store`. Denied: all RivalSearchMCP, `slack_*`, `gw_*`, `cron_*`, `delegate_to_*`

**COMMUNICATION** — `slack_*`, `webhook_*`, 6 Gmail tools, 4 Google Chat tools, `memory_store`, `memory_recall`. Denied: `pw_*`, `browser_*`, all RivalSearchMCP, `cron_*`, `delegate_to_*`

**WORKSPACE** — `gw_*`, `memory_store`, `memory_recall`. Denied: `pw_*`, `browser_*`, all RivalSearchMCP, `slack_*`, `cron_*`, `delegate_to_*`

**BLOCKCHAIN** — `cb_*`, `memory_store`, `memory_recall`. Denied: everything else

## Orchestrator Flow

`OrchestratorAgent` in `agents/orchestrator.py` has 3 phases:

### Phase 1: Decompose (`decompose_task()`)
LLM analyzes request and outputs a JSON array of subtasks:
```json
[{"target_role": "RESEARCH", "instruction": "...", "context": "...", "parallel": true}]
```
- Maximum 5 subtasks per decomposition
- Empty array = simple request → falls back to Research Agent directly

### Phase 2: Execute (`execute_tasks()`)
- Parallel tasks run via `asyncio.gather()`
- Sequential tasks run one by one
- Each task spawns a specialist agent via `run_agent(agent_config=...)`

### Phase 3: Synthesize (`synthesize_results()`)
- LLM combines specialist results into a unified response
- Cites which specialist provided which information
- Fallback: concatenates raw results if synthesis fails

### Research Prompts
Orchestrator fetches guided workflows from RivalSearchMCP via `bridge.get_prompt()`:
- `comprehensive_research(topic, depth)`
- `multi_source_search(query, include_social, include_news)`
- `deep_content_analysis(url, extract_documents)`
- `academic_literature_review(research_question, max_papers)`

Prompt selection is context-aware (academic, URL, social, news keywords).

## Delegation

5 delegation tools in `agents/tools.py` (orchestrator-only):

| Tool | Target Role |
|------|------------|
| `delegate_to_research` | `AgentRole.RESEARCH` |
| `delegate_to_browser` | `AgentRole.BROWSER` |
| `delegate_to_communication` | `AgentRole.COMMUNICATION` |
| `delegate_to_workspace` | `AgentRole.WORKSPACE` |
| `delegate_to_blockchain` | `AgentRole.BLOCKCHAIN` |

Max delegation depth controlled by `multi_agent_max_delegation_depth` config.

## Prompts

7 prompt constants in `agents/prompts.py`:

| Constant | Role | Lines |
|----------|------|-------|
| `ORCHESTRATOR_PROMPT` | Orchestrator | ~105 |
| `RESEARCH_AGENT_PROMPT` | Research | ~40 |
| `BROWSER_AGENT_PROMPT` | Browser | ~15 |
| `COMMUNICATION_AGENT_PROMPT` | Communication | ~42 |
| `WORKSPACE_AGENT_PROMPT` | Workspace | ~44 |
| `BLOCKCHAIN_AGENT_PROMPT` | Blockchain | ~56 |
| `_SLACK_FORMAT_BLOCK` | All (appended) | ~12 |

`get_system_prompt(role: AgentRole) -> str` returns the role-specific prompt.

## Safety & Confirmation

3-tier confirmation system in `core/safety.py`:

1. **Explicit write tools** — `WRITE_TOOLS` frozenset (38 tools): Slack send/upload/react/topic/invite/kick/archive, Cron create/delete, Memory forget, 12 Google Workspace tools
2. **Google Workspace pattern** — `gw_*` tools matched against `_GW_DANGEROUS_KEYWORDS` frozenset: create, delete, update, send, share, move, modify, batch, transfer, remove, import, manage, clear, draft, run, set_publish
3. **Blockchain unconditional** — ALL `cb_*` tools require confirmation, no exceptions

Confirmation paths:
- **Path A:** MCP `ctx.elicit()` — structured confirmation dialog
- **Path B:** Slack callback — thread-based yes/no polling (60s timeout, defaults to deny)
- **Path C:** Block — if no confirmation mechanism is available

## Agent Loop (`core/agent.py`)

928-line agentic loop. Each `run_agent()` iteration:

1. **Memory recall** — semantic search via pgvector
2. **Planning** — multi-step plan for complex requests (>100 chars)
3. **LLM call** — xAI SDK with filtered tool schemas per agent role
4. **Tool execution** — parallel for independent, sequential for browser/duplicates
5. **Self-correction** — single retry, stuck-loop detection (same tool+args), strategy injection after 3+ failures
6. **Context management** — token counting via tiktoken, LLM summarization compaction
7. **Guardrails** — cost/token per conversation, max iterations, daily cost limit

Loop terminates when the LLM says "stop" or `max_iterations` is reached.

## Iteration Limits

Configured per role in `config.py`:

| Config Field | Default | Role |
|-------------|---------|------|
| `multi_agent_orchestrator_max_iterations` | — | Orchestrator |
| `multi_agent_research_max_iterations` | — | Research |
| `multi_agent_browser_max_iterations` | — | Browser |
| `multi_agent_communication_max_iterations` | — | Communication |
| `multi_agent_workspace_max_iterations` | — | Workspace |
| `multi_agent_blockchain_max_iterations` | — | Blockchain |

## Adding a New Agent

Follow this recipe (same pattern used for Slack, Blockchain):

1. Create `src/auton/<name>/` package with `client.py` (SDK wrapper) and `tools.py` (tool schemas + handler)
2. Add `AgentRole.<NAME>` to `agents/roles.py`
3. Add registry config in `agents/registry.py` with `allowed_tool_patterns` and `denied_tool_patterns`
4. Add `<NAME>_AGENT_PROMPT` to `agents/prompts.py` and register in `get_system_prompt()`
5. Add `delegate_to_<name>` to `agents/tools.py` DELEGATION_TOOLS + _ROLE_MAP
6. Update orchestrator prompt and decomposition prompt in `agents/prompts.py` and `agents/orchestrator.py`
7. Add safety rules in `core/safety.py`
8. Add config fields in `config.py`
9. Initialize in `mcp/server.py` lifespan (conditional on config)
10. Add dependency to `pyproject.toml` and env vars to `.env.example`
