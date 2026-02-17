import type { OptimizationObjective, Solution, OptimizationResult } from "@/protocols/optimization/types.js";
import { DELEGATION_OBJECTIVES } from "@/protocols/optimization/objectives.js";
import { normalize, computeParetoFront, weightedScore } from "@/protocols/optimization/compute.js";

export class MultiObjectiveOptimizer {
  private objectives: OptimizationObjective[];

  constructor(objectives?: OptimizationObjective[]) {
    this.objectives = objectives ?? [...DELEGATION_OBJECTIVES];
    this.normalizeWeights();
  }

  optimize(solutions: Solution[]): OptimizationResult {
    if (solutions.length === 0) {
      throw new Error("No solutions to optimize");
    }

    if (solutions.length === 1) {
      return {
        selected: solutions[0],
        paretoFront: solutions,
        allScored: [{ solution: solutions[0], aggregatedScore: 1 }],
      };
    }

    const feasible = solutions.filter((s) => this.isFeasible(s));
    const candidates = feasible.length > 0 ? feasible : solutions;

    const normalized = normalize(candidates, this.objectives);
    const paretoFront = computeParetoFront(normalized, this.objectives);

    const allScored = normalized.map((n) => ({
      solution: candidates[normalized.indexOf(n)],
      aggregatedScore: weightedScore(n, this.objectives),
    }));

    allScored.sort((a, b) => b.aggregatedScore - a.aggregatedScore);

    return {
      selected: allScored[0].solution,
      paretoFront: paretoFront.map((n) => candidates[normalized.indexOf(n)]),
      allScored,
    };
  }

  private isFeasible(solution: Solution): boolean {
    for (const obj of this.objectives) {
      const value = solution.scores[obj.name];
      if (value === undefined) continue;
      if (obj.bounds?.min !== undefined && value < obj.bounds.min) return false;
      if (obj.bounds?.max !== undefined && value > obj.bounds.max) return false;
    }
    return true;
  }

  updateWeights(updates: Record<string, number>): void {
    for (const obj of this.objectives) {
      if (updates[obj.name] !== undefined) {
        obj.weight = updates[obj.name];
      }
    }
    this.normalizeWeights();
  }

  private normalizeWeights(): void {
    const sum = this.objectives.reduce((s, o) => s + o.weight, 0);
    if (sum > 0) {
      for (const obj of this.objectives) {
        obj.weight /= sum;
      }
    }
  }

  addObjective(objective: OptimizationObjective): void {
    this.objectives.push(objective);
    this.normalizeWeights();
  }

  getObjectives(): OptimizationObjective[] {
    return [...this.objectives];
  }
}
