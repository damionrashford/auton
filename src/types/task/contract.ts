// Delegation contract, resource budget, permissions (§4.1, §4.7)

import type { SuccessCriterion } from "@/types/task/definition.js";

export interface DelegationContract {
  id: string;
  taskId: string;
  delegatorId: string;
  delegateeId: string;
  deliverables: string[];
  acceptanceCriteria: SuccessCriterion[];
  grantedPermissions: Permission[];
  budget: ResourceBudget;
  monitoringMode: MonitoringMode;
  autonomyLevel: AutonomyLevel;
  deadline?: number;
  escalationPolicy: EscalationPolicy;
  createdAt: number;
  status: "active" | "completed" | "violated" | "cancelled";
  compensationTerms?: string;
  renegotiationClause?: boolean;
  privacyClauses?: Record<string, unknown>;
}

export interface ResourceBudget {
  maxTokens?: number;
  maxCost?: number;
  maxDuration?: number;
  maxApiCalls?: number;
  maxDelegationDepth?: number;
}

export type MonitoringMode = "continuous" | "periodic" | "event_triggered" | "on_completion";

export type AutonomyLevel =
  | "atomic_execution"
  | "bounded_autonomy"
  | "guided_autonomy"
  | "open_delegation";

export interface EscalationPolicy {
  triggers: EscalationTrigger[];
  escalateTo: string;
  autoEscalateAfter?: number;
}

export interface EscalationTrigger {
  type: "timeout" | "budget_exceeded" | "quality_below" | "error_rate" | "permission_needed" | "stuck";
  threshold: number;
}

export interface Permission {
  id: string;
  resource: string;
  actions: string[];
  conditions?: PermissionCondition[];
  expiresAt?: number;
  delegatable: boolean;
  grantChain: string[];
}

export interface PermissionCondition {
  type: "time_window" | "rate_limit" | "approval_required" | "context_match" | "semantic";
  parameters: Record<string, unknown>;
}
