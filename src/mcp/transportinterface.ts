// ============================================================================
// MCP Transport Interface — Common contract for all transports
// ============================================================================

import type { MCPMessage, MCPResponse } from "@/mcp/types.js";

/** Transport that can send MCP messages and receive responses */
export interface MCPTransport {
  /** Send a message; for requests, returns the response */
  send(message: MCPMessage): Promise<MCPResponse>;
  /** Close the transport */
  close(): Promise<void>;
}
