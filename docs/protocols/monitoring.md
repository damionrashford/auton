# Monitoring

Continuous, periodic, and event-triggered monitoring of task execution (§4.5). Tracks performance metrics, detects anomalies, and feeds the Adaptive Coordinator.

## Modes

| Mode | Description |
|------|--------------|
| `continuous` | Health check every 5s |
| `periodic` | Health check every 30s |
| `event_triggered` | No interval; events only |
| `on_completion` | No active checks |

## Usage

```typescript
import { Monitor } from "auton";

const monitor = new Monitor(
  {
    heartbeatTimeout: 30_000,
    maxErrorRate: 5,
    budgetWarningThreshold: 0.8,
    budgetCriticalThreshold: 0.95,
    minQualityScore: 0.5,
    maxExecutionTime: 600_000,
  },
  (trigger) => coordinator.processTrigger(trigger)
);

monitor.startMonitoring(taskId, agentId, "continuous", budget);

// Record events (typically from AgentLoop)
monitor.recordEvent(taskId, agentId, "tool_called", { toolName: "search" });
monitor.recordEvent(taskId, agentId, "token_usage", { tokens: 150 });
monitor.recordEvent(taskId, agentId, "task_completed", { success: true, output: "..." });

monitor.heartbeat(taskId);  // Agent signals alive

monitor.stopMonitoring(taskId);
monitor.dispose();  // Cleanup all
```

## Event Types

- `task_started`, `task_progress`, `task_completed`, `task_failed`
- `tool_called`, `delegation_created`
- `token_usage`, `cost_incurred`
- `error_occurred`, `heartbeat`, `checkpoint`

## Triggers Emitted

When thresholds are exceeded, the monitor emits `CoordinationTrigger`:

- **agent_unresponsive** — No heartbeat within `heartbeatTimeout`
- **error_rate_spike** — Too many errors in last minute
- **budget_overrun** — Token or cost budget exceeded (warning/critical)
- **performance_degradation** — Exceeded `maxExecutionTime`

## Task Metrics

```typescript
interface TaskMetrics {
  taskId: string;
  agentId: string;
  elapsedTime: number;
  tokensUsed: number;
  costIncurred: number;
  toolCalls: number;
  errorCount: number;
  delegationCount: number;
  progress: number;
  lastHeartbeat: number;
  events: MonitoringEvent[];
}
```

## See Also

- [Adaptive Coordination](./coordination.md) — Consumes triggers
- [Agent Loop](../core/agent-loop.md) — Integrates with Monitor
