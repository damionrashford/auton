export interface OptimizationObjective {
  name: string;
  direction: "minimize" | "maximize";
  weight: number;
  bounds?: { min?: number; max?: number };
}

export interface Solution {
  id: string;
  scores: Record<string, number>;
  config: unknown;
}

export interface OptimizationResult {
  selected: Solution;
  paretoFront: Solution[];
  allScored: Array<{ solution: Solution; aggregatedScore: number }>;
}
