// Agent Loop — Execution Engine

import type { ChatMessage, AssistantMessage } from "@/types/ai.js";
import type { Task, TaskResult, ResourceBudget } from "@/types/task/index.js";
import type { AgentProfile } from "@/types/agent.js";
import { AIClient } from "@/core/ai/client.js";
import type { Monitor } from "@/protocols/monitoring/index.js";
import type { SecurityManager } from "@/protocols/security/index.js";
import type { ToolExecutor } from "@/core/agent/types.js";
import { buildSystemPrompt } from "@/core/agent/prompt.js";
import { executeToolCalls } from "@/core/agent/tools.js";

export type { ToolHandler, ToolExecutor } from "@/core/agent/types.js";

export interface AgentLoopConfig {
  agent: AgentProfile;
  toolExecutor?: ToolExecutor;
  monitor?: Monitor;
  securityManager?: SecurityManager;
  maxIterations?: number;
  parallelToolCalls?: boolean;
  signal?: AbortSignal;
  budget?: ResourceBudget;
}

export class AgentLoop {
  private readonly config: AgentLoopConfig;
  private readonly client: AIClient;

  constructor(config: AgentLoopConfig) {
    this.config = { maxIterations: 20, parallelToolCalls: true, ...config };

    const modelConfig = config.agent.modelConfig;
    if (!modelConfig) {
      throw new Error(`Agent ${config.agent.id} has no modelConfig — cannot run agent loop`);
    }

    this.client = new AIClient({
      baseURL: modelConfig.baseURL,
      apiKey: modelConfig.apiKey,
      defaultModel: modelConfig.model,
      defaultHeaders: modelConfig.headers,
    });
  }

  async run(task: Task): Promise<TaskResult> {
    const startTime = Date.now();
    let tokensUsed = 0;
    const { agent, toolExecutor, monitor, securityManager, maxIterations, parallelToolCalls, signal, budget } =
      this.config;

    monitor?.startMonitoring(task.id, agent.id, "continuous", budget);

    const basePrompt = agent.modelConfig?.systemPrompt ?? "You are a capable AI assistant.";
    const systemPrompt = buildSystemPrompt(task, basePrompt);
    const messages: ChatMessage[] = [
      { role: "system", content: systemPrompt },
      { role: "user", content: task.description },
    ];

    const tools = agent.tools.length > 0 ? agent.tools : undefined;
    let iterations = 0;

    try {
      while (iterations < maxIterations!) {
        iterations++;

        const maxTokens = budget?.maxTokens
          ? Math.min(budget.maxTokens - tokensUsed, agent.modelConfig?.maxTokens ?? 4096)
          : agent.modelConfig?.maxTokens;

        const response = await this.client.chatCompletion(messages, {
          model: agent.modelConfig?.model,
          tools,
          parallelToolCalls,
          temperature: agent.modelConfig?.temperature,
          maxTokens: maxTokens && maxTokens > 0 ? maxTokens : undefined,
          signal,
        });

        const choice = response.choices[0];
        if (!choice) throw new Error("Empty response from model");

        const { message, finish_reason } = choice;

        if (response.usage) {
          tokensUsed += response.usage.total_tokens;
          monitor?.recordEvent(task.id, agent.id, "token_usage", {
            tokens: response.usage.total_tokens,
            promptTokens: response.usage.prompt_tokens,
            completionTokens: response.usage.completion_tokens,
          });
        }

        if (budget?.maxTokens && tokensUsed >= budget.maxTokens) {
          monitor?.recordEvent(task.id, agent.id, "task_failed", {
            error: `Token budget exceeded (${tokensUsed} >= ${budget.maxTokens})`,
          });
          monitor?.stopMonitoring(task.id);
          return { success: false, output: null, scores: {}, executionTime: Date.now() - startTime, tokensUsed, error: `Token budget exceeded (${tokensUsed} >= ${budget.maxTokens})` };
        }

        if (budget?.maxDuration && Date.now() - startTime >= budget.maxDuration) {
          monitor?.recordEvent(task.id, agent.id, "task_failed", {
            error: `Duration budget exceeded (${Date.now() - startTime}ms >= ${budget.maxDuration}ms)`,
          });
          monitor?.stopMonitoring(task.id);
          return { success: false, output: null, scores: {}, executionTime: Date.now() - startTime, tokensUsed, error: `Duration budget exceeded` };
        }

        messages.push(message);

        if (finish_reason === "stop" || finish_reason === "length" || finish_reason === "content_filter") {
          const content = message.content ?? "";
          monitor?.recordEvent(task.id, agent.id, "task_completed", { success: true, output: content });
          monitor?.stopMonitoring(task.id);
          return { success: true, output: content, scores: {}, executionTime: Date.now() - startTime, tokensUsed };
        }

        if (finish_reason === "tool_calls" && message.tool_calls?.length && toolExecutor) {
          const toolResults = await executeToolCalls(
            agent,
            message.tool_calls,
            toolExecutor,
            securityManager,
            this.config.parallelToolCalls ?? true
          );

          for (const tr of toolResults) {
            messages.push({ role: "tool", tool_call_id: tr.tool_call_id, content: tr.content });
            monitor?.recordEvent(task.id, agent.id, "tool_called", { toolName: tr.toolName, toolCallId: tr.tool_call_id });
          }
        } else if (finish_reason === "tool_calls" && (!toolExecutor || !message.tool_calls?.length)) {
          monitor?.recordEvent(task.id, agent.id, "task_failed", {
            error: "Model requested tool calls but no tool executor or no tool calls provided",
          });
          monitor?.stopMonitoring(task.id);
          return { success: false, output: null, scores: {}, executionTime: Date.now() - startTime, tokensUsed, error: "Model requested tool calls but no tool executor configured" };
        }
      }

      monitor?.recordEvent(task.id, agent.id, "task_failed", {
        error: `Max iterations (${maxIterations}) exceeded`,
      });
      monitor?.stopMonitoring(task.id);

      return {
        success: false,
        output: (messages[messages.length - 1] as AssistantMessage)?.content ?? null,
        scores: {},
        executionTime: Date.now() - startTime,
        tokensUsed,
        error: `Max iterations (${maxIterations}) exceeded`,
      };
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      monitor?.recordEvent(task.id, agent.id, "task_failed", { error: errorMessage });
      monitor?.stopMonitoring(task.id);
      return {
        success: false,
        output: null,
        scores: {},
        executionTime: Date.now() - startTime,
        tokensUsed,
        error: errorMessage,
      };
    }
  }
}

export interface CreateAgentLoopOptions {
  agent: AgentProfile;
  toolExecutor?: ToolExecutor;
  monitor?: Monitor;
  securityManager?: SecurityManager;
  maxIterations?: number;
  parallelToolCalls?: boolean;
  budget?: ResourceBudget;
}

export function createAgentLoop(options: CreateAgentLoopOptions): AgentLoop {
  return new AgentLoop(options);
}
