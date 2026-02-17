// ============================================================================
// MCP stdio Transport — Spawn process, newline-delimited JSON (Node.js)
// Messages: JSON-RPC over stdin/stdout, newline-delimited
// ============================================================================

import { spawn } from "node:child_process";
import type { MCPMessage, MCPResponse } from "@/mcp/types.js";
import type { MCPTransport } from "@/mcp/transportinterface.js";

export interface MCPStdioTransportConfig {
  /** Command to run (e.g. "node", "npx") */
  command: string;
  /** Arguments (e.g. ["server.js"]) */
  args?: string[];
  /** Working directory */
  cwd?: string;
  /** Environment overrides */
  env?: Record<string, string>;
}

function serializeMessage(msg: MCPMessage): string {
  return JSON.stringify(msg) + "\n";
}

/** stdio transport — spawns server process, communicates via stdin/stdout */
export class MCPStdioTransport implements MCPTransport {
  private process: ReturnType<typeof spawn> | null = null;
  private config: MCPStdioTransportConfig;
  private buffer = "";
  private pending = new Map<string | number, { resolve: (r: MCPResponse) => void; reject: (e: Error) => void }>();

  constructor(config: MCPStdioTransportConfig) {
    this.config = config;
  }

  async send(message: MCPMessage): Promise<MCPResponse> {
    if (!this.process?.stdin) throw new Error("MCP stdio transport not started");

    const req = message as { id?: string | number };
    if (req.id === undefined) {
      this.process.stdin.write(serializeMessage(message));
      return { jsonrpc: "2.0", id: 0, result: {} };
    }

    const rid = req.id;
    return new Promise<MCPResponse>((resolve, reject) => {
      this.pending.set(rid, { resolve, reject });
      this.process!.stdin!.write(serializeMessage(message));
    });
  }

  async start(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.process = spawn(this.config.command, this.config.args ?? [], {
        stdio: ["pipe", "pipe", "inherit"],
        cwd: this.config.cwd,
        env: { ...process.env, ...this.config.env },
      });

      this.process.on("error", (err: Error) => {
        reject(err);
        for (const { reject: r } of this.pending.values()) r(err);
        this.pending.clear();
      });

      this.process.on("spawn", () => resolve());

      this.process.stdout!.on("data", (chunk: Buffer | string) => {
        this.buffer += typeof chunk === "string" ? chunk : chunk.toString("utf8");
        this.processBuffer();
      });

      this.process.on("close", (code: number | null) => {
        this.process = null;
        if (this.pending.size > 0) {
          const err = new Error(`Process exited with code ${code}`);
          for (const { reject: r } of this.pending.values()) r(err);
          this.pending.clear();
        }
      });
    });
  }

  private processBuffer(): void {
    const idx = this.buffer.indexOf("\n");
    if (idx === -1) return;
    const line = this.buffer.slice(0, idx).replace(/\r$/, "");
    this.buffer = this.buffer.slice(idx + 1);
    try {
      const msg = JSON.parse(line) as MCPResponse;
      if ("id" in msg && msg.id !== undefined) {
        const pending = this.pending.get(msg.id);
        if (pending) {
          this.pending.delete(msg.id);
          pending.resolve(msg);
        }
      }
    } catch {
      // Skip malformed
    }
    if (this.buffer.includes("\n")) this.processBuffer();
  }

  async close(): Promise<void> {
    if (this.process) {
      const p = this.process;
      this.process = null;
      p.stdin?.end();
      await new Promise<void>((r) => p.once("close", r));
      try {
        if (p.exitCode === null) p.kill("SIGTERM");
      } catch {
        // ignore
      }
    }
  }
}
