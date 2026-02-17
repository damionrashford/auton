# Delegation Chain

Manages hierarchical delegation with **privilege attenuation** (§4.7). Each delegation hop can only narrow permissions; delegatees never receive more than delegators hold.

## Concepts

### Delegation Edge

A single hop from delegator → delegatee:

```typescript
interface DelegationEdge {
  delegatorId: string;
  delegateeId: string;
  contractId: string;
  taskId: string;
  depth: number;
  timestamp: number;
}
```

### Delegation Chain

Ordered chain of edges with accumulated (attenuated) permissions:

```typescript
interface DelegationChainInfo {
  rootDelegatorId: string;
  chain: DelegationEdge[];
  depth: number;
  maxDepth: number;
  effectivePermissions: Permission[];
}
```

### Privilege Attenuation

- Requested permissions are intersected with the delegator's available permissions
- Only delegatable permissions can be passed down
- Actions are narrowed: delegatee gets only actions the delegator has
- Expiration is capped by parent permission expiry

## Usage

```typescript
import {
  DelegationChainManager,
  generateId,
  DelegationError,
} from "auton";

const manager = new DelegationChainManager();

const contract = {
  id: generateId("contract"),
  taskId: task.id,
  delegatorId: delegator.id,
  delegateeId: delegatee.id,
  deliverables: [task.objective.expectedOutput],
  acceptanceCriteria: task.objective.successCriteria,
  grantedPermissions: delegatee.basePermissions,
  budget: { maxTokens: 100_000, maxDuration: 300_000 },
  monitoringMode: "continuous",
  autonomyLevel: "bounded_autonomy",
  escalationPolicy: { triggers: [], escalateTo: delegator.id },
  createdAt: Date.now(),
  status: "active" as const,
};

const chain = manager.delegate(delegator, delegatee, contract, parentChainId);

// Check permission in chain
const has = manager.hasPermission(chain.chainId, "files", "read");

// Revoke chain (cascades to children)
manager.revoke(chainId);
```

## Constraints

- **Depth** — Delegation depth cannot exceed `delegator.maxDelegationDepth`
- **Authorization** — `delegator.canDelegate` must be true
- **Budget** — Child `maxDelegationDepth` is capped by remaining parent depth

## Errors

```typescript
class DelegationError extends Error {
  code: "DEPTH_EXCEEDED" | "UNAUTHORIZED_DELEGATION" | "PERMISSION_DENIED" | "CONTRACT_VIOLATED" | "BUDGET_EXCEEDED";
}
```

## ID Generation

```typescript
generateId(prefix?: string): string
// e.g. "contract_abc123_0", "perm_abc123_1"
```

## See Also

- [Executor](./executor.md) — Uses DelegationChainManager in the pipeline
- [Permissions](../protocols/permissions.md) — Permission policies and JIT granting
- [Contract Types](../types.md#delegation-contract) — DelegationContract shape
