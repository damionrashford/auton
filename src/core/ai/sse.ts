import type { ChatCompletionChunk } from "@/types/ai.js";

export async function* parseSSEStream(
  stream: ReadableStream<Uint8Array>
): AsyncGenerator<ChatCompletionChunk> {
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

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed === "" || trimmed.startsWith(":")) continue;
        if (trimmed === "data: [DONE]") return;
        if (trimmed.startsWith("data: ")) {
          const json = trimmed.slice(6);
          try {
            yield JSON.parse(json) as ChatCompletionChunk;
          } catch {
            /* skip malformed */
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
