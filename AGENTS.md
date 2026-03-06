# AGENTS.md

## Project

**auton** — autonomous AI agent. Two files that matter: `agent.js` (core loop, tools, MCP, skills) and `comms.js` (Slack/Telegram/WhatsApp bridge). No build step. No dependencies beyond Node.js 18+.

## Files

| File | Role |
|---|---|
| `agent.js` | Core agent — LLM loop, built-in tools, MCP client, skill loader |
| `comms.js` | Messaging bridge — imports and wraps `agent.js` |
| `config.json` | User config — `llm`, `agent`, `slack`, `telegram`, `whatsapp` |
| `state.json` | Runtime state — auto-created, auto-saved. Do not commit. |

## Running

```bash
node agent.js "do something"   # one-shot task
node agent.js                  # daemon mode (checks goals/schedules every 30s)
node comms.js                  # messaging bridge (Slack + Telegram + WhatsApp)
```

## Architecture

- **No npm packages.** Keep it that way. Use Node built-ins and native `fetch`.
- `config.json` values take priority over environment variables (`API_KEY`, `API_URL`, `MODEL`).
- State (`S`) is a single in-memory object. Call `save()` after any mutation.
- The agent loop (`loop()`) runs up to `maxTurns` tool calls before stopping.
- Tools are defined in the `tools` object in `agent.js`. Each has `desc`, `params`/`schema`, and `fn`.

## Adding a built-in tool

Add an entry to the `tools` object:

```js
tools.my_tool = {
  desc: 'One line description',
  params: {
    input: { type: 'string', description: 'The input value' }
  },
  fn: ({ input }) => {
    return 'result'
  }
}
```

Required fields are inferred from `params` — any param whose description does not include `"optional"` is required.

## MCP

MCP connections are established at startup from `S.mcp` (persisted in `state.json`) and optionally from the `MCP_SERVERS` env var. Each connected server's tools are registered into `tools` as `servername__toolname`.

## Skills

Skills are discovered from `./skills/` (project-level) and `~/.agents/skills/` (user-level). Each skill is a directory with a `SKILL.md` that has a YAML frontmatter `name` and `description`. Project-level skills shadow user-level skills with the same name.

## Conventions

- `comms.js` must not contain agent logic — it delegates everything to `agent.loop()`.
- Long tool output is truncated to 8000 chars before being sent back to the LLM (50000 for skill activation).
- The system prompt is rebuilt on every `loop()` call — it reflects current goals, memory, schedule, and MCP connections live.
