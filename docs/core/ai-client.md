# AI Client

OpenAI-compatible HTTP client with zero dependencies. Supports OpenAI, vLLM, Ollama, Together AI, LM Studio, Groq, xAI, and any API that follows the OpenAI chat completions format.

## Features

- **Non-streaming** — `chatCompletion()` for standard request/response
- **Streaming** — `chatCompletionStream()` for SSE chunks
- **Collect stream** — `collectStream()` assembles deltas into a full response
- **Tool calling** — Tools, `tool_choice`, parallel tool calls
- **Structured output** — `response_format: { type: "json_object" }`
- **Retries** — Automatic retry on 429 and 5xx
- **Abort** — `AbortSignal` support for cancellation

## Usage

```typescript
import { AIClient, AIError } from "auton";

const client = new AIClient({
  baseURL: "https://api.openai.com/v1",
  apiKey: process.env.OPENAI_API_KEY!,
  defaultModel: "gpt-4o",
  timeout: 120_000,
  maxRetries: 2,
});

// Non-streaming
const response = await client.chatCompletion([
  { role: "system", content: "You are a helpful assistant." },
  { role: "user", content: "Hello!" },
], {
  temperature: 0.7,
  maxTokens: 1024,
});

// Streaming
for await (const chunk of client.chatCompletionStream(messages)) {
  // Process chunk.choices[0].delta
}

// Collect stream into full response
const full = await client.collectStream(messages, { includeUsage: true });
```

## Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `baseURL` | string | — | API base URL (trailing slashes removed) |
| `apiKey` | string | — | Bearer token |
| `defaultModel` | string | `"gpt-4o"` | Model when not specified per request |
| `defaultHeaders` | Record | `{}` | Extra headers |
| `timeout` | number | `120_000` | Request timeout (ms) |
| `maxRetries` | number | `2` | Retries on 429/5xx |
| `retryDelay` | number | `1000` | Base delay between retries (ms) |

## Error Handling

```typescript
import { AIError } from "auton";

try {
  await client.chatCompletion(messages);
} catch (err) {
  if (err instanceof AIError) {
    console.log(err.status, err.body);
  }
}
```

`AIError` extends `Error` with `status` (HTTP status) and `body` (response body string).

## Tool Calling

```typescript
const response = await client.chatCompletion(messages, {
  tools: [
    {
      type: "function",
      function: {
        name: "get_weather",
        description: "Get weather for a location",
        parameters: {
          type: "object",
          properties: { location: { type: "string" } },
          required: ["location"],
        },
      },
    },
  ],
  tool_choice: "auto",
  parallelToolCalls: true,
});
```

## See Also

- [Agent Loop](./agent-loop.md) — Uses AIClient for task execution
- [Task Decomposition](../protocols/task-decomposition.md) — Uses AIClient for AI-assisted decomposition
