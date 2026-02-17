import type { ToolCall } from "@/types/ai.js";
import type { AgentProfile } from "@/types/agent.js";
import type { SecurityManager } from "@/protocols/security/index.js";
import type { ToolExecutor } from "@/core/agent/types.js";

export async function executeToolCalls(
  agent: AgentProfile,
  toolCalls: ToolCall[],
  toolExecutor: ToolExecutor,
  securityManager: SecurityManager | undefined,
  parallel: boolean
): Promise<Array<{ tool_call_id: string; content: string; toolName: string }>> {
  const results: Array<{ tool_call_id: string; content: string; toolName: string }> = [];

  const executeOne = async (tc: ToolCall) => {
    const toolName = tc.function.name;
    const argsStr = tc.function.arguments;
    const permissions = agent.basePermissions.flatMap((p) => p.actions);

    if (securityManager) {
      const threat = securityManager.validateToolCall(agent.id, toolName, argsStr, permissions);
      if (threat) {
        return {
          tool_call_id: tc.id,
          content: JSON.stringify({
            error: "Tool call blocked by security policy",
            threat: threat.threatType,
            message: threat.description,
          }),
          toolName,
        };
      }
    }

    const handler = toolExecutor[toolName];
    if (!handler) {
      return {
        tool_call_id: tc.id,
        content: JSON.stringify({ error: `Unknown tool: ${toolName}` }),
        toolName,
      };
    }

    let args: Record<string, unknown> = {};
    try {
      args = argsStr.trim() ? (JSON.parse(argsStr) as Record<string, unknown>) : {};
    } catch {
      return {
        tool_call_id: tc.id,
        content: JSON.stringify({ error: `Invalid JSON arguments: ${argsStr}` }),
        toolName,
      };
    }

    try {
      const result = await handler(args);
      return {
        tool_call_id: tc.id,
        content: typeof result === "string" ? result : JSON.stringify(result),
        toolName,
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        tool_call_id: tc.id,
        content: JSON.stringify({ error: msg }),
        toolName,
      };
    }
  };

  if (parallel) {
    const settled = await Promise.all(toolCalls.map(executeOne));
    results.push(...settled);
  } else {
    for (const tc of toolCalls) {
      results.push(await executeOne(tc));
    }
  }

  return results;
}
