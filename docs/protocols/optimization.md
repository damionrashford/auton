# Optimization

Multi-objective optimization for balancing cost, quality, speed, and risk (§4.3). Implements Pareto-optimal solution selection.

## Default Objectives

| Objective | Direction | Weight |
|-----------|-----------|--------|
| quality | maximize | 0.35 |
| cost | minimize | 0.20 |
| speed | maximize | 0.25 |
| risk | minimize | 0.20 |

## Usage

```typescript
import {
  MultiObjectiveOptimizer,
  DELEGATION_OBJECTIVES,
  type Solution,
} from "auton";

const optimizer = new MultiObjectiveOptimizer();

const solutions: Solution[] = [
  {
    id: "s1",
    scores: { quality: 0.9, cost: 50, speed: 0.7, risk: 0.2 },
    config: { agentId: "a1", ... },
  },
  {
    id: "s2",
    scores: { quality: 0.7, cost: 20, speed: 0.9, risk: 0.3 },
    config: { agentId: "a2", ... },
  },
];

const result = optimizer.optimize(solutions);

// result.selected — Best solution by weighted score
// result.paretoFront — Pareto-optimal solutions
// result.allScored — All solutions with aggregated scores
```

## Optimization Result

```typescript
interface OptimizationResult {
  selected: Solution;
  paretoFront: Solution[];
  allScored: Array<{ solution: Solution; aggregatedScore: number }>;
}
```

## Process

1. Filter solutions that violate bounds (if any)
2. Normalize scores to [0, 1] per objective (flip for minimize)
3. Compute Pareto front — solutions not dominated by any other
4. Score each with weighted sum
5. Select highest-scoring

## Custom Objectives

```typescript
optimizer.addObjective({
  name: "latency",
  direction: "minimize",
  weight: 0.1,
  bounds: { min: 0, max: 1000 },
});

optimizer.updateWeights({ quality: 0.4, cost: 0.15 });
```

## See Also

- [Task Assignment](./task-assignment.md) — Can use optimizer for multi-candidate selection
- [Architecture](../architecture.md) — Role in delegation
