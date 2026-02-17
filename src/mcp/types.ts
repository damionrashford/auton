// ============================================================================
// MCP Protocol Types — Model Context Protocol (zero deps)
// Based on https://modelcontextprotocol.io/specification
// ============================================================================

/** JSON-RPC 2.0 request */
export interface MCPRequest {
  jsonrpc: "2.0";
  id: string | number;
  method: string;
  params?: Record<string, unknown>;
}

/** JSON-RPC 2.0 notification (no id) */
export interface MCPNotification {
  jsonrpc: "2.0";
  method: string;
  params?: Record<string, unknown>;
}

/** JSON-RPC 2.0 result response */
export interface MCPResultResponse {
  jsonrpc: "2.0";
  id: string | number;
  result: Record<string, unknown>;
}

/** JSON-RPC 2.0 error response */
export interface MCPErrorResponse {
  jsonrpc: "2.0";
  id?: string | number;
  error: { code: number; message: string; data?: unknown };
}

export type MCPResponse = MCPResultResponse | MCPErrorResponse;
export type MCPMessage = MCPRequest | MCPNotification | MCPResponse;

/** MCP Tool definition */
export interface MCPTool {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
}

/** MCP Tool call result content item */
export interface MCPTextContent {
  type: "text";
  text: string;
}

export interface MCPResourceLinkContent {
  type: "resource_link";
  uri: string;
  name?: string;
  mimeType?: string;
  description?: string;
}

export type MCPToolResultContent = MCPTextContent | MCPResourceLinkContent;

/** MCP Tool call result */
export interface MCPCallToolResult {
  content: MCPToolResultContent[];
  isError?: boolean;
  structuredContent?: unknown;
}

/** MCP Resource template */
export interface MCPResource {
  uri: string;
  name?: string;
  description?: string;
  mimeType?: string;
}

/** MCP Resource content */
export interface MCPResourceContent {
  uri: string;
  mimeType?: string;
  text?: string;
  blob?: string;
}

/** MCP Read resource result */
export interface MCPReadResourceResult {
  contents: MCPResourceContent[];
}

/** MCP Prompt template */
export interface MCPPrompt {
  name: string;
  description?: string;
  arguments?: Array<{ name: string; description?: string; required?: boolean }>;
}

/** MCP Prompt message */
export interface MCPPromptMessage {
  role: "user" | "assistant";
  content: { type: "text"; text: string };
}

/** MCP Get prompt result */
export interface MCPGetPromptResult {
  messages: MCPPromptMessage[];
}

export const MCP_PROTOCOL_VERSION = "2024-11-05";
