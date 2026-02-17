import type { Task } from "@/types/task/index.js";
import type { AgentProfile } from "@/types/agent.js";

export type ExternalTriggerType =
  | "task_change"
  | "resource_change"
  | "priority_change"
  | "security_alert"
  | "environment_change";

export type InternalTriggerType =
  | "performance_degradation"
  | "budget_overrun"
  | "verification_failure"
  | "agent_unresponsive"
  | "deadline_at_risk"
  | "error_rate_spike";

export type TriggerType = ExternalTriggerType | InternalTriggerType;

export interface CoordinationTrigger {
  type: TriggerType;
  severity: "info" | "warning" | "critical";
  taskId?: string;
  agentId?: string;
  message: string;
  data?: unknown;
  timestamp: number;
}

export type CoordinationAction =
  | { type: "reassign"; taskId: string; fromAgentId: string; toAgentId?: string }
  | { type: "replan"; taskId: string; reason: string }
  | { type: "escalate"; taskId: string; escalateTo: string; reason: string }
  | { type: "pause"; taskId: string; reason: string }
  | { type: "resume"; taskId: string }
  | { type: "cancel"; taskId: string; reason: string }
  | { type: "adjust_budget"; taskId: string; newBudget: Record<string, number> }
  | { type: "adjust_priority"; taskId: string; newPriority: Task["priority"] }
  | { type: "add_monitoring"; taskId: string; mode: string }
  | { type: "notify"; message: string; recipients: string[] };

export interface CoordinationRule {
  id: string;
  triggerTypes: TriggerType[];
  minSeverity: "info" | "warning" | "critical";
  condition: (trigger: CoordinationTrigger, context: CoordinationContext) => boolean;
  actions: (trigger: CoordinationTrigger, context: CoordinationContext) => CoordinationAction[];
  priority: number;
  enabled: boolean;
}

export interface CoordinationContext {
  tasks: Map<string, Task>;
  agents: Map<string, AgentProfile>;
  activeAssignments: Map<string, string>;
  triggerHistory: CoordinationTrigger[];
  lastReassignment?: Map<string, number>;
  reassignmentCountInWindow?: Map<string, number>;
  reassignmentWindowStart?: number;
}

export interface CoordinatorStabilityConfig {
  cooldownMs?: number;
  maxReassignmentsPerHour?: number;
}
