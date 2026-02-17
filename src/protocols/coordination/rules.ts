import type { CoordinationRule } from "@/protocols/coordination/types.js";

export function createDefaultRules(): CoordinationRule[] {
  return [
    {
      id: "agent_unresponsive_reassign",
      triggerTypes: ["agent_unresponsive"],
      minSeverity: "warning",
      condition: (trigger) => !!trigger.agentId,
      actions: (trigger, context) => {
        const affectedTasks = Array.from(context.activeAssignments.entries())
          .filter(([, agentId]) => agentId === trigger.agentId)
          .map(([taskId]) => taskId);

        const actions: ReturnType<CoordinationRule["actions"]> = [];
        for (const taskId of affectedTasks) {
          const task = context.tasks.get(taskId);
          const irreversible = task?.characteristics.reversibility === "irreversible";
          const critical = task?.characteristics.criticality === "critical";

          if (irreversible && critical) {
            actions.push({
              type: "escalate",
              taskId,
              escalateTo: task?.delegatorId ?? "system",
              reason: `Irreversible critical task: agent unresponsive — escalate instead of reassign`,
            });
          } else {
            actions.push({
              type: "reassign",
              taskId,
              fromAgentId: trigger.agentId!,
            });
          }
        }
        return actions;
      },
      priority: 90,
      enabled: true,
    },
    {
      id: "verification_failure_replan",
      triggerTypes: ["verification_failure"],
      minSeverity: "warning",
      condition: (trigger) => !!trigger.taskId,
      actions: (trigger, context) => {
        const task = trigger.taskId ? context.tasks.get(trigger.taskId) : undefined;
        const irreversible = task?.characteristics.reversibility === "irreversible";
        const critical = task?.characteristics.criticality === "critical";

        if (irreversible && critical) {
          return [
            {
              type: "escalate",
              taskId: trigger.taskId!,
              escalateTo: task?.delegatorId ?? "system",
              reason: `Verification failed on irreversible critical task: ${trigger.message}`,
            },
          ];
        }
        return [{ type: "replan", taskId: trigger.taskId!, reason: trigger.message }];
      },
      priority: 80,
      enabled: true,
    },
    {
      id: "budget_overrun_escalate",
      triggerTypes: ["budget_overrun"],
      minSeverity: "warning",
      condition: (trigger) => !!trigger.taskId,
      actions: (trigger, context) => {
        const task = trigger.taskId ? context.tasks.get(trigger.taskId) : undefined;
        const delegatorId = task?.delegatorId ?? "system";
        return [
          {
            type: "escalate",
            taskId: trigger.taskId!,
            escalateTo: delegatorId,
            reason: `Budget overrun: ${trigger.message}`,
          },
        ];
      },
      priority: 70,
      enabled: true,
    },
    {
      id: "security_alert_pause",
      triggerTypes: ["security_alert"],
      minSeverity: "critical",
      condition: () => true,
      actions: (trigger, context) => {
        if (trigger.taskId) {
          return [{ type: "pause", taskId: trigger.taskId, reason: trigger.message }];
        }
        return Array.from(context.tasks.keys()).map((taskId) => ({
          type: "pause" as const,
          taskId,
          reason: `Security alert: ${trigger.message}`,
        }));
      },
      priority: 100,
      enabled: true,
    },
    {
      id: "perf_degradation_monitor",
      triggerTypes: ["performance_degradation"],
      minSeverity: "info",
      condition: (trigger) => !!trigger.taskId,
      actions: (trigger) => [
        { type: "add_monitoring", taskId: trigger.taskId!, mode: "continuous" },
      ],
      priority: 50,
      enabled: true,
    },
    {
      id: "deadline_risk_escalate",
      triggerTypes: ["deadline_at_risk"],
      minSeverity: "warning",
      condition: (trigger) => !!trigger.taskId,
      actions: (trigger, context) => {
        const actions: ReturnType<CoordinationRule["actions"]> = [
          { type: "adjust_priority", taskId: trigger.taskId!, newPriority: "critical" },
        ];
        if (trigger.severity === "critical") {
          const task = context.tasks.get(trigger.taskId!);
          actions.push({
            type: "escalate",
            taskId: trigger.taskId!,
            escalateTo: task?.delegatorId ?? "system",
            reason: trigger.message,
          });
        }
        return actions;
      },
      priority: 75,
      enabled: true,
    },
  ];
}
