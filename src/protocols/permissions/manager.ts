import type { Permission } from "@/types/task/index.js";
import { generateId } from "@/core/delegation/index.js";
import type { PermissionRequest, PermissionDecision, PermissionPolicy, PermissionAuditEntry } from "@/protocols/permissions/types.js";
import { resourceMatches, isExpired, conditionsMet } from "@/protocols/permissions/utils.js";

export type { PermissionRequest, PermissionDecision, PermissionPolicy, PermissionAuditEntry } from "@/protocols/permissions/types.js";

export class PermissionManager {
  private policies: PermissionPolicy[] = [];
  private activePermissions: Map<string, Permission[]> = new Map();
  private auditLog: PermissionAuditEntry[] = [];

  constructor(policies?: PermissionPolicy[]) {
    if (policies) this.policies = policies;
  }

  requestPermission(
    request: PermissionRequest,
    grantorPermissions: Permission[]
  ): PermissionDecision {
    const policy = this.findMatchingPolicy(request.resource);

    if (!policy) {
      this.audit(request.requesterId, request.resource, request.actions, false, "No matching policy");
      return { granted: false, reason: "No policy found for resource" };
    }

    const policyAllowed = request.actions.filter((a) => policy.allowedActions.includes(a));
    if (policyAllowed.length === 0) {
      this.audit(request.requesterId, request.resource, request.actions, false, "Actions not in policy");
      return { granted: false, reason: "Requested actions not allowed by policy" };
    }

    const grantorPerm = grantorPermissions.find(
      (p) => resourceMatches(p.resource, request.resource) && p.delegatable
    );

    let approvedActions: string[];
    if (grantorPerm) {
      approvedActions = policyAllowed.filter((a) => grantorPerm.actions.includes(a));
    } else {
      approvedActions = policyAllowed;
    }

    if (approvedActions.length === 0) {
      this.audit(request.requesterId, request.resource, request.actions, false, "Grantor lacks permissions");
      return { granted: false, reason: "Grantor does not have delegatable permissions for these actions" };
    }

    const duration = request.duration
      ? policy.maxDuration
        ? Math.min(request.duration, policy.maxDuration)
        : request.duration
      : policy.maxDuration;

    const permission: Permission = {
      id: generateId("perm"),
      resource: request.resource,
      actions: approvedActions,
      conditions: policy.requiredConditions,
      expiresAt: duration ? Date.now() + duration : undefined,
      delegatable: request.needsDelegation && policy.delegatable,
      grantChain: grantorPerm ? [...grantorPerm.grantChain, request.requesterId] : [request.requesterId],
    };

    const agentPerms = this.activePermissions.get(request.requesterId) ?? [];
    agentPerms.push(permission);
    this.activePermissions.set(request.requesterId, agentPerms);

    this.audit(request.requesterId, request.resource, approvedActions, true, "Granted");

    const fullyGranted = approvedActions.length === request.actions.length;
    return {
      granted: true,
      permission,
      reason: fullyGranted
        ? "All requested actions granted"
        : `Partially granted: ${approvedActions.join(", ")}`,
      approvedActions,
    };
  }

  checkPermission(agentId: string, resource: string, action: string): boolean {
    const perms = this.activePermissions.get(agentId) ?? [];
    return perms.some(
      (p) =>
        resourceMatches(p.resource, resource) &&
        p.actions.includes(action) &&
        !isExpired(p) &&
        conditionsMet(p)
    );
  }

  revokePermission(agentId: string, permissionId: string): void {
    const perms = this.activePermissions.get(agentId);
    if (perms) {
      const idx = perms.findIndex((p) => p.id === permissionId);
      if (idx >= 0) {
        const revoked = perms.splice(idx, 1)[0];
        this.audit(agentId, revoked.resource, revoked.actions, false, "Revoked");
      }
    }
  }

  revokeAll(agentId: string): void {
    const perms = this.activePermissions.get(agentId) ?? [];
    for (const p of perms) {
      this.audit(agentId, p.resource, p.actions, false, "All revoked");
    }
    this.activePermissions.delete(agentId);
  }

  cleanupExpired(): number {
    let cleaned = 0;
    for (const [agentId, perms] of this.activePermissions) {
      const active = perms.filter((p) => !isExpired(p));
      cleaned += perms.length - active.length;
      if (active.length === 0) {
        this.activePermissions.delete(agentId);
      } else {
        this.activePermissions.set(agentId, active);
      }
    }
    return cleaned;
  }

  getPermissions(agentId: string): Permission[] {
    return (this.activePermissions.get(agentId) ?? []).filter((p) => !isExpired(p));
  }

  addPolicy(policy: PermissionPolicy): void {
    this.policies.push(policy);
  }

  getAuditLog(agentId?: string): PermissionAuditEntry[] {
    if (agentId) return this.auditLog.filter((e) => e.agentId === agentId);
    return [...this.auditLog];
  }

  private findMatchingPolicy(resource: string): PermissionPolicy | undefined {
    return this.policies
      .filter((p) => resourceMatches(p.resourcePattern, resource))
      .sort((a, b) => b.resourcePattern.length - a.resourcePattern.length)[0];
  }

  private audit(
    agentId: string,
    resource: string,
    actions: string[],
    granted: boolean,
    reason: string
  ): void {
    this.auditLog.push({
      agentId,
      resource,
      actions,
      granted,
      reason,
      timestamp: Date.now(),
    });
  }
}
