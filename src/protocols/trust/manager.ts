import type { ReputationMetrics } from "@/types/agent.js";
import type { TaskResult } from "@/types/task/index.js";
import type { TrustLedgerEntry, TrustEndorsement, TrustConfig } from "@/protocols/trust/types.js";
import { DEFAULT_TRUST_CONFIG } from "@/protocols/trust/types.js";
import {
  computeQualityScore,
  computeDirectTrustScore,
  computeWebOfTrustScore,
  computeReputationFromEntries,
} from "@/protocols/trust/compute.js";

export class TrustReputationManager {
  private ledger: TrustLedgerEntry[] = [];
  private endorsements: TrustEndorsement[] = [];
  private config: TrustConfig;
  private reputationCache: Map<string, ReputationMetrics> = new Map();
  private entryIdCounter = 0;

  constructor(config?: Partial<TrustConfig>) {
    this.config = { ...DEFAULT_TRUST_CONFIG, ...config };
  }

  recordCompletion(
    agentId: string,
    taskId: string,
    domain: string,
    result: TaskResult,
    deadline?: number
  ): TrustLedgerEntry {
    const entry: TrustLedgerEntry = {
      id: `trust_${(this.entryIdCounter++).toString(36)}`,
      agentId,
      taskId,
      domain,
      success: result.success,
      qualityScore: computeQualityScore(result),
      onTime: deadline ? result.executionTime + Date.now() <= deadline : true,
      executionTime: result.executionTime,
      violations: [],
      cost: result.cost ?? 0,
      timestamp: Date.now(),
    };

    this.ledger.push(entry);
    this.reputationCache.delete(agentId);
    return entry;
  }

  recordViolation(agentId: string, taskId: string, domain: string, violation: string): void {
    const existing = this.ledger.find((e) => e.agentId === agentId && e.taskId === taskId);
    if (existing) {
      existing.violations.push(violation);
    } else {
      const entry: TrustLedgerEntry = {
        id: `trust_${(this.entryIdCounter++).toString(36)}`,
        agentId,
        taskId,
        domain,
        success: false,
        qualityScore: 0,
        onTime: false,
        executionTime: 0,
        violations: [violation],
        cost: 0,
        timestamp: Date.now(),
      };
      this.ledger.push(entry);
    }
    this.reputationCache.delete(agentId);
  }

  addEndorsement(endorsement: TrustEndorsement): void {
    this.endorsements = this.endorsements.filter(
      (e) =>
        !(
          e.fromAgentId === endorsement.fromAgentId &&
          e.toAgentId === endorsement.toAgentId &&
          e.domain === endorsement.domain
        )
    );
    this.endorsements.push(endorsement);
    this.reputationCache.delete(endorsement.toAgentId);
  }

  computeTrustScore(agentId: string): number {
    const directScore = this.computeDirectTrustScore(agentId);
    const wotScore = this.computeWebOfTrustScore(agentId);
    const w = this.config.directObservationWeight;
    return directScore * w + wotScore * (1 - w);
  }

  computeReputation(agentId: string): ReputationMetrics {
    const cached = this.reputationCache.get(agentId);
    if (cached) return cached;

    const entries = this.getAgentEntries(agentId);
    const getWot = (id: string) =>
      computeWebOfTrustScore(id, this.endorsements, this.config, this.getAgentEntries.bind(this));

    const metrics = computeReputationFromEntries(agentId, entries, this.config, getWot);
    this.reputationCache.set(agentId, metrics);
    return metrics;
  }

  shouldTrust(
    agentId: string,
    requiredTrustLevel: number = 0.5
  ): { trusted: boolean; score: number; reason: string } {
    const score = this.computeTrustScore(agentId);
    const rep = this.computeReputation(agentId);

    if (rep.totalCompleted + rep.totalFailed < this.config.minTasksForReliability) {
      return {
        trusted: score >= requiredTrustLevel * 0.8,
        score,
        reason: `Insufficient history (${rep.totalCompleted + rep.totalFailed} tasks, need ${this.config.minTasksForReliability})`,
      };
    }

    return {
      trusted: score >= requiredTrustLevel,
      score,
      reason:
        score >= requiredTrustLevel
          ? `Trust score ${score.toFixed(3)} meets threshold ${requiredTrustLevel}`
          : `Trust score ${score.toFixed(3)} below threshold ${requiredTrustLevel}`,
    };
  }

  getLedger(agentId?: string): TrustLedgerEntry[] {
    if (agentId) return this.getAgentEntries(agentId);
    return [...this.ledger];
  }

  private getAgentEntries(agentId: string): TrustLedgerEntry[] {
    return this.ledger.filter((e) => e.agentId === agentId);
  }

  private computeDirectTrustScore(agentId: string): number {
    const entries = this.getAgentEntries(agentId);
    return computeDirectTrustScore(entries, this.config, this.computeReputation.bind(this));
  }

  private computeWebOfTrustScore(agentId: string): number {
    return computeWebOfTrustScore(
      agentId,
      this.endorsements,
      this.config,
      this.getAgentEntries.bind(this)
    );
  }
}
