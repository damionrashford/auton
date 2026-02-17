// ============================================================================
// MCP Legacy HTTP+SSE Transport — 2024-11-05 (deprecated)
// GET for SSE stream, endpoint event, POST to endpoint for messages
// ============================================================================

import type { MCPMessage, MCPResponse } from "@/mcp/types.js";
import type { MCPTransport } from "@/mcp/transportinterface.js";

export interface MCPSSETransportOptions {
  fetch?: typeof globalThis.fetch;
  timeout?: number;
}

async function* parseSSEEvents(stream: ReadableStream<Uint8Array>): AsyncGenerator<{ event?: string; data: string }> {
  const decoder = new TextDecoder();
  const reader = stream.getReader();
  let buffer = "";
  let currentEvent = "";
  let currentData = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed === "") {
          if (currentData) {
            yield { event: currentEvent || "message", data: currentData };
            currentEvent = "";
            currentData = "";
          }
        } else if (trimmed.startsWith("event: ")) {
          currentEvent = trimmed.slice(7).trim();
        } else if (trimmed.startsWith("data: ")) {
          currentData += (currentData ? "\n" : "") + trimmed.slice(6);
        }
      }
    }
    if (currentData) yield { event: currentEvent || "message", data: currentData };
  } finally {
    reader.releaseLock();
  }
}

export class MCPSSETransport implements MCPTransport {
  private url: string;
  private endpoint: string | null = null;
  private fetchFn: typeof globalThis.fetch;
  private timeout: number;
  private abortController: AbortController | null = null;
  private pending = new Map<string | number, { resolve: (r: MCPResponse) => void; reject: (e: Error) => void }>();
  private readPromise: Promise<void> | null = null;

  constructor(url: string | URL, options?: MCPSSETransportOptions) {
    this.url = typeof url === "string" ? url : url.toString();
    this.fetchFn = options?.fetch ?? fetch;
    this.timeout = options?.timeout ?? 60_000;
  }

  async start(): Promise<void> {
    this.abortController = new AbortController();
    const res = await this.fetchFn(this.url, {
      method: "GET",
      headers: { Accept: "text/event-stream" },
      signal: this.abortController.signal,
    });
    if (!res.ok || !res.body) throw new Error(`SSE GET failed: ${res.status}`);

    this.readPromise = (async () => {
      for await (const ev of parseSSEEvents(res.body!)) {
        if (ev.event === "endpoint") {
          const base = new URL(this.url);
          this.endpoint = new URL(ev.data.trim(), base.origin).toString();
        } else if (ev.event === "message" && ev.data && this.endpoint) {
          try {
            const msg = JSON.parse(ev.data) as MCPResponse;
            if ("id" in msg && msg.id !== undefined) {
              const p = this.pending.get(msg.id);
              if (p) {
                this.pending.delete(msg.id);
                p.resolve(msg);
              }
            }
          } catch {
            /* skip */
          }
        }
      }
    })();

    const deadline = Date.now() + 5000;
    while (!this.endpoint && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 50));
    }
    if (!this.endpoint) throw new Error("No endpoint event from SSE server");
  }

  async send(message: MCPMessage): Promise<MCPResponse> {
    if (!this.endpoint) throw new Error("MCP SSE transport not connected");

    const req = message as { id?: string | number };
    if (req.id === undefined) {
      await this.fetchFn(this.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(message),
      });
      return { jsonrpc: "2.0", id: 0, result: {} };
    }

    const controller = new AbortController();
    setTimeout(() => controller.abort(), this.timeout);

    await this.fetchFn(this.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message),
      signal: controller.signal,
    });

    const rid = req.id;
    return new Promise<MCPResponse>((resolve, reject) => {
      this.pending.set(rid, { resolve, reject });
      setTimeout(() => {
        if (this.pending.has(rid)) {
          this.pending.delete(rid);
          reject(new Error("MCP SSE request timeout"));
        }
      }, this.timeout);
    });
  }

  async close(): Promise<void> {
    this.abortController?.abort();
    this.endpoint = null;
    for (const { reject } of this.pending.values()) reject(new Error("Transport closed"));
    this.pending.clear();
    await this.readPromise;
  }
}
