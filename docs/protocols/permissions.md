# Permissions

Privilege attenuation, just-in-time permissions, and semantic constraints (§4.7). Ensures delegation chains never escalate privileges.

## Usage

```typescript
import { PermissionManager, type PermissionPolicy } from "auton";

const manager = new PermissionManager([
  {
    resourcePattern: "files/*",
    allowedActions: ["read", "write"],
    grantableToTypes: ["ai", "human"],
    maxDuration: 3600_000,
    delegatable: true,
    maxDelegationDepth: 2,
  },
]);

// Request permission
const decision = manager.requestPermission(
  {
    requesterId: "agent-1",
    resource: "files/reports",
    actions: ["read", "write"],
    reason: "Generate report",
    duration: 600_000,
    needsDelegation: false,
  },
  grantorPermissions
);

if (decision.granted && decision.permission) {
  // Use decision.permission
}

// Check permission
const has = manager.checkPermission(agentId, "files/reports", "read");

// Revoke
manager.revokePermission(agentId, permissionId);
manager.revokeAll(agentId);

// Cleanup expired
const cleaned = manager.cleanupExpired();
```

## Policy Matching

- `*` — Matches any resource
- `files/*` — Matches `files/readme`, `files/reports`, etc.
- Exact match — `files/reports` matches only that resource

Most specific matching policy wins.

## Privilege Attenuation

When granting, the manager intersects:

1. Policy-allowed actions
2. Grantor's delegatable permissions for that resource

The delegatee receives only actions the grantor can delegate.

## Conditions

- `time_window` — Valid only between start/end timestamps
- `rate_limit` — Stub (would need external state)
- `approval_required`, `context_match`, `semantic` — Extensible

## Audit Log

```typescript
manager.getAuditLog();        // All entries
manager.getAuditLog(agentId); // Per agent
```

## See Also

- [Delegation Chain](../core/delegation.md) — Attenuates permissions in chain
- [Task Types](../types.md#permission) — Permission, PermissionCondition
