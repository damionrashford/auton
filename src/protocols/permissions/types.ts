import type { Permission, PermissionCondition } from "@/types/task/index.js";

export interface PermissionRequest {
  requesterId: string;
  resource: string;
  actions: string[];
  reason: string;
  duration?: number;
  needsDelegation: boolean;
}

export interface PermissionDecision {
  granted: boolean;
  permission?: Permission;
  reason: string;
  approvedActions?: string[];
}

export interface PermissionPolicy {
  resourcePattern: string;
  allowedActions: string[];
  grantableToTypes: ("human" | "ai")[];
  maxDuration?: number;
  delegatable: boolean;
  requiredConditions?: PermissionCondition[];
  maxDelegationDepth: number;
}

export interface PermissionAuditEntry {
  agentId: string;
  resource: string;
  actions: string[];
  granted: boolean;
  reason: string;
  timestamp: number;
}
