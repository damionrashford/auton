# Executor

Full orchestration pipeline that implements the complete delegation lifecycle: Complexity Floor → Decompose → Assign → Contract → Execute → Verify → Trust.

## Overview

The `DelegationExecutor`:

1. **Complexity floor** — Bypasses full pipeline for trivial, low-criticality, low-uncertainty tasks
2. **Decomposition** — Optionally decomposes with AI before assignment
3. **Assignment** — Selects best agent from candidates
4. **Contract** — Creates delegation contract with budget, permissions
5. **Delegate** — Records in chain, attenuates permissions
6. **Execute** — Runs agent loop with monitor and security
7. **Verify** — Validates result against success criteria
8. **Trust** — Records completion in trust ledger

## Usage

```typescript
import {
  DelegationExecutor,
  shouldBypassDelegation,
  TrustReputationManager,
  AIClient,
} from "auton";

const aiClient = new AIClient({ baseURL, apiKey });

const executor = new DelegationExecutor({
  candidates: [agent1, agent2, agent3],
  delegator: orchestratorAgent,
  toolExecutor: myTools,
  trustManager: new TrustReputationManager(),
  decompositionClient: aiClient,
  verifierClient: aiClient,
  decomposeFirst: true,
  complexityFloor: {
    maxCriticalityToBypass: "low",
    maxUncertaintyToBypass: "low",
    maxDurationMsToBypass: 60_000,
  },
  defaultBudget: { maxTokens: 100_000, maxDuration: 300_000 },
  onCoordinationTrigger: (t) => console.log("Trigger:", t),
});

const result = await executor.execute(task);

// Access coordinator and chain manager for advanced usage
const coordinator = executor.getCoordinator();
const chainManager = executor.getChainManager();
```

## Configuration

| Option | Type | Description |
|--------|------|-------------|
| `candidates` | AgentProfile[] | Agents available for assignment |
| `delegator` | AgentProfile | Orchestrator (usually human proxy) |
| `toolExecutor` | ToolExecutor | Tool handlers for executing agent |
| `decompositionClient` | AIClient | For AI-assisted decomposition |
| `trustManager` | TrustReputationManager | Records completions |
| `verifierClient` | AIClient | For LLM-based verification |
| `complexityFloor` | ComplexityFloorConfig | Bypass thresholds |
| `decomposeFirst` | boolean | Decompose before assignment |
| `defaultBudget` | ResourceBudget | Default contract budget |
| `onCoordinationTrigger` | (t) => void | Callback for triggers |

## Complexity Floor

When a task is **trivial** and below thresholds, the executor bypasses decomposition and uses a simple assign-and-run path:

```typescript
shouldBypassDelegation(task, {
  maxCriticalityToBypass: "low",
  maxUncertaintyToBypass: "low",
  maxDurationMsToBypass: 60_000,
});
```

## Decomposition Flow

When `decomposeFirst` is true and `decompositionClient` is set:

- Task is decomposed via LLM into subtasks
- If multiple subtasks, the first is executed (full recursive execution can be layered on top)

## See Also

- [Architecture](../architecture.md) — Lifecycle diagram
- [Task Decomposition](../protocols/task-decomposition.md) — Decomposition strategies
- [Task Assignment](../protocols/task-assignment.md) — Scoring and ranking
