import type { Permission, DelegationContract } from "@/types/task/index.js";
import type { AgentProfile, DelegationEdge, DelegationChainInfo } from "@/types/agent.js";
import { generateId } from "@/core/delegation/id.js";
import { DelegationError } from "@/core/delegation/error.js";
import { attenuatePermissions, attenuateBudget } from "@/core/delegation/attenuate.js";

export { generateId } from "@/core/delegation/id.js";
export { DelegationError } from "@/core/delegation/error.js";
export type { DelegationErrorCode } from "@/core/delegation/error.js";

export class DelegationChainManager {
  private chains: Map<string, DelegationChainInfo> = new Map();
  private contracts: Map<string, DelegationContract> = new Map();
  private edges: DelegationEdge[] = [];

  delegate(
    delegator: AgentProfile,
    delegatee: AgentProfile,
    contract: DelegationContract,
    parentChainId?: string
  ): DelegationChainInfo {
    const parentChain = parentChainId ? this.chains.get(parentChainId) : undefined;
    const currentDepth = parentChain ? parentChain.depth + 1 : 0;

    if (currentDepth > delegator.maxDelegationDepth) {
      throw new DelegationError(
        `Delegation depth ${currentDepth} exceeds maximum ${delegator.maxDelegationDepth}`,
        "DEPTH_EXCEEDED"
      );
    }

    if (!delegator.canDelegate) {
      throw new DelegationError(
        `Agent ${delegator.id} is not authorized to delegate`,
        "UNAUTHORIZED_DELEGATION"
      );
    }

    const attenuatedPermissions = attenuatePermissions(
      contract.grantedPermissions,
      parentChain?.effectivePermissions ?? delegator.basePermissions,
      delegator.id,
      this.isExpired.bind(this)
    );

    attenuateBudget(contract.budget, parentChain);

    const edge: DelegationEdge = {
      delegatorId: delegator.id,
      delegateeId: delegatee.id,
      contractId: contract.id,
      taskId: contract.taskId,
      depth: currentDepth,
      timestamp: Date.now(),
    };

    this.edges.push(edge);
    this.contracts.set(contract.id, contract);

    const chain: DelegationChainInfo = {
      rootDelegatorId: parentChain?.rootDelegatorId ?? delegator.id,
      chain: [...(parentChain?.chain ?? []), edge],
      depth: currentDepth,
      maxDepth: Math.min(delegator.maxDelegationDepth, delegatee.maxDelegationDepth),
      effectivePermissions: attenuatedPermissions,
    };

    const chainId = generateId("chain");
    this.chains.set(chainId, chain);

    return chain;
  }

  private isExpired(permission: Permission): boolean {
    return permission.expiresAt !== undefined && Date.now() > permission.expiresAt;
  }

  hasPermission(chainId: string, resource: string, action: string): boolean {
    const chain = this.chains.get(chainId);
    if (!chain) return false;

    return chain.effectivePermissions.some(
      (p) =>
        p.resource === resource &&
        p.actions.includes(action) &&
        !this.isExpired(p)
    );
  }

  getContract(contractId: string): DelegationContract | undefined {
    return this.contracts.get(contractId);
  }

  getChain(chainId: string): DelegationChainInfo | undefined {
    return this.chains.get(chainId);
  }

  revoke(chainId: string): void {
    const chain = this.chains.get(chainId);
    if (!chain) return;

    for (const edge of chain.chain) {
      const contract = this.contracts.get(edge.contractId);
      if (contract) contract.status = "cancelled";
    }

    for (const [id, c] of this.chains) {
      if (c.chain.some((e) => chain.chain.some((pe) => pe.contractId === e.contractId))) {
        if (id !== chainId) this.revoke(id);
      }
    }

    this.chains.delete(chainId);
  }

  getActiveContracts(agentId: string): DelegationContract[] {
    return Array.from(this.contracts.values()).filter(
      (c) =>
        c.status === "active" &&
        (c.delegatorId === agentId || c.delegateeId === agentId)
    );
  }
}
