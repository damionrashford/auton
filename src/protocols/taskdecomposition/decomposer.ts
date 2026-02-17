import type {
  Task,
  TaskCharacteristics,
  DecompositionPlan,
  DecompositionStrategy,
  SuccessCriterion,
} from "@/types/task/index.js";
import type { ChatMessage } from "@/types/ai.js";
import type { AIClient } from "@/core/ai/client.js";
import { createSubtask, buildPlan, getExecutionOrder } from "@/protocols/taskdecomposition/plan.js";

export class TaskDecomposer {
  constructor(private client?: AIClient) {}

  async decompose(
    task: Task,
    strategy: DecompositionStrategy = "hierarchical",
    maxDepth: number = 5
  ): Promise<DecompositionPlan> {
    if (this.client) {
      return this.decomposeWithAI(task, strategy, maxDepth);
    }
    return this.decomposeManual(task, strategy);
  }

  private async decomposeWithAI(
    task: Task,
    strategy: DecompositionStrategy,
    maxDepth: number
  ): Promise<DecompositionPlan> {
    const systemPrompt = `You are a task decomposition engine. Given a task, break it down into subtasks.
Return a JSON object with this exact structure:
{
  "subtasks": [
    {
      "description": "string",
      "expectedOutput": "string",
      "successCriteria": [{"metric": "string", "operator": "eq|gt|lt|contains|matches", "target": "value", "weight": 0.0-1.0}],
      "dependsOn": [indices of subtasks this depends on],
      "complexity": "trivial|simple|moderate|complex|extreme",
      "estimatedDuration": milliseconds,
      "assigneeType": "human|ai"
    }
  ],
  "strategy": "${strategy}"
}
Rules:
- Each subtask MUST have at least one measurable success criterion (contract-first)
- Dependencies form a DAG — no cycles
- Maximum decomposition depth: ${maxDepth}
- Strategy "${strategy}" guides the structure
- For hybrid human-AI markets: set assigneeType to "human" when the subtask requires human judgment`;

    const messages: ChatMessage[] = [
      { role: "system", content: systemPrompt },
      {
        role: "user",
        content: `Decompose this task:\n\nDescription: ${task.description}\nObjective: ${task.objective.expectedOutput}\nComplexity: ${task.characteristics.complexity}\nConstraints: ${JSON.stringify(task.characteristics.constraints ?? [])}`,
      },
    ];

    const response = await this.client!.chatCompletion(messages, {
      temperature: 0.2,
      responseFormat: { type: "json_object" },
    });

    const content = response.choices[0]?.message?.content;
    if (!content) throw new Error("Empty decomposition response");

    const parsed = JSON.parse(content) as {
      subtasks: Array<{
        description: string;
        expectedOutput: string;
        successCriteria: SuccessCriterion[];
        dependsOn: number[];
        complexity: TaskCharacteristics["complexity"];
        estimatedDuration?: number;
        assigneeType?: "human" | "ai";
      }>;
      strategy: DecompositionStrategy;
    };

    return buildPlan(task, parsed.subtasks, strategy, createSubtask);
  }

  decomposeManual(task: Task, strategy: DecompositionStrategy): DecompositionPlan {
    const subtask = createSubtask(task, {
      description: task.description,
      objective: task.objective,
      characteristics: { ...task.characteristics },
      dependencyIds: [],
    });

    return {
      rootTaskId: task.id,
      strategy,
      subtasks: [subtask],
      dependencyGraph: { [subtask.id]: [] },
    };
  }

  getExecutionOrder(graph: Record<string, string[]>): string[][] {
    return getExecutionOrder(graph);
  }
}
