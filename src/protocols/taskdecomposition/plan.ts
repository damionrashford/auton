import type {
  Task,
  TaskCharacteristics,
  TaskObjective,
  DecompositionPlan,
  DecompositionStrategy,
  SuccessCriterion,
} from "@/types/task/index.js";
import { generateId } from "@/core/delegation/index.js";

export function createSubtask(
  parent: Task,
  overrides: {
    description: string;
    objective: TaskObjective;
    characteristics: TaskCharacteristics;
    dependencyIds: string[];
    assigneeType?: "human" | "ai";
  }
): Task {
  const now = Date.now();
  return {
    id: generateId("task"),
    description: overrides.description,
    objective: overrides.objective,
    characteristics: overrides.characteristics,
    priority: parent.priority,
    status: "pending",
    parentId: parent.id,
    subtaskIds: [],
    dependencyIds: overrides.dependencyIds,
    delegatorId: parent.delegatorId,
    requiredPermissions: [...parent.requiredPermissions],
    createdAt: now,
    updatedAt: now,
    deadline: parent.deadline,
    tags: [...parent.tags],
    assigneeType: overrides.assigneeType,
  };
}

export function validateDAG(graph: Record<string, string[]>): void {
  const visited = new Set<string>();
  const inStack = new Set<string>();

  const dfs = (node: string): void => {
    if (inStack.has(node)) {
      throw new Error(`Cycle detected in dependency graph at task ${node}`);
    }
    if (visited.has(node)) return;

    visited.add(node);
    inStack.add(node);
    for (const dep of graph[node] ?? []) {
      dfs(dep);
    }
    inStack.delete(node);
  };

  for (const node of Object.keys(graph)) {
    dfs(node);
  }
}

export function estimateDuration(
  subtasks: Task[],
  graph: Record<string, string[]>,
  strategy: DecompositionStrategy
): number {
  if (subtasks.length === 0) return 0;

  const durations = new Map<string, number>();
  for (const st of subtasks) {
    durations.set(st.id, st.characteristics.estimatedDuration ?? 60_000);
  }

  if (strategy === "parallel") {
    return Math.max(...Array.from(durations.values()));
  }

  if (strategy === "sequential" || strategy === "pipeline") {
    return Array.from(durations.values()).reduce((a, b) => a + b, 0);
  }

  return criticalPath(subtasks, graph, durations);
}

function criticalPath(
  subtasks: Task[],
  graph: Record<string, string[]>,
  durations: Map<string, number>
): number {
  const memo = new Map<string, number>();

  const longest = (taskId: string): number => {
    if (memo.has(taskId)) return memo.get(taskId)!;

    const deps = graph[taskId] ?? [];
    const depMax = deps.length > 0 ? Math.max(...deps.map(longest)) : 0;
    const total = depMax + (durations.get(taskId) ?? 0);
    memo.set(taskId, total);
    return total;
  };

  return Math.max(...subtasks.map((st) => longest(st.id)));
}

export function getExecutionOrder(graph: Record<string, string[]>): string[][] {
  const inDegree = new Map<string, number>();
  const nodes = new Set<string>();

  for (const [node, deps] of Object.entries(graph)) {
    nodes.add(node);
    if (!inDegree.has(node)) inDegree.set(node, 0);
    for (const dep of deps) {
      nodes.add(dep);
      inDegree.set(node, (inDegree.get(node) ?? 0) + 1);
    }
  }

  for (const node of nodes) {
    if (!inDegree.has(node)) inDegree.set(node, 0);
  }

  const order: string[][] = [];
  const remaining = new Map(inDegree);

  while (remaining.size > 0) {
    const batch = Array.from(remaining.entries())
      .filter(([, deg]) => deg === 0)
      .map(([id]) => id);

    if (batch.length === 0) {
      throw new Error("Cycle detected in dependency graph during topological sort");
    }

    order.push(batch);

    for (const id of batch) {
      remaining.delete(id);
      for (const [node, deps] of Object.entries(graph)) {
        if (deps.includes(id) && remaining.has(node)) {
          remaining.set(node, (remaining.get(node) ?? 1) - 1);
        }
      }
    }
  }

  return order;
}

export function buildPlan(
  parentTask: Task,
  subtaskData: Array<{
    description: string;
    expectedOutput: string;
    successCriteria: SuccessCriterion[];
    dependsOn: number[];
    complexity: TaskCharacteristics["complexity"];
    estimatedDuration?: number;
    assigneeType?: "human" | "ai";
  }>,
  strategy: DecompositionStrategy,
  createSubtaskFn: typeof createSubtask
): DecompositionPlan {
  const subtasks: Task[] = [];
  const dependencyGraph: Record<string, string[]> = {};

  for (const data of subtaskData) {
    const subtask = createSubtaskFn(parentTask, {
      description: data.description,
      objective: {
        expectedOutput: data.expectedOutput,
        successCriteria: data.successCriteria,
        verificationMethod: parentTask.objective.verificationMethod,
      },
      characteristics: {
        ...parentTask.characteristics,
        complexity: data.complexity,
        estimatedDuration: data.estimatedDuration,
      },
      dependencyIds: [],
      assigneeType: data.assigneeType,
    });
    subtasks.push(subtask);
  }

  for (let i = 0; i < subtaskData.length; i++) {
    const deps = subtaskData[i].dependsOn
      .filter((idx) => idx >= 0 && idx < subtasks.length && idx !== i)
      .map((idx) => subtasks[idx].id);
    subtasks[i].dependencyIds = deps;
    dependencyGraph[subtasks[i].id] = deps;
  }

  validateDAG(dependencyGraph);
  parentTask.subtaskIds = subtasks.map((s) => s.id);

  return {
    rootTaskId: parentTask.id,
    strategy,
    subtasks,
    dependencyGraph,
    estimatedTotalDuration: estimateDuration(subtasks, dependencyGraph, strategy),
  };
}
