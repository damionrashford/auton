import type { Task } from "@/types/task/index.js";
import type { AgentProfile } from "@/types/agent.js";
import type { AssignmentScore, AssignmentWeights } from "@/protocols/taskassignment/types.js";
import { DEFAULT_WEIGHTS } from "@/protocols/taskassignment/types.js";
import {
  scoreCapabilityMatch,
  scoreAvailability,
  scoreDomainMatch,
  scoreCostEfficiency,
  scoreHistoricalPerformance,
  computeTotalScore,
} from "@/protocols/taskassignment/scoring.js";

export type { AssignmentScore, AssignmentWeights } from "@/protocols/taskassignment/types.js";

export class TaskAssigner {
  private weights: AssignmentWeights;

  constructor(weights?: Partial<AssignmentWeights>) {
    this.weights = { ...DEFAULT_WEIGHTS, ...weights };
  }

  rankCandidates(task: Task, candidates: AgentProfile[]): AssignmentScore[] {
    const availableCandidates = candidates.filter(
      (a) => a.status === "available" || a.status === "busy"
    );

    const scores = availableCandidates.map((agent) => this.scoreAgent(task, agent));
    scores.sort((a, b) => b.totalScore - a.totalScore);
    return scores;
  }

  assign(
    task: Task,
    candidates: AgentProfile[],
    options?: { delegator?: AgentProfile; currentDelegateeCount?: number }
  ): AgentProfile | null {
    const delegator = options?.delegator;
    const currentCount = options?.currentDelegateeCount ?? 0;

    if (delegator?.maxConcurrentDelegatees !== undefined && currentCount >= delegator.maxConcurrentDelegatees) {
      return null;
    }

    const ranked = this.rankCandidates(task, candidates);
    if (ranked.length === 0) return null;

    const bestId = ranked[0].agentId;
    return candidates.find((a) => a.id === bestId) ?? null;
  }

  assignBatch(
    tasks: Task[],
    candidates: AgentProfile[],
    maxConcurrentPerAgent: number = 3
  ): Map<string, string> {
    const assignments = new Map<string, string>();
    const agentLoad = new Map<string, number>();

    for (const agent of candidates) {
      agentLoad.set(agent.id, 0);
    }

    const priorityOrder: Record<string, number> = {
      critical: 0,
      high: 1,
      normal: 2,
      low: 3,
      lowest: 4,
    };
    const sortedTasks = [...tasks].sort(
      (a, b) => (priorityOrder[a.priority] ?? 2) - (priorityOrder[b.priority] ?? 2)
    );

    for (const task of sortedTasks) {
      const available = candidates.filter(
        (a) =>
          (a.status === "available" || a.status === "busy") &&
          (agentLoad.get(a.id) ?? 0) < maxConcurrentPerAgent
      );

      if (available.length === 0) continue;

      const ranked = this.rankCandidates(task, available);
      if (ranked.length > 0) {
        const bestId = ranked[0].agentId;
        assignments.set(task.id, bestId);
        agentLoad.set(bestId, (agentLoad.get(bestId) ?? 0) + 1);
      }
    }

    return assignments;
  }

  private scoreAgent(task: Task, agent: AgentProfile): AssignmentScore {
    const breakdown = {
      capabilityMatch: scoreCapabilityMatch(task, agent),
      trustScore: agent.trustScore ?? 0.5,
      availabilityScore: scoreAvailability(agent),
      domainMatch: scoreDomainMatch(task, agent),
      costEfficiency: scoreCostEfficiency(task, agent),
      historicalPerformance: scoreHistoricalPerformance(task, agent),
    };

    const totalScore = computeTotalScore(breakdown, this.weights);
    return { agentId: agent.id, totalScore, breakdown };
  }
}
