import type { Task } from "@/types/task/index.js";
import type { AgentProfile } from "@/types/agent.js";
import type { AssignmentWeights } from "@/protocols/taskassignment/types.js";

export function scoreCapabilityMatch(task: Task, agent: AgentProfile): number {
  if (task.requiredPermissions.length === 0 && task.tags.length === 0) {
    if (agent.capabilities.length === 0) return 0.5;
    return (
      agent.capabilities.reduce((sum, c) => sum + c.proficiency, 0) /
      agent.capabilities.length
    );
  }

  const required = new Set([...task.tags, ...task.requiredPermissions]);
  let matched = 0;
  let totalProficiency = 0;

  for (const req of required) {
    const cap = agent.capabilities.find(
      (c) => c.name === req || (c.domains ?? []).includes(req)
    );
    if (cap) {
      matched++;
      totalProficiency += cap.proficiency;
    }
  }

  if (required.size === 0) return 0.5;
  return matched > 0 ? totalProficiency / required.size : 0;
}

export function scoreAvailability(agent: AgentProfile): number {
  if (agent.status === "available") return 1;
  if (agent.status === "busy") return 0.7;
  return 0;
}

export function scoreDomainMatch(task: Task, agent: AgentProfile): number {
  if (task.tags.length === 0) return 0.5;

  let matchCount = 0;
  for (const tag of task.tags) {
    const hasDomain = agent.capabilities.some(
      (c) => c.domains?.includes(tag) || c.name === tag
    );
    if (hasDomain) matchCount++;
  }

  return task.tags.length > 0 ? matchCount / task.tags.length : 0.5;
}

export function scoreCostEfficiency(_task: Task, _agent: AgentProfile): number {
  const agent = _agent as AgentProfile & { costPerTask?: number };
  return agent.costPerTask !== undefined ? 1 - Math.min(1, agent.costPerTask / 100) : 0.5;
}

export function scoreHistoricalPerformance(_task: Task, agent: AgentProfile): number {
  return agent.trustScore ?? 0.5;
}

export function computeTotalScore(
  breakdown: {
    capabilityMatch: number;
    trustScore: number;
    availabilityScore: number;
    domainMatch: number;
    costEfficiency: number;
    historicalPerformance: number;
  },
  weights: AssignmentWeights
): number {
  return (
    breakdown.capabilityMatch * weights.capabilityMatch +
    breakdown.trustScore * weights.trustScore +
    breakdown.availabilityScore * weights.availability +
    breakdown.domainMatch * weights.domainMatch +
    breakdown.costEfficiency * weights.costEfficiency +
    breakdown.historicalPerformance * weights.historicalPerformance
  );
}
