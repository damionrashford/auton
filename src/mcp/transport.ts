// ============================================================================
// MCP Streamable HTTP Transport — Zero Dependencies
// POST for requests, JSON or SSE for responses (2025+ spec)
// ============================================================================

import type { MCPMessage, MCPResponse } from "@/mcp/types.js";
import type { MCPTransport } from "@/mcp/transportinterface.js";

export interface MCPStreamableHTTPTransportOptions {
  /** Custom fetch (e.g. for Node 18+) */
  fetch?: typeof globalThis.fetch;
  /** Request timeout (ms) */
  timeout?: number;
}

/** Parse SSE stream into JSON-RPC messages (zero deps) */
async function* parseSSE(stream: ReadableStream<Uint8Array>): AsyncGenerator<MCPResponse> {
  const decoder = new TextDecoder();
  const reader = stream.getReader();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      let eventData = "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed === "" && eventData) {
          const parsed = JSON.parse(eventData) as MCPResponse;
          if ("result" in parsed || "error" in parsed) yield parsed;
          eventData = "";
        } else if (trimmed.startsWith("data: ")) {
          const data = trimmed.slice(6);
          if (data !== "[DONE]") eventData += (eventData ? "\n" : "") + data;
        }
      }
      if (eventData) {
        try {
          const parsed = JSON.parse(eventData) as MCPResponse;
          if ("result" in parsed || "error" in parsed) yield parsed;
        } catch {
          // Incomplete chunk, keep in buffer
          buffer = `data: ${eventData}\n` + buffer;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** Streamable HTTP transport for MCP (modern spec) */
export class MCPStreamableHTTPTransport implements MCPTransport {
  private url: string;
  private fetchFn: typeof globalThis.fetch;
  private timeout: number;
  private sessionId?: string;

  constructor(url: string | URL, options?: MCPStreamableHTTPTransportOptions) {
    this.url = typeof url === "string" ? url : url.toString();
    this.fetchFn = options?.fetch ?? fetch;
    this.timeout = options?.timeout ?? 60_000;
  }

  getSessionId(): string | undefined {
    return this.sessionId;
  }

  async send(request: MCPMessage): Promise<MCPResponse> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      "mcp-protocol-version": "2024-11-05",
    };
    if (this.sessionId) headers["mcp-session-id"] = this.sessionId;

    const response = await this.fetchFn(this.url, {
      method: "POST",
      headers,
      body: JSON.stringify(request),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    const newSessionId = response.headers.get("mcp-session-id");
    if (newSessionId) this.sessionId = newSessionId;

    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(`MCP HTTP ${response.status}: ${text || response.statusText}`);
    }

    if (response.status === 202) {
      const req = request as { id?: string | number };
      if (req.id === undefined) return { jsonrpc: "2.0", id: 0, result: {} };
      throw new Error("Server returned 202 for request; SSE GET not yet supported");
    }

    const contentType = response.headers.get("content-type") ?? "";

    if (contentType.includes("text/event-stream") && response.body) {
      for await (const msg of parseSSE(response.body)) {
        if ("id" in msg && msg.id === (request as { id: string | number }).id) return msg;
      }
      throw new Error("No matching response in SSE stream");
    }

    if (contentType.includes("application/json")) {
      return (await response.json()) as MCPResponse;
    }

    throw new Error(`Unexpected content-type: ${contentType}`);
  }

  async close(): Promise<void> {
    if (this.sessionId) {
      try {
        await this.fetchFn(this.url, {
          method: "DELETE",
          headers: { "mcp-session-id": this.sessionId },
        });
      } catch {
        // Ignore
      }
      this.sessionId = undefined;
    }
  }
}
