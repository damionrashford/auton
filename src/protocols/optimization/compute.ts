import type { OptimizationObjective, Solution } from "@/protocols/optimization/types.js";

export function normalize(
  solutions: Solution[],
  objectives: OptimizationObjective[]
): Record<string, number>[] {
  const ranges = new Map<string, { min: number; max: number }>();

  for (const obj of objectives) {
    let min = Infinity;
    let max = -Infinity;
    for (const s of solutions) {
      const v = s.scores[obj.name] ?? 0;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    ranges.set(obj.name, { min, max });
  }

  return solutions.map((s) => {
    const normalized: Record<string, number> = {};
    for (const obj of objectives) {
      const range = ranges.get(obj.name)!;
      const raw = s.scores[obj.name] ?? 0;
      const span = range.max - range.min;
      const norm = span > 0 ? (raw - range.min) / span : 0.5;
      normalized[obj.name] = obj.direction === "minimize" ? 1 - norm : norm;
    }
    return normalized;
  });
}

export function computeParetoFront(
  normalizedSolutions: Record<string, number>[],
  objectives: OptimizationObjective[]
): Record<string, number>[] {
  const front: Record<string, number>[] = [];

  for (let i = 0; i < normalizedSolutions.length; i++) {
    let dominated = false;
    for (let j = 0; j < normalizedSolutions.length; j++) {
      if (i === j) continue;
      if (dominates(normalizedSolutions[j], normalizedSolutions[i], objectives)) {
        dominated = true;
        break;
      }
    }
    if (!dominated) {
      front.push(normalizedSolutions[i]);
    }
  }

  return front;
}

function dominates(
  a: Record<string, number>,
  b: Record<string, number>,
  objectives: OptimizationObjective[]
): boolean {
  let strictlyBetter = false;
  for (const obj of objectives) {
    const va = a[obj.name] ?? 0;
    const vb = b[obj.name] ?? 0;
    if (va < vb) return false;
    if (va > vb) strictlyBetter = true;
  }
  return strictlyBetter;
}

export function weightedScore(
  normalized: Record<string, number>,
  objectives: OptimizationObjective[]
): number {
  let score = 0;
  for (const obj of objectives) {
    score += (normalized[obj.name] ?? 0) * obj.weight;
  }
  return score;
}
