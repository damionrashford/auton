// OpenAI-Compatible HTTP Client — Zero Dependencies

import type {
  ChatCompletionRequest,
  ChatCompletionResponse,
  ChatCompletionChunk,
  ChatMessage,
  ToolDefinition,
  ToolChoice,
  ResponseFormat,
  AIClientConfig,
} from "@/types/ai.js";
import { parseSSEStream } from "@/core/ai/sse.js";
import { AIError } from "@/core/ai/error.js";
import { rawRequest } from "@/core/ai/http.js";
import { collectStream as collectStreamFn } from "@/core/ai/collect.js";

export { AIError } from "@/core/ai/error.js";

export class AIClient {
  private readonly baseURL: string;
  private readonly apiKey: string;
  private readonly defaultModel: string;
  private readonly defaultHeaders: Record<string, string>;
  private readonly timeout: number;
  private readonly maxRetries: number;
  private readonly retryDelay: number;

  constructor(config: AIClientConfig) {
    this.baseURL = config.baseURL.replace(/\/+$/, "");
    this.apiKey = config.apiKey;
    this.defaultModel = config.defaultModel ?? "gpt-4o";
    this.defaultHeaders = config.defaultHeaders ?? {};
    this.timeout = config.timeout ?? 120_000;
    this.maxRetries = config.maxRetries ?? 2;
    this.retryDelay = config.retryDelay ?? 1000;
  }

  async chatCompletion(
    messages: ChatMessage[],
    options: {
      model?: string;
      tools?: ToolDefinition[];
      toolChoice?: ToolChoice;
      parallelToolCalls?: boolean;
      responseFormat?: ResponseFormat;
      temperature?: number;
      maxTokens?: number;
      stop?: string | string[];
      seed?: number;
      user?: string;
      signal?: AbortSignal;
    } = {}
  ): Promise<ChatCompletionResponse> {
    const body: ChatCompletionRequest = {
      model: options.model ?? this.defaultModel,
      messages,
      stream: false,
    };

    if (options.tools?.length) {
      body.tools = options.tools;
      body.tool_choice = options.toolChoice ?? "auto";
      if (options.parallelToolCalls !== undefined) {
        body.parallel_tool_calls = options.parallelToolCalls;
      }
    }
    if (options.responseFormat) body.response_format = options.responseFormat;
    if (options.temperature !== undefined) body.temperature = options.temperature;
    if (options.maxTokens !== undefined) body.max_tokens = options.maxTokens;
    if (options.stop) body.stop = options.stop;
    if (options.seed !== undefined) body.seed = options.seed;
    if (options.user) body.user = options.user;

    return this.request<ChatCompletionResponse>(
      "/v1/chat/completions",
      body,
      options.signal
    );
  }

  async *chatCompletionStream(
    messages: ChatMessage[],
    options: {
      model?: string;
      tools?: ToolDefinition[];
      toolChoice?: ToolChoice;
      parallelToolCalls?: boolean;
      responseFormat?: ResponseFormat;
      temperature?: number;
      maxTokens?: number;
      stop?: string | string[];
      seed?: number;
      includeUsage?: boolean;
      signal?: AbortSignal;
    } = {}
  ): AsyncGenerator<ChatCompletionChunk> {
    const body: ChatCompletionRequest = {
      model: options.model ?? this.defaultModel,
      messages,
      stream: true,
    };

    if (options.includeUsage) {
      body.stream_options = { include_usage: true };
    }
    if (options.tools?.length) {
      body.tools = options.tools;
      body.tool_choice = options.toolChoice ?? "auto";
      if (options.parallelToolCalls !== undefined) {
        body.parallel_tool_calls = options.parallelToolCalls;
      }
    }
    if (options.responseFormat) body.response_format = options.responseFormat;
    if (options.temperature !== undefined) body.temperature = options.temperature;
    if (options.maxTokens !== undefined) body.max_tokens = options.maxTokens;
    if (options.stop) body.stop = options.stop;
    if (options.seed !== undefined) body.seed = options.seed;

    const response = await this.rawRequest("/v1/chat/completions", body, options.signal);

    if (!response.body) {
      throw new AIError("No response body for streaming request", 0);
    }

    yield* parseSSEStream(response.body);
  }

  async collectStream(
    messages: ChatMessage[],
    options: Parameters<AIClient["chatCompletionStream"]>[1] = {}
  ): Promise<ChatCompletionResponse> {
    const stream = this.chatCompletionStream(messages, { ...options, includeUsage: true });
    return collectStreamFn(stream);
  }

  private async request<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
    const response = await rawRequest(
      this.baseURL,
      this.apiKey,
      this.defaultHeaders,
      this.timeout,
      this.maxRetries,
      this.retryDelay,
      path,
      body,
      signal
    );
    return response.json() as Promise<T>;
  }

  private async rawRequest(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
    return rawRequest(
      this.baseURL,
      this.apiKey,
      this.defaultHeaders,
      this.timeout,
      this.maxRetries,
      this.retryDelay,
      path,
      body,
      signal
    );
  }
}
