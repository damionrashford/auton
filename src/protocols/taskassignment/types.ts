export interface AssignmentScore {
  agentId: string;
  totalScore: number;
  breakdown: {
    capabilityMatch: number;
    trustScore: number;
    availabilityScore: number;
    domainMatch: number;
    costEfficiency: number;
    historicalPerformance: number;
  };
}

export interface AssignmentWeights {
  capabilityMatch: number;
  trustScore: number;
  availability: number;
  domainMatch: number;
  costEfficiency: number;
  historicalPerformance: number;
}

export const DEFAULT_WEIGHTS: AssignmentWeights = {
  capabilityMatch: 0.30,
  trustScore: 0.20,
  availability: 0.15,
  domainMatch: 0.15,
  costEfficiency: 0.10,
  historicalPerformance: 0.10,
};
