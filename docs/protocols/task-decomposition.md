# Task Decomposition

Breaks complex tasks into subtask DAGs with dependency resolution. Uses **contract-first decomposition**: every subtask has measurable success criteria before delegation (§4.1).

## Strategies

| Strategy | Description |
|----------|-------------|
| `sequential` | Subtasks execute in order |
| `parallel` | Independent subtasks run concurrently |
| `hierarchical` | Tree of progressively simpler tasks |
| `pipeline` | Output of one feeds input to next |
| `map_reduce` | Split data, process in parallel, combine |
| `conditional` | Branching based on intermediate results |

## Usage

```typescript
import { TaskDecomposer } from "auton";

// With AI client for LLM-assisted decomposition
const decomposer = new TaskDecomposer(aiClient);
const plan = await decomposer.decompose(task, "hierarchical", 5);

// Manual decomposition (no LLM)
const decomposer = new TaskDecomposer();
const plan = decomposer.decomposeManual(task, "sequential");

// Execution order from dependency graph
const order = decomposer.getExecutionOrder(plan.dependencyGraph);
// Returns string[][] — batches of task IDs that can run in parallel
```

## Decomposition Plan

```typescript
interface DecompositionPlan {
  rootTaskId: string;
  strategy: DecompositionStrategy;
  subtasks: Task[];
  dependencyGraph: Record<string, string[]>;  // taskId -> dependsOn[]
  estimatedTotalCost?: number;
  estimatedTotalDuration?: number;
}
```

## AI-Assisted Decomposition

When an `AIClient` is provided, the decomposer:

1. Sends a structured prompt with task description, objective, complexity
2. Expects JSON with `subtasks` array and `strategy`
3. Each subtask must have: `description`, `expectedOutput`, `successCriteria`, `dependsOn`, `complexity`, `estimatedDuration`, `assigneeType`
4. Validates DAG (no cycles)
5. Resolves dependency indices to task IDs

## Manual Decomposition

When no client is provided, `decomposeManual()` returns a single-subtask plan (the task itself). Domain-specific logic can be layered on top.

## Execution Order

`getExecutionOrder(graph)` returns a topological order as batches: each batch contains task IDs that can run in parallel (no dependencies within the batch).

## See Also

- [Architecture](../architecture.md) — Role in lifecycle
- [Executor](../core/executor.md) — Uses decomposition when `decomposeFirst` is true
