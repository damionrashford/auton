import type { OptimizationObjective } from "@/protocols/optimization/types.js";

export const DELEGATION_OBJECTIVES: OptimizationObjective[] = [
  { name: "quality", direction: "maximize", weight: 0.35 },
  { name: "cost", direction: "minimize", weight: 0.20 },
  { name: "speed", direction: "maximize", weight: 0.25 },
  { name: "risk", direction: "minimize", weight: 0.20 },
];
