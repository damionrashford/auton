// ============================================================================
// MCP Client — Connect to any MCP server (zero deps)
// Supports: Streamable HTTP, stdio, legacy SSE
// ============================================================================

import type {
  MCPTool,
  MCPCallToolResult,
  MCPResource,
  MCPReadResourceResult,
  MCPPrompt,
  MCPGetPromptResult,
} from "@/mcp/types.js";
import type { MCPTransport } from "@/mcp/transportinterface.js";
import { MCPStreamableHTTPTransport } from "@/mcp/transport.js";
import { MCPStdioTransport } from "@/mcp/transportstdio.js";
import { MCPSSETransport } from "@/mcp/transportsse.js";

export interface MCPClientConfig {
  /** Use a specific transport */
  transport?: MCPTransport;
  /** Server URL (for Streamable HTTP or SSE; used when transport not provided) */
  url?: string | URL;
  /** stdio: command + args (Node.js only) */
  stdio?: { command: string; args?: string[]; cwd?: string; env?: Record<string, string> };
  /** Client name */
  clientName?: string;
  /** Client version */
  clientVersion?: string;
  /** MCP protocol version */
  protocolVersion?: string;
  /** Custom fetch (HTTP transports) */
  fetch?: typeof globalThis.fetch;
  /** Request timeout (ms) */
  timeout?: number;
}

let requestId = 0;
function nextId(): number {
  return ++requestId;
}

function hasStart(t: MCPTransport): t is MCPTransport & { start(): Promise<void> } {
  return typeof (t as { start?: () => Promise<void> }).start === "function";
}

/** MCP Client — connect to any MCP server */
export class MCPClient {
  private transport: MCPTransport;
  private clientName: string;
  private clientVersion: string;
  private protocolVersion: string;
  private initialized = false;

  constructor(config: MCPClientConfig) {
    if (config.transport) {
      this.transport = config.transport;
    } else if (config.stdio) {
      this.transport = new MCPStdioTransport(config.stdio);
    } else if (config.url) {
      this.transport = new MCPStreamableHTTPTransport(config.url, {
        fetch: config.fetch,
        timeout: config.timeout,
      });
    } else {
      throw new Error("MCPClient requires transport, url, or stdio config");
    }
    this.clientName = config.clientName ?? "intelligent-delegation-client";
    this.clientVersion = config.clientVersion ?? "1.0.0";
    this.protocolVersion = config.protocolVersion ?? "2024-11-05";
  }

  /** Connect and perform MCP initialization handshake */
  async connect(): Promise<void> {
    if (hasStart(this.transport)) await this.transport.start();

    const id = nextId();
    const initResult = await this.transport.send({
      jsonrpc: "2.0",
      id,
      method: "initialize",
      params: {
        protocolVersion: this.protocolVersion,
        capabilities: {},
        clientInfo: { name: this.clientName, version: this.clientVersion },
      },
    });

    if ("error" in initResult) throw new Error(`MCP init failed: ${initResult.error.message}`);

    await this.transport.send({
      jsonrpc: "2.0",
      method: "notifications/initialized",
    });

    this.initialized = true;
  }

  async listTools(): Promise<{ tools: MCPTool[] }> {
    this.ensureConnected();
    const res = await this.transport.send({
      jsonrpc: "2.0",
      id: nextId(),
      method: "tools/list",
      params: {},
    });
    if ("error" in res) throw new Error(res.error.message);
    return { tools: (res.result.tools as MCPTool[]) ?? [] };
  }

  async callTool(name: string, args: Record<string, unknown> = {}): Promise<MCPCallToolResult> {
    this.ensureConnected();
    const res = await this.transport.send({
      jsonrpc: "2.0",
      id: nextId(),
      method: "tools/call",
      params: { name, arguments: args },
    });
    if ("error" in res) throw new Error(res.error.message);
    return res.result as unknown as MCPCallToolResult;
  }

  async listResources(): Promise<{ resources: MCPResource[] }> {
    this.ensureConnected();
    const res = await this.transport.send({
      jsonrpc: "2.0",
      id: nextId(),
      method: "resources/list",
      params: {},
    });
    if ("error" in res) throw new Error(res.error.message);
    return { resources: (res.result.resources as MCPResource[]) ?? [] };
  }

  async readResource(uri: string): Promise<MCPReadResourceResult> {
    this.ensureConnected();
    const res = await this.transport.send({
      jsonrpc: "2.0",
      id: nextId(),
      method: "resources/read",
      params: { uri },
    });
    if ("error" in res) throw new Error(res.error.message);
    return res.result as unknown as MCPReadResourceResult;
  }

  async listPrompts(): Promise<{ prompts: MCPPrompt[] }> {
    this.ensureConnected();
    const res = await this.transport.send({
      jsonrpc: "2.0",
      id: nextId(),
      method: "prompts/list",
      params: {},
    });
    if ("error" in res) throw new Error(res.error.message);
    return { prompts: (res.result.prompts as MCPPrompt[]) ?? [] };
  }

  async getPrompt(name: string, args: Record<string, string> = {}): Promise<MCPGetPromptResult> {
    this.ensureConnected();
    const res = await this.transport.send({
      jsonrpc: "2.0",
      id: nextId(),
      method: "prompts/get",
      params: { name, arguments: args },
    });
    if ("error" in res) throw new Error(res.error.message);
    return res.result as unknown as MCPGetPromptResult;
  }

  async close(): Promise<void> {
    await this.transport.close();
    this.initialized = false;
  }

  private ensureConnected(): void {
    if (!this.initialized) throw new Error("MCPClient not connected. Call connect() first.");
  }
}

/** Connect with auto-detection: try Streamable HTTP, then legacy SSE on 400/404/405 */
export async function connectWithAutoDetect(
  url: string | URL,
  options?: { clientName?: string; clientVersion?: string; fetch?: typeof fetch; timeout?: number }
): Promise<MCPClient> {
  const baseUrl = typeof url === "string" ? url : url.toString();
  const fetchFn = options?.fetch ?? fetch;

  try {
    const transport = new MCPStreamableHTTPTransport(baseUrl, {
      fetch: fetchFn,
      timeout: options?.timeout ?? 60_000,
    });
    const client = new MCPClient({
      transport,
      clientName: options?.clientName,
      clientVersion: options?.clientVersion,
    });
    await client.connect();
    return client;
  } catch (e) {
    const status = e instanceof Error ? e.message : String(e);
    if (/400|404|405/.test(status)) {
      const sseTransport = new MCPSSETransport(baseUrl, {
        fetch: fetchFn,
        timeout: options?.timeout ?? 60_000,
      });
      const client = new MCPClient({
        transport: sseTransport,
        clientName: options?.clientName,
        clientVersion: options?.clientVersion,
      });
      await client.connect();
      return client;
    }
    throw e;
  }
}
