import type { ReputationMetrics, DomainScore } from "@/types/agent.js";
import type { TaskResult } from "@/types/task/index.js";
import type { TrustLedgerEntry, TrustEndorsement, TrustConfig } from "@/protocols/trust/types.js";

export function computeQualityScore(result: TaskResult): number {
  if (!result.success) return 0;
  const scores = Object.values(result.scores);
  if (scores.length === 0) return result.success ? 0.7 : 0;
  return scores.reduce((a, b) => a + b, 0) / scores.length;
}

export function computeDirectTrustScore(
  entries: TrustLedgerEntry[],
  config: TrustConfig,
  getReputation: (agentId: string) => ReputationMetrics
): number {
  if (entries.length === 0) return config.initialTrustScore;

  const agentId = entries[0]?.agentId ?? "";
  const rep = getReputation(agentId);

  let score =
    rep.successRate * 0.35 +
    rep.avgQuality * 0.25 +
    rep.onTimeRate * 0.15 +
    rep.consistency * 0.15 +
    (1 - Math.min(1, rep.violations * config.violationPenalty)) * 0.10;

  if (rep.consistency > 0.8 && rep.totalCompleted >= config.minTasksForReliability) {
    score = Math.min(1, score + config.consistencyBonus);
  }

  return Math.max(0, Math.min(1, score));
}

export function computeWebOfTrustScore(
  agentId: string,
  endorsements: TrustEndorsement[],
  config: TrustConfig,
  getAgentEntries: (id: string) => TrustLedgerEntry[]
): number {
  const endorsementsForAgent = endorsements.filter((e) => e.toAgentId === agentId);

  if (endorsementsForAgent.length === 0) return config.initialTrustScore;

  let totalWeight = 0;
  let weightedSum = 0;

  for (const endorsement of endorsementsForAgent) {
    const endorserEntries = getAgentEntries(endorsement.fromAgentId);
    const endorserReliability =
      endorserEntries.length >= config.minTasksForReliability
        ? endorserEntries.filter((e) => e.success).length / endorserEntries.length
        : config.initialTrustScore;

    const weight = endorserReliability;
    weightedSum += endorsement.trustLevel * weight;
    totalWeight += weight;
  }

  return totalWeight > 0 ? weightedSum / totalWeight : config.initialTrustScore;
}

export function computeReputationFromEntries(
  agentId: string,
  entries: TrustLedgerEntry[],
  config: TrustConfig,
  getWebOfTrustScore: (agentId: string) => number
): ReputationMetrics {
  const now = Date.now();

  if (entries.length === 0) {
    return {
      totalCompleted: 0,
      totalFailed: 0,
      successRate: config.initialTrustScore,
      avgQuality: config.initialTrustScore,
      avgResponseTime: 0,
      onTimeRate: 1,
      violations: 0,
      webOfTrustScore: getWebOfTrustScore(agentId),
      consistency: config.initialTrustScore,
      domainScores: {},
      lastUpdated: now,
    };
  }

  const weightedEntries = entries.map((e) => {
    const age = now - e.timestamp;
    const weight = Math.exp(-config.decayRate * (age / 86_400_000));
    return { entry: e, weight };
  });

  const totalWeight = weightedEntries.reduce((s, w) => s + w.weight, 0);

  const successEntries = weightedEntries.filter((w) => w.entry.success);
  const successRate =
    totalWeight > 0
      ? successEntries.reduce((s, w) => s + w.weight, 0) / totalWeight
      : config.initialTrustScore;

  const avgQuality =
    totalWeight > 0
      ? weightedEntries.reduce((s, w) => s + w.entry.qualityScore * w.weight, 0) / totalWeight
      : config.initialTrustScore;

  const avgResponseTime =
    entries.length > 0
      ? entries.reduce((s, e) => s + e.executionTime, 0) / entries.length
      : 0;

  const onTimeEntries = weightedEntries.filter((w) => w.entry.onTime);
  const onTimeRate =
    totalWeight > 0 ? onTimeEntries.reduce((s, w) => s + w.weight, 0) / totalWeight : 1;

  const totalViolations = entries.reduce((s, e) => s + e.violations.length, 0);

  const qualityValues = entries.map((e) => e.qualityScore);
  const mean = qualityValues.reduce((s, v) => s + v, 0) / qualityValues.length;
  const variance =
    qualityValues.reduce((s, v) => s + (v - mean) ** 2, 0) / qualityValues.length;
  const consistency = Math.max(0, 1 - Math.sqrt(variance));

  const domainScores: Record<string, DomainScore> = {};
  const domainGroups = new Map<string, TrustLedgerEntry[]>();
  for (const e of entries) {
    const group = domainGroups.get(e.domain) ?? [];
    group.push(e);
    domainGroups.set(e.domain, group);
  }
  for (const [domain, group] of domainGroups) {
    const successes = group.filter((e) => e.success).length;
    const avgQ = group.reduce((s, e) => s + e.qualityScore, 0) / group.length;
    domainScores[domain] = {
      domain,
      tasksCompleted: group.length,
      successRate: successes / group.length,
      avgQuality: avgQ,
    };
  }

  return {
    totalCompleted: entries.filter((e) => e.success).length,
    totalFailed: entries.filter((e) => !e.success).length,
    successRate,
    avgQuality,
    avgResponseTime,
    onTimeRate,
    violations: totalViolations,
    webOfTrustScore: getWebOfTrustScore(agentId),
    consistency,
    domainScores,
    lastUpdated: now,
  };
}
