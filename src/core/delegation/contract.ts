import type { Task, DelegationContract } from "@/types/task/index.js";
import type { AgentProfile } from "@/types/agent.js";
import { generateId } from "@/core/delegation/id.js";

export function createContract(
  task: Task,
  delegator: AgentProfile,
  delegatee: AgentProfile,
  defaultBudget?: { maxTokens?: number; maxDuration?: number }
): DelegationContract {
  const budget = defaultBudget ?? {
    maxTokens: 100_000,
    maxDuration: 300_000,
  };

  return {
    id: generateId("contract"),
    taskId: task.id,
    delegatorId: delegator.id,
    delegateeId: delegatee.id,
    deliverables: [task.objective.expectedOutput],
    acceptanceCriteria: task.objective.successCriteria,
    grantedPermissions: delegatee.basePermissions,
    budget,
    monitoringMode: delegatee.preferredMonitoringMode,
    autonomyLevel: delegator.maxAutonomyLevel,
    deadline: task.deadline,
    escalationPolicy: {
      triggers: [{ type: "timeout", threshold: 0 }],
      escalateTo: delegator.id,
    },
    createdAt: Date.now(),
    status: "active",
  };
}
