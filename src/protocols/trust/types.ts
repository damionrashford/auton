export interface TrustLedgerEntry {
  id: string;
  agentId: string;
  taskId: string;
  domain: string;
  success: boolean;
  qualityScore: number;
  onTime: boolean;
  executionTime: number;
  violations: string[];
  cost: number;
  timestamp: number;
}

export interface TrustEndorsement {
  fromAgentId: string;
  toAgentId: string;
  trustLevel: number;
  domain?: string;
  reason: string;
  timestamp: number;
}

export interface TrustConfig {
  decayRate: number;
  minTasksForReliability: number;
  directObservationWeight: number;
  initialTrustScore: number;
  violationPenalty: number;
  consistencyBonus: number;
}

export const DEFAULT_TRUST_CONFIG: TrustConfig = {
  decayRate: 0.05,
  minTasksForReliability: 5,
  directObservationWeight: 0.7,
  initialTrustScore: 0.5,
  violationPenalty: 0.15,
  consistencyBonus: 0.05,
};
