import type { ChatCompletionResponse, ChatCompletionChunk, UsageStats } from "@/types/ai.js";

export async function collectStream(
  stream: AsyncGenerator<ChatCompletionChunk>
): Promise<ChatCompletionResponse> {
  let id = "";
  let model = "";
  let created = 0;
  let content = "";
  let finishReason: string = "stop";
  const toolCalls: Map<number, { id: string; name: string; arguments: string }> = new Map();
  let usage: UsageStats | undefined;

  for await (const chunk of stream) {
    if (!id) id = chunk.id;
    if (!model) model = chunk.model;
    if (!created) created = chunk.created;

    for (const choice of chunk.choices) {
      if (choice.finish_reason) finishReason = choice.finish_reason;

      if (choice.delta.content) {
        content += choice.delta.content;
      }

      if (choice.delta.tool_calls) {
        for (const tc of choice.delta.tool_calls) {
          const existing = toolCalls.get(tc.index);
          if (!existing) {
            toolCalls.set(tc.index, {
              id: tc.id ?? "",
              name: tc.function?.name ?? "",
              arguments: tc.function?.arguments ?? "",
            });
          } else {
            if (tc.id) existing.id = tc.id;
            if (tc.function?.name) existing.name += tc.function.name;
            if (tc.function?.arguments) existing.arguments += tc.function.arguments;
          }
        }
      }
    }

    if (chunk.usage) usage = chunk.usage;
  }

  const assembledToolCalls = toolCalls.size > 0
    ? Array.from(toolCalls.values()).map((tc) => ({
        id: tc.id,
        type: "function" as const,
        function: { name: tc.name, arguments: tc.arguments },
      }))
    : undefined;

  return {
    id,
    object: "chat.completion",
    created,
    model,
    choices: [
      {
        index: 0,
        message: {
          role: "assistant",
          content: content || null,
          tool_calls: assembledToolCalls,
        },
        finish_reason: finishReason as ChatCompletionResponse["choices"][0]["finish_reason"],
      },
    ],
    usage,
  };
}
