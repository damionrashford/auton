// ============================================================================
// AI Chat Completions API — Full Type Definitions
// Compatible with: OpenAI, vLLM, Ollama, Together AI, LM Studio, Groq, xAI, etc.
// ============================================================================

export type {
  SystemMessage,
  UserMessage,
  AssistantMessage,
  ToolMessage,
  ChatMessage,
  TextContentPart,
  ImageContentPart,
  ContentPart,
  FunctionDefinition,
  ToolDefinition,
  ToolCall,
  ToolChoice,
  JsonSchema,
  ResponseFormat,
} from "@/types/aimessages.js";

export type {
  ChatCompletionRequest,
  ChatCompletionChoice,
  FinishReason,
  ChatCompletionResponse,
  UsageStats,
  LogprobsResult,
  LogprobToken,
  ChatCompletionChunk,
  ChatCompletionChunkChoice,
  DeltaMessage,
  DeltaToolCall,
  AIClientConfig,
} from "@/types/aicompletion.js";
