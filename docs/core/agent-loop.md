# Agent Loop

Execution engine that runs the LLM agent loop with tool calling, parallel tool execution, and optional integration with Monitoring, Security, and Adaptive Coordination.

## Overview

The agent loop:

1. Builds a system prompt from the task and agent config
2. Sends the task to the LLM
3. If the model returns tool calls, executes them (with optional security validation)
4. Feeds tool results back to the model
5. Repeats until the model returns a final response or max iterations / budget exceeded

## Usage

```typescript
import {
  AgentLoop,
  createAgentLoop,
  type ToolExecutor,
  type ToolHandler,
} from "auton";

const toolExecutor: ToolExecutor = {
  get_weather: (async (args) => {
    const loc = args.location as string;
    return JSON.stringify({ temp: 72, location: loc });
  }) as ToolHandler,
};

const loop = createAgentLoop({
  agent: myAgentProfile,
  toolExecutor,
  monitor: myMonitor,
  securityManager: mySecurityManager,
  maxIterations: 20,
  parallelToolCalls: true,
  budget: { maxTokens: 10_000, maxDuration: 60_000 },
});

const result = await loop.run(task);
```

## Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `agent` | AgentProfile | — | Agent executing the task |
| `toolExecutor` | ToolExecutor | — | Map of tool name → handler |
| `monitor` | Monitor | — | Emits task_started, tool_called, token_usage, task_completed |
| `securityManager` | SecurityManager | — | Validates tool calls before execution |
| `maxIterations` | number | `20` | Max LLM → tools → LLM cycles |
| `parallelToolCalls` | boolean | `true` | Execute tool calls in parallel |
| `signal` | AbortSignal | — | Cancel execution |
| `budget` | ResourceBudget | — | Enforce token/duration limits |

## Tool Handler

```typescript
type ToolHandler = (args: Record<string, unknown>) => Promise<string> | string;
type ToolExecutor = Record<string, ToolHandler>;
```

Handlers receive parsed JSON arguments and return a string (or JSON string). Errors are caught and returned as `{ error: "message" }` to the model.

## System Prompt

The loop builds a prompt that includes:

- Task description, objective, priority, tags
- Task characteristics (reversibility, contextuality, subjectivity)
- Delegation guidelines from the paper:
  - **Zone of indifference** — Reject unclear or unsafe instructions
  - **Authority gradient** — State concerns before blind compliance

## Budget Enforcement

When `budget` is provided:

- **maxTokens** — Stops when total tokens exceed the limit
- **maxDuration** — Stops when elapsed time exceeds the limit

## See Also

- [Executor](./executor.md) — Uses AgentLoop for full orchestration
- [Monitoring](../protocols/monitoring.md) — Event types and thresholds
- [Security](../protocols/security.md) — Tool validation rules
