import type {
  CoordinationTrigger,
  CoordinationAction,
  CoordinationRule,
  CoordinationContext,
  CoordinatorStabilityConfig,
} from "@/protocols/coordination/types.js";
import { createDefaultRules } from "@/protocols/coordination/rules.js";

export type {
  ExternalTriggerType,
  InternalTriggerType,
  TriggerType,
  CoordinationTrigger,
  CoordinationAction,
  CoordinationRule,
  CoordinationContext,
  CoordinatorStabilityConfig,
} from "@/protocols/coordination/types.js";

export class AdaptiveCoordinator {
  private rules: CoordinationRule[] = [];
  private triggerHistory: CoordinationTrigger[] = [];
  private listeners: Array<(action: CoordinationAction) => void> = [];
  private context: CoordinationContext;
  private lastReassignment: Map<string, number> = new Map();
  private reassignmentCountInWindow: Map<string, number> = new Map();
  private reassignmentWindowStart: number = Date.now();
  private stability: Required<CoordinatorStabilityConfig>;

  constructor(stabilityConfig?: CoordinatorStabilityConfig) {
    this.stability = {
      cooldownMs: stabilityConfig?.cooldownMs ?? 30_000,
      maxReassignmentsPerHour: stabilityConfig?.maxReassignmentsPerHour ?? 5,
    };

    this.context = {
      tasks: new Map(),
      agents: new Map(),
      activeAssignments: new Map(),
      triggerHistory: this.triggerHistory,
      lastReassignment: this.lastReassignment,
      reassignmentCountInWindow: this.reassignmentCountInWindow,
      reassignmentWindowStart: this.reassignmentWindowStart,
    };

    for (const rule of createDefaultRules()) this.rules.push(rule);
  }

  private canReassign(taskId: string): boolean {
    const now = Date.now();
    const last = this.lastReassignment.get(taskId);
    if (last && now - last < this.stability.cooldownMs) return false;

    const hourMs = 60 * 60 * 1000;
    if (now - this.reassignmentWindowStart > hourMs) {
      this.reassignmentWindowStart = now;
      this.reassignmentCountInWindow.clear();
    }
    const count = this.reassignmentCountInWindow.get(taskId) ?? 0;
    if (count >= this.stability.maxReassignmentsPerHour) return false;

    return true;
  }

  recordReassignment(taskId: string): void {
    this.lastReassignment.set(taskId, Date.now());
    this.reassignmentCountInWindow.set(
      taskId,
      (this.reassignmentCountInWindow.get(taskId) ?? 0) + 1
    );
  }

  processTrigger(trigger: CoordinationTrigger): CoordinationAction[] {
    this.triggerHistory.push(trigger);
    const severityLevel = { info: 0, warning: 1, critical: 2 };

    const matchingRules = this.rules
      .filter(
        (r) =>
          r.enabled &&
          r.triggerTypes.includes(trigger.type) &&
          severityLevel[trigger.severity] >= severityLevel[r.minSeverity] &&
          r.condition(trigger, this.context)
      )
      .sort((a, b) => b.priority - a.priority);

    const allActions: CoordinationAction[] = [];

    for (const rule of matchingRules) {
      const actions = rule.actions(trigger, this.context);
      for (const action of actions) {
        if (action.type === "reassign" && action.taskId) {
          if (!this.canReassign(action.taskId)) continue;
          this.recordReassignment(action.taskId);
        }
        allActions.push(action);
      }
    }

    for (const action of allActions) {
      for (const listener of this.listeners) listener(action);
    }

    return allActions;
  }

  addRule(rule: CoordinationRule): void {
    this.rules.push(rule);
  }

  onAction(listener: (action: CoordinationAction) => void): () => void {
    this.listeners.push(listener);
    return () => {
      const idx = this.listeners.indexOf(listener);
      if (idx >= 0) this.listeners.splice(idx, 1);
    };
  }

  updateContext(updates: Partial<CoordinationContext>): void {
    if (updates.tasks) this.context.tasks = updates.tasks;
    if (updates.agents) this.context.agents = updates.agents;
    if (updates.activeAssignments) this.context.activeAssignments = updates.activeAssignments;
  }

  getRecentTriggers(since: number): CoordinationTrigger[] {
    return this.triggerHistory.filter((t) => t.timestamp >= since);
  }

  checkDeadlines(): CoordinationTrigger[] {
    const triggers: CoordinationTrigger[] = [];
    const now = Date.now();

    for (const [, task] of this.context.tasks) {
      if (
        task.status === "in_progress" &&
        task.deadline &&
        task.characteristics.estimatedDuration
      ) {
        const estimatedEnd = (task.startedAt ?? now) + task.characteristics.estimatedDuration;
        if (estimatedEnd > task.deadline) {
          const trigger: CoordinationTrigger = {
            type: "deadline_at_risk",
            severity: estimatedEnd > task.deadline * 1.2 ? "critical" : "warning",
            taskId: task.id,
            message: `Task ${task.id} estimated to miss deadline`,
            timestamp: now,
          };
          triggers.push(trigger);
          this.processTrigger(trigger);
        }
      }
    }

    return triggers;
  }
}
