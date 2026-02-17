// ============================================================================
// AI Chat API — Message, Content & Tool Types
// ============================================================================

export interface SystemMessage {
  role: "system";
  content: string;
  name?: string;
}

export interface UserMessage {
  role: "user";
  content: string | ContentPart[];
  name?: string;
}

export interface AssistantMessage {
  role: "assistant";
  content: string | null;
  name?: string;
  tool_calls?: ToolCall[];
  refusal?: string | null;
}

export interface ToolMessage {
  role: "tool";
  content: string;
  tool_call_id: string;
}

export type ChatMessage = SystemMessage | UserMessage | AssistantMessage | ToolMessage;

export interface TextContentPart {
  type: "text";
  text: string;
}

export interface ImageContentPart {
  type: "image_url";
  image_url: {
    url: string;
    detail?: "auto" | "low" | "high";
  };
}

export type ContentPart = TextContentPart | ImageContentPart;

export interface FunctionDefinition {
  name: string;
  description?: string;
  parameters?: JsonSchema;
  strict?: boolean;
}

export interface ToolDefinition {
  type: "function";
  function: FunctionDefinition;
}

export interface ToolCall {
  id: string;
  type: "function";
  function: {
    name: string;
    arguments: string;
  };
}

export type ToolChoice =
  | "auto"
  | "none"
  | "required"
  | { type: "function"; function: { name: string } };

export interface JsonSchema {
  type?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  enum?: (string | number | boolean | null)[];
  description?: string;
  default?: unknown;
  additionalProperties?: boolean | JsonSchema;
  oneOf?: JsonSchema[];
  anyOf?: JsonSchema[];
  allOf?: JsonSchema[];
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  const?: unknown;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  minItems?: number;
  maxItems?: number;
  format?: string;
}

export type ResponseFormat =
  | { type: "text" }
  | { type: "json_object" }
  | {
      type: "json_schema";
      json_schema: {
        name: string;
        description?: string;
        schema: JsonSchema;
        strict?: boolean;
      };
    };
