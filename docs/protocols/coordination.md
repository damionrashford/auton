# Adaptive Coordination

Dynamic replanning based on internal and external triggers (§4.4). Implements Monitor → Detect → Evaluate → Replan → Execute.

## Trigger Types

**External:** `task_change`, `resource_change`, `priority_change`, `security_alert`, `environment_change`

**Internal:** `performance_degradation`, `budget_overrun`, `verification_failure`, `agent_unresponsive`, `deadline_at_risk`, `error_rate_spike`

## Coordination Actions

- `reassign` — Move task to different agent
- `replan` — Re-decompose or adjust plan
- `escalate` — Escalate to delegator
- `pause`, `resume`, `cancel`
- `adjust_budget`, `adjust_priority`
- `add_monitoring` — Increase monitoring level
- `notify` — Send message to recipients

## Usage

```typescript
import { AdaptiveCoordinator } from "auton";

const coordinator = new AdaptiveCoordinator({
  cooldownMs: 30_000,
  maxReassignmentsPerHour: 5,
});

// Update context
coordinator.updateContext({
  tasks: taskMap,
  agents: agentMap,
  activeAssignments: assignmentMap,
});

// Process trigger (from Monitor, SecurityManager, etc.)
const actions = coordinator.processTrigger({
  type: "budget_overrun",
  severity: "critical",
  taskId: "task-1",
  message: "Token budget 95% used",
  timestamp: Date.now(),
});

// Listen for actions
const unsubscribe = coordinator.onAction((action) => {
  if (action.type === "reassign") { /* ... */ }
});

// Check deadlines
const triggers = coordinator.checkDeadlines();
```

## Default Rules

- **Agent unresponsive** → Reassign or escalate (reversibility-aware)
- **Verification failure** → Replan or escalate (reversibility-aware)
- **Budget overrun** → Escalate
- **Security alert (critical)** → Pause affected tasks
- **Performance degradation** → Add continuous monitoring
- **Deadline at risk** → Adjust priority, escalate if critical

## Stability

- **Cooldown** — Min time between reassignments for same task
- **Damping** — Max reassignments per task per hour

## See Also

- [Monitoring](./monitoring.md) — Emits triggers
- [Security](./security.md) — Emits security_alert
- [Executor](../core/executor.md) — Wires coordinator to monitor/security
