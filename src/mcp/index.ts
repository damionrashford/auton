// ============================================================================
// MCP — Model Context Protocol (zero deps)
// ============================================================================

export type {
  MCPTool,
  MCPCallToolResult,
  MCPResource,
  MCPReadResourceResult,
  MCPPrompt,
  MCPGetPromptResult,
  MCPToolResultContent,
  MCPMessage,
  MCPResponse,
} from "@/mcp/types.js";

export type { MCPTransport } from "@/mcp/transportinterface.js";
export { MCPStreamableHTTPTransport } from "@/mcp/transport.js";
export type { MCPStreamableHTTPTransportOptions } from "@/mcp/transport.js";
export { MCPStdioTransport } from "@/mcp/transportstdio.js";
export type { MCPStdioTransportConfig } from "@/mcp/transportstdio.js";
export { MCPSSETransport } from "@/mcp/transportsse.js";
export type { MCPSSETransportOptions } from "@/mcp/transportsse.js";

export { MCPClient, connectWithAutoDetect } from "@/mcp/client.js";
export type { MCPClientConfig } from "@/mcp/client.js";
