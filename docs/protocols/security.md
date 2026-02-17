# Security

Threat detection, mitigation, and defense (§4.9). Implements rules for malicious delegatee, delegator, and ecosystem-level threats.

## Threat Categories

| Category | Examples |
|----------|----------|
| Malicious delegatee | Data exfiltration, poisoning, verification subversion, resource exhaustion, unauthorized access |
| Malicious delegator | Harmful delegation, prompt injection, model extraction, reputation sabotage |
| Ecosystem | Sybil attack, collusion, agent trap, agentic virus, protocol exploitation |

## Usage

```typescript
import { SecurityManager } from "auton";

const security = new SecurityManager((trigger) => {
  coordinator.processTrigger(trigger);
});

// Scan context
const detections = security.scan({
  task,
  agent,
  recentToolCalls: [...],
  recentDelegations: [...],
  resourceUsage: { agentId, tokensUsed, apiCalls, ... },
  allAgents: [...],
});

// Validate tool call before execution
const threat = security.validateToolCall(agentId, toolName, args, permissions);
if (threat) {
  // Block execution, return error to model
}

// Custom rule
security.addRule({
  id: "custom",
  name: "Custom Rule",
  description: "...",
  detectsThreats: ["data_exfiltration"],
  check: (ctx) => { /* return ThreatDetection or null */ },
  enabled: true,
});
```

## Default Rules

1. **Resource exhaustion** — >60 API calls/min or >100k tokens/min
2. **Unauthorized access** — Agent accessing resources outside base permissions
3. **Sybil detection** — 3+ agents with identical capability profiles
4. **Delegation depth** — >5 delegations for same task (agent trap)
5. **Data exfiltration** — Tool calls with suspicious external URLs/patterns

## Tool Call Validation

Validates arguments for prompt injection patterns (e.g., "ignore previous instructions", "system: you are", "sudo", "rm -rf", SQL injection patterns).

## Threat Detection

```typescript
interface ThreatDetection {
  id: string;
  threatType: ThreatType;
  category: ThreatCategory;
  severity: "low" | "medium" | "high" | "critical";
  agentId?: string;
  taskId?: string;
  description: string;
  evidence: unknown[];
  timestamp: number;
  mitigated: boolean;
}
```

## See Also

- [Agent Loop](../core/agent-loop.md) — Integrates SecurityManager for tool validation
- [Coordination](./coordination.md) — Receives security_alert triggers
