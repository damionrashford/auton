// ============================================================================
// AI Chat API — Completion Request/Response & Client Config
// ============================================================================

import type { AssistantMessage, ChatMessage, ToolDefinition, ToolChoice, ResponseFormat } from "@/types/aimessages.js";

export interface ChatCompletionRequest {
  model: string;
  messages: ChatMessage[];
  tools?: ToolDefinition[];
  tool_choice?: ToolChoice;
  parallel_tool_calls?: boolean;
  response_format?: ResponseFormat;
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  max_completion_tokens?: number;
  stop?: string | string[];
  frequency_penalty?: number;
  presence_penalty?: number;
  seed?: number;
  n?: number;
  stream?: boolean;
  stream_options?: { include_usage?: boolean };
  logprobs?: boolean;
  top_logprobs?: number;
  user?: string;
}

export interface ChatCompletionChoice {
  index: number;
  message: AssistantMessage;
  finish_reason: FinishReason;
  logprobs?: LogprobsResult | null;
}

export type FinishReason = "stop" | "length" | "tool_calls" | "content_filter" | "function_call";

export interface ChatCompletionResponse {
  id: string;
  object: "chat.completion";
  created: number;
  model: string;
  choices: ChatCompletionChoice[];
  usage?: UsageStats;
  system_fingerprint?: string;
}

export interface UsageStats {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  prompt_tokens_details?: { cached_tokens?: number };
  completion_tokens_details?: { reasoning_tokens?: number };
}

export interface LogprobsResult {
  content: LogprobToken[] | null;
}

export interface LogprobToken {
  token: string;
  logprob: number;
  bytes: number[] | null;
  top_logprobs: { token: string; logprob: number; bytes: number[] | null }[];
}

export interface ChatCompletionChunk {
  id: string;
  object: "chat.completion.chunk";
  created: number;
  model: string;
  choices: ChatCompletionChunkChoice[];
  usage?: UsageStats | null;
  system_fingerprint?: string;
}

export interface ChatCompletionChunkChoice {
  index: number;
  delta: DeltaMessage;
  finish_reason: FinishReason | null;
  logprobs?: LogprobsResult | null;
}

export interface DeltaMessage {
  role?: "assistant";
  content?: string | null;
  tool_calls?: DeltaToolCall[];
  refusal?: string | null;
}

export interface DeltaToolCall {
  index: number;
  id?: string;
  type?: "function";
  function?: {
    name?: string;
    arguments?: string;
  };
}

export interface AIClientConfig {
  baseURL: string;
  apiKey: string;
  defaultModel?: string;
  defaultHeaders?: Record<string, string>;
  timeout?: number;
  maxRetries?: number;
  retryDelay?: number;
}
