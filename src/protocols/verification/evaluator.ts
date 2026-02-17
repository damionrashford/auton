// Criterion evaluation and LLM-based verification

import type {
  Task,
  TaskResult,
  SuccessCriterion,
  VerificationMethod,
} from "@/types/task/index.js";
import type { ChatMessage } from "@/types/ai.js";
import type { AIClient } from "@/core/ai/client.js";
import type { VerificationDetail, VerificationResult } from "@/protocols/verification/types.js";

export function evaluateCriterion(
  criterion: SuccessCriterion,
  result: TaskResult,
  extractValue: (output: unknown, metric: string) => unknown
): VerificationDetail {
  const actualValue = result.scores[criterion.metric] ?? extractValue(result.output, criterion.metric);
  let passed = false;
  let score = 0;

  if (actualValue !== undefined && actualValue !== null) {
    switch (criterion.operator) {
      case "eq":
        passed = actualValue === criterion.target;
        score = passed ? 1 : 0;
        break;
      case "neq":
        passed = actualValue !== criterion.target;
        score = passed ? 1 : 0;
        break;
      case "gt":
        passed = (actualValue as number) > (criterion.target as number);
        score = passed ? 1 : Math.max(0, (actualValue as number) / (criterion.target as number));
        break;
      case "gte":
        passed = (actualValue as number) >= (criterion.target as number);
        score = passed ? 1 : Math.max(0, (actualValue as number) / (criterion.target as number));
        break;
      case "lt":
        passed = (actualValue as number) < (criterion.target as number);
        score = passed ? 1 : 0;
        break;
      case "lte":
        passed = (actualValue as number) <= (criterion.target as number);
        score = passed ? 1 : 0;
        break;
      case "contains":
        passed = String(actualValue).includes(String(criterion.target));
        score = passed ? 1 : 0;
        break;
      case "matches":
        try {
          passed = new RegExp(String(criterion.target)).test(String(actualValue));
          score = passed ? 1 : 0;
        } catch {
          passed = false;
          score = 0;
        }
        break;
      case "custom":
        score = typeof actualValue === "number" ? actualValue : 0;
        passed = score >= 0.5;
        break;
    }
  }

  return {
    criterion,
    passed,
    actualValue,
    score,
    message: passed
      ? `${criterion.metric}: passed (${JSON.stringify(actualValue)} ${criterion.operator} ${JSON.stringify(criterion.target)})`
      : `${criterion.metric}: failed (${JSON.stringify(actualValue)} ${criterion.operator} ${JSON.stringify(criterion.target)})`,
  };
}

export function extractValue(output: unknown, metric: string): unknown {
  if (output === null || output === undefined) return undefined;
  if (typeof output === "object" && !Array.isArray(output)) {
    return (output as Record<string, unknown>)[metric];
  }
  return undefined;
}

export async function llmEvaluate(
  client: AIClient,
  task: Task,
  result: TaskResult,
  temperature: number = 0.3
): Promise<VerificationDetail> {
  const messages: ChatMessage[] = [
    {
      role: "system",
      content: `You are a task verification engine. Evaluate whether the output meets the task objective.
Return JSON: {"passed": boolean, "score": 0.0-1.0, "reason": "string"}`,
    },
    {
      role: "user",
      content: `Task: ${task.description}\nExpected: ${task.objective.expectedOutput}\nActual output: ${JSON.stringify(result.output)}\nSuccess: ${result.success}`,
    },
  ];

  try {
    const response = await client.chatCompletion(messages, {
      temperature,
      responseFormat: { type: "json_object" },
    });
    const content = response.choices[0]?.message?.content;
    if (content) {
      const parsed = JSON.parse(content) as { passed: boolean; score: number; reason: string };
      return {
        criterion: { metric: "llm_evaluation", operator: "gte", target: 0.5, weight: 0.3 },
        passed: parsed.passed,
        actualValue: parsed.score,
        score: parsed.score,
        message: `LLM evaluation: ${parsed.reason}`,
      };
    }
  } catch {
    /* fallback */
  }

  return {
    criterion: { metric: "llm_evaluation", operator: "gte", target: 0.5, weight: 0.1 },
    passed: result.success,
    actualValue: result.success ? 0.6 : 0.3,
    score: result.success ? 0.6 : 0.3,
    message: "LLM evaluation unavailable, using fallback",
  };
}

export function buildResult(
  method: VerificationMethod,
  details: VerificationDetail[]
): VerificationResult {
  const totalWeight = details.reduce((s, d) => s + d.criterion.weight, 0);
  const overallScore = totalWeight > 0
    ? details.reduce((s, d) => s + d.score * d.criterion.weight, 0) / totalWeight
    : 0;
  const allPassed = details.every((d) => d.passed || d.criterion.weight === 0);
  const verified = allPassed && overallScore >= 0.5;
  const confidence = Math.min(1, 0.3 + details.length * 0.1 + (verified ? 0.2 : 0));
  return {
    verified,
    confidence,
    method,
    details,
    overallScore,
    record: {
      method,
      verified,
      timestamp: Date.now(),
      confidence,
      evidence: { details, overallScore },
    },
  };
}
