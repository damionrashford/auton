import type { Permission, ResourceBudget } from "@/types/task/index.js";
import type { DelegationChainInfo } from "@/types/agent.js";
import { generateId } from "@/core/delegation/id.js";

export function attenuatePermissions(
  requested: Permission[],
  available: Permission[],
  grantorId: string,
  isExpired: (p: Permission) => boolean
): Permission[] {
  const attenuated: Permission[] = [];

  for (const req of requested) {
    const matching = available.find(
      (p) => p.resource === req.resource && !isExpired(p)
    );
    if (!matching) continue;
    if (!matching.delegatable) continue;

    const allowedActions = req.actions.filter((a) => matching.actions.includes(a));
    if (allowedActions.length === 0) continue;

    attenuated.push({
      ...req,
      id: generateId("perm"),
      actions: allowedActions,
      delegatable: req.delegatable && matching.delegatable,
      grantChain: [...matching.grantChain, grantorId],
      expiresAt: matching.expiresAt
        ? req.expiresAt
          ? Math.min(req.expiresAt, matching.expiresAt)
          : matching.expiresAt
        : req.expiresAt,
    });
  }

  return attenuated;
}

export function attenuateBudget(
  budget: ResourceBudget,
  parentChain?: DelegationChainInfo
): void {
  if (!parentChain) return;
  if (budget.maxDelegationDepth !== undefined) {
    budget.maxDelegationDepth = Math.min(
      budget.maxDelegationDepth,
      parentChain.maxDepth - parentChain.depth
    );
  }
}
