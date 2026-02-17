# Getting Started

## Installation

```bash
npm install auton
```

**Requirements:** Node.js ≥ 18

## Minimal Example

```typescript
import {
  createDelegationFramework,
  type AgentProfile,
} from "auton";

const agent: AgentProfile = {
  id: "agent-1",
  name: "Assistant",
  type: "ai",
  capabilities: [{ name: "general", proficiency: 0.9 }],
  tools: [],
  basePermissions: [],
  maxAutonomyLevel: "bounded_autonomy",
  preferredMonitoringMode: "continuous",
  trustScore: 0.5,
  reputation: {
    totalCompleted: 0,
    totalFailed: 0,
    successRate: 0.5,
    avgQuality: 0.5,
    avgResponseTime: 0,
    onTimeRate: 1,
    violations: 0,
    webOfTrustScore: 0.5,
    consistency: 0.5,
    domainScores: {},
    lastUpdated: Date.now(),
  },
  canDelegate: false,
  maxDelegationDepth: 0,
  domains: [],
  status: "available",
  metadata: {},
  modelConfig: {
    model: "gpt-4o",
    baseURL: "https://api.openai.com/v1",
    apiKey: process.env.OPENAI_API_KEY!,
  },
};

const { agentLoop } = createDelegationFramework({
  agent,
  enableMonitoring: true,
});

const result = await agentLoop.run({
  id: "task-1",
  description: "Summarize the key points of intelligent delegation.",
  objective: {
    expectedOutput: "A concise summary",
    successCriteria: [{ metric: "length", operator: "gte", target: 100, weight: 0.5 }],
    verificationMethod: "direct_inspection",
  },
  characteristics: {
    complexity: "simple",
    criticality: "low",
    uncertainty: "low",
    verifiability: "measurable",
    reversibility: "fully_reversible",
  },
  priority: "normal",
  status: "pending",
  subtaskIds: [],
  dependencyIds: [],
  requiredPermissions: [],
  createdAt: Date.now(),
  updatedAt: Date.now(),
  tags: [],
});

console.log(result.success, result.output);
```

## Full Orchestration

For multi-agent delegation with decomposition, assignment, and verification:

```typescript
import {
  DelegationExecutor,
  TrustReputationManager,
} from "auton";

const executor = new DelegationExecutor({
  candidates: [agent1, agent2, agent3],
  delegator: orchestratorAgent,
  toolExecutor: myToolHandlers,
  trustManager: new TrustReputationManager(),
  decompositionClient: new AIClient({ baseURL, apiKey }),
  verifierClient: new AIClient({ baseURL, apiKey }),
  decomposeFirst: true,
  complexityFloor: {
    maxCriticalityToBypass: "low",
    maxUncertaintyToBypass: "low",
    maxDurationMsToBypass: 60_000,
  },
});

const result = await executor.execute(task);
```

## Next Steps

- [Architecture Overview](./architecture.md) — Understand the delegation lifecycle
- [Agent Loop](./core/agent-loop.md) — Configure tools, budgets, monitoring
- [Executor](./core/executor.md) — Full pipeline configuration
