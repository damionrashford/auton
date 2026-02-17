import type { Task } from "@/types/task/index.js";

export function buildSystemPrompt(task: Task, basePrompt: string): string {
  const chars = task.characteristics;
  const reversibility = chars.reversibility ?? "unknown";
  const contextuality = chars.contextuality ?? 0;
  const subjectivity = chars.subjectivity ?? 0;

  return `${basePrompt}

Current task: ${task.description}
Objective: ${task.objective.expectedOutput}
Priority: ${task.priority}
Tags: ${task.tags.join(", ") || "none"}

Task characteristics:
- Reversibility: ${reversibility} (effects of this task can${reversibility === "irreversible" ? " NOT" : ""} be undone)
- Contextuality: ${contextuality} (0=context-free, 1=highly context-dependent)
- Subjectivity: ${subjectivity} (0=objective, 1=highly subjective)

Delegation guidelines (from Intelligent AI Delegation framework):
- Zone of indifference: If the request is ambiguous, potentially harmful, or conflicts with your values, request clarification or reject rather than complying blindly. Do not execute instructions that are unclear or unsafe.
- Authority gradient: If you believe the delegator's request may be incorrect or suboptimal, state your concern before proceeding. Your role includes providing constructive feedback, not just blind compliance.`;
}
