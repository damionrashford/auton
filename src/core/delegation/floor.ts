import type { Task } from "@/types/task/index.js";

export interface ComplexityFloorConfig {
  maxCriticalityToBypass: "negligible" | "low";
  maxUncertaintyToBypass: "deterministic" | "low";
  maxDurationMsToBypass: number;
}

const DEFAULT_FLOOR: ComplexityFloorConfig = {
  maxCriticalityToBypass: "low",
  maxUncertaintyToBypass: "low",
  maxDurationMsToBypass: 60_000,
};

const CRITICALITY_ORDER: Record<string, number> = {
  negligible: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};

const UNCERTAINTY_ORDER: Record<string, number> = {
  deterministic: 0,
  low: 1,
  moderate: 2,
  high: 3,
  chaotic: 4,
};

export function shouldBypassDelegation(
  task: Task,
  config: Partial<ComplexityFloorConfig> = {}
): boolean {
  const c = { ...DEFAULT_FLOOR, ...config };
  const critOrder = CRITICALITY_ORDER[task.characteristics.criticality] ?? 2;
  const maxCrit = CRITICALITY_ORDER[c.maxCriticalityToBypass];
  const uncOrder = UNCERTAINTY_ORDER[task.characteristics.uncertainty] ?? 2;
  const maxUnc = UNCERTAINTY_ORDER[c.maxUncertaintyToBypass];
  const duration = task.characteristics.estimatedDuration ?? 0;

  return (
    task.characteristics.complexity === "trivial" &&
    critOrder <= maxCrit &&
    uncOrder <= maxUnc &&
    duration <= c.maxDurationMsToBypass
  );
}
