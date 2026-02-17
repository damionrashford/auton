import { AIError } from "@/core/ai/error.js";

export async function rawRequest(
  baseURL: string,
  apiKey: string,
  defaultHeaders: Record<string, string>,
  timeout: number,
  maxRetries: number,
  retryDelay: number,
  path: string,
  body: unknown,
  signal?: AbortSignal
): Promise<Response> {
  const url = `${baseURL}${path}`;
  let lastError: Error | undefined;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (attempt > 0) {
      await new Promise((r) => setTimeout(r, retryDelay * attempt));
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    if (signal) {
      signal.addEventListener("abort", () => controller.abort(), { once: true });
    }

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
          ...defaultHeaders,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorBody = await response.text().catch(() => "");
        const err = new AIError(
          `HTTP ${response.status}: ${errorBody}`,
          response.status,
          errorBody
        );
        if (response.status === 429 || response.status >= 500) {
          lastError = err;
          continue;
        }
        throw err;
      }

      return response;
    } catch (e) {
      clearTimeout(timeoutId);
      if (e instanceof AIError) throw e;
      lastError = e instanceof Error ? e : new Error(String(e));
      if (signal?.aborted) throw lastError;
    }
  }

  throw lastError ?? new Error("Request failed after retries");
}
