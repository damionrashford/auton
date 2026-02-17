import type { ResourceBudget } from "@/types/task/index.js";
import type { CoordinationTrigger } from "@/protocols/coordination/index.js";
import type { TaskMetrics, MonitoringThresholds } from "@/protocols/monitoring/types.js";

export function checkHealth(
  taskId: string,
  metrics: TaskMetrics | undefined,
  thresholds: MonitoringThresholds,
  budget: ResourceBudget | undefined,
  emitTrigger: (t: CoordinationTrigger) => void
): void {
  if (!metrics) return;

  const now = Date.now();

  if (now - metrics.lastHeartbeat > thresholds.heartbeatTimeout) {
    emitTrigger({
      type: "agent_unresponsive",
      severity: "warning",
      taskId,
      agentId: metrics.agentId,
      message: `Agent ${metrics.agentId} unresponsive for ${now - metrics.lastHeartbeat}ms`,
      timestamp: now,
    });
  }

  const recentErrors = metrics.events.filter(
    (e) => e.type === "error_occurred" && e.timestamp > now - 60_000
  ).length;
  if (recentErrors > thresholds.maxErrorRate) {
    emitTrigger({
      type: "error_rate_spike",
      severity: "warning",
      taskId,
      agentId: metrics.agentId,
      message: `Error rate spike: ${recentErrors} errors in last minute`,
      data: { errorRate: recentErrors },
      timestamp: now,
    });
  }

  if (budget) {
    if (budget.maxTokens && metrics.tokensUsed > 0) {
      const usage = metrics.tokensUsed / budget.maxTokens;
      if (usage >= thresholds.budgetCriticalThreshold) {
        emitTrigger({
          type: "budget_overrun",
          severity: "critical",
          taskId,
          message: `Token budget ${(usage * 100).toFixed(0)}% used`,
          data: { used: metrics.tokensUsed, budget: budget.maxTokens },
          timestamp: now,
        });
      } else if (usage >= thresholds.budgetWarningThreshold) {
        emitTrigger({
          type: "budget_overrun",
          severity: "warning",
          taskId,
          message: `Token budget ${(usage * 100).toFixed(0)}% used`,
          data: { used: metrics.tokensUsed, budget: budget.maxTokens },
          timestamp: now,
        });
      }
    }

    if (budget.maxCost && metrics.costIncurred > 0) {
      const costUsage = metrics.costIncurred / budget.maxCost;
      if (costUsage >= thresholds.budgetCriticalThreshold) {
        emitTrigger({
          type: "budget_overrun",
          severity: "critical",
          taskId,
          message: `Cost budget ${(costUsage * 100).toFixed(0)}% used`,
          data: { used: metrics.costIncurred, budget: budget.maxCost },
          timestamp: now,
        });
      }
    }
  }

  if (metrics.elapsedTime > thresholds.maxExecutionTime) {
    emitTrigger({
      type: "performance_degradation",
      severity: "warning",
      taskId,
      agentId: metrics.agentId,
      message: `Task exceeded max execution time (${metrics.elapsedTime}ms)`,
      timestamp: now,
    });
  }
}
