"""xAI LLM client using the official xai-sdk (gRPC).

Wraps ``xai_sdk.AsyncClient`` to provide chat completion, streaming,
and embedding capabilities via Grok models.  Returns responses in the
same OpenAI-compatible dict format the agent loop expects, so
``core/agent.py`` needs no changes to its response parsing.

Features:
  - Async chat completion (non-streaming and streaming)
  - Tool / function calling via xai_sdk.chat.tool
  - Reasoning models with configurable effort
  - Embeddings via xAI's OpenAI-compatible REST endpoint
  - Response normalization to OpenAI dict format
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from fast_mcp_agent.config import Settings
from fast_mcp_agent.models import ChatMessage, ChatRole

logger = logging.getLogger(__name__)


class LLMClient:
    """Async xAI chat completion client via xai-sdk."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any = None
        self._http: httpx.AsyncClient | None = None

    # ── lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Initialize the xAI AsyncClient."""
        from xai_sdk import AsyncClient

        self._client = AsyncClient(api_key=self._settings.xai_api_key)

        # httpx client for embedding endpoint (REST, not gRPC)
        self._http = httpx.AsyncClient(
            base_url="https://api.x.ai/v1",
            headers={
                "Authorization": f"Bearer {self._settings.xai_api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=15.0),
        )
        logger.info("LLMClient started (xai-sdk, model=%s)", self._settings.xai_model)

    async def stop(self) -> None:
        """Clean up resources."""
        if self._http:
            await self._http.aclose()
            self._http = None
        self._client = None
        logger.info("LLMClient stopped.")

    # ── chat completion (non-streaming) ────────────────────────────

    async def chat_completion(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        *,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request and return a normalized dict.

        The returned dict matches the OpenAI chat completion format so
        the agent loop in ``core/agent.py`` can parse it unchanged.
        """
        if self._client is None:
            raise RuntimeError("LLMClient.start() has not been called.")

        from xai_sdk.chat import tool as sdk_tool

        # Build chat kwargs
        chat_kwargs: dict[str, Any] = {
            "model": self._settings.xai_model,
        }
        if self._settings.xai_temperature is not None:
            chat_kwargs["temperature"] = self._settings.xai_temperature
        if self._settings.xai_max_tokens is not None:
            chat_kwargs["max_tokens"] = self._settings.xai_max_tokens
        if self._settings.xai_reasoning_effort:
            chat_kwargs["reasoning_effort"] = self._settings.xai_reasoning_effort

        # Convert tool schemas to xai_sdk tool objects
        sdk_tools = []
        if tools:
            for t in tools:
                fn = t.get("function", t)
                sdk_tools.append(
                    sdk_tool(
                        name=fn.get("name", ""),
                        description=fn.get("description", ""),
                        parameters=fn.get("parameters", {}),
                    )
                )
            chat_kwargs["tools"] = sdk_tools

        # Convert messages and build the chat
        sdk_messages = _convert_messages(messages)
        if sdk_messages:
            chat_kwargs["messages"] = [sdk_messages[0]]

        chat = self._client.chat.create(**chat_kwargs)

        # Append remaining messages
        for msg in sdk_messages[1:]:
            chat.append(msg)

        # Sample response
        try:
            response = await chat.sample()
        except Exception as exc:
            logger.error("xAI chat completion failed: %s", exc)
            raise XAIError(message=str(exc)) from exc

        # Normalize to OpenAI dict format
        return _normalize_response(response, self._settings.xai_model)

    # ── chat completion (streaming) ────────────────────────────────

    async def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        *,
        conversation_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream a chat completion response.

        Yields partial dicts with delta content for each chunk.
        The final yield includes full usage stats.
        """
        if self._client is None:
            raise RuntimeError("LLMClient.start() has not been called.")

        from xai_sdk.chat import tool as sdk_tool

        chat_kwargs: dict[str, Any] = {
            "model": self._settings.xai_model,
        }
        if self._settings.xai_temperature is not None:
            chat_kwargs["temperature"] = self._settings.xai_temperature
        if self._settings.xai_max_tokens is not None:
            chat_kwargs["max_tokens"] = self._settings.xai_max_tokens
        if self._settings.xai_reasoning_effort:
            chat_kwargs["reasoning_effort"] = self._settings.xai_reasoning_effort

        sdk_tools = []
        if tools:
            for t in tools:
                fn = t.get("function", t)
                sdk_tools.append(
                    sdk_tool(
                        name=fn.get("name", ""),
                        description=fn.get("description", ""),
                        parameters=fn.get("parameters", {}),
                    )
                )
            chat_kwargs["tools"] = sdk_tools

        sdk_messages = _convert_messages(messages)
        if sdk_messages:
            chat_kwargs["messages"] = [sdk_messages[0]]

        chat = self._client.chat.create(**chat_kwargs)
        for msg in sdk_messages[1:]:
            chat.append(msg)

        async for response, chunk in chat.stream():
            yield {
                "choices": [
                    {
                        "delta": {
                            "content": chunk.content or "",
                            "reasoning": getattr(chunk, "reasoning_content", None),
                        },
                    }
                ],
                "model": self._settings.xai_model,
                "usage": {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                    "total_tokens": getattr(response.usage, "total_tokens", 0),
                    "reasoning_tokens": getattr(response.usage, "reasoning_tokens", 0),
                },
            }

    # ── embeddings ─────────────────────────────────────────────────

    async def embed(
        self, texts: list[str], model: str | None = None
    ) -> list[list[float]]:
        """Generate embeddings via xAI's OpenAI-compatible REST endpoint.

        Uses https://api.x.ai/v1/embeddings (same format as OpenAI).
        """
        if self._http is None:
            raise RuntimeError("LLMClient.start() has not been called.")

        embedding_model = model or self._settings.xai_embedding_model
        payload = {"input": texts, "model": embedding_model}

        logger.debug(
            "Embedding request: model=%s, texts=%d",
            embedding_model,
            len(texts),
        )

        resp = await self._http.post("/embeddings", json=payload)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise XAIError(message=data["error"].get("message", "Embedding failed"))

        return [item["embedding"] for item in data["data"]]


# ── Exceptions ─────────────────────────────────────────────────────


class XAIError(Exception):
    """Raised when the xAI API returns an error."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"xAI error: {message}")


# Keep backward-compatible alias
OpenRouterError = XAIError


# ── helpers ────────────────────────────────────────────────────────


def _convert_messages(messages: list[ChatMessage]) -> list[Any]:
    """Convert our ChatMessage list to xai_sdk message objects."""
    from xai_sdk.chat import system, tool_result, user

    sdk_msgs: list[Any] = []

    for msg in messages:
        if msg.role == ChatRole.SYSTEM:
            sdk_msgs.append(system(msg.content or ""))
        elif msg.role == ChatRole.USER:
            sdk_msgs.append(user(msg.content or ""))
        elif msg.role == ChatRole.ASSISTANT:
            # Assistant messages are appended as the response from previous sample
            # We skip them here — they're part of the chat history managed by the SDK
            # But we need to represent them for the SDK's internal state
            sdk_msgs.append(
                _make_assistant_message(msg)
            )
        elif msg.role == ChatRole.TOOL:
            sdk_msgs.append(tool_result(msg.content or ""))

    return sdk_msgs


def _make_assistant_message(msg: ChatMessage) -> Any:
    """Create an SDK-compatible assistant message placeholder.

    The xai_sdk manages assistant messages internally via chat.append(response).
    For conversation replay, we construct a minimal representation.
    """
    from xai_sdk.chat import system

    # The SDK doesn't have a direct assistant() constructor.
    # For conversation history replay, we use the system role as a workaround
    # with a prefix to distinguish it. The SDK's chat.create() with messages
    # handles the actual conversation state.
    content = msg.content or ""
    if msg.tool_calls:
        tc_data = [
            {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]
        content += f"\n[tool_calls: {json.dumps(tc_data)}]"
    # Return as a system message tagged as assistant context
    return system(f"[Previous assistant response]: {content}")


def _normalize_response(response: Any, model: str) -> dict[str, Any]:
    """Convert an xai_sdk response object to OpenAI-compatible dict.

    This keeps the agent loop's response parsing code unchanged.
    """
    # Build tool_calls if present
    tool_calls = None
    if response.tool_calls:
        tool_calls = []
        for tc in response.tool_calls:
            tool_calls.append(
                {
                    "id": getattr(tc, "id", "") or "",
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
            )

    # Determine finish reason
    finish_reason = "tool_calls" if tool_calls else "stop"

    # Build usage dict
    usage: dict[str, Any] = {}
    if hasattr(response, "usage") and response.usage:
        usage = {
            "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
            "completion_tokens": getattr(
                response.usage, "completion_tokens", 0
            ),
            "total_tokens": getattr(response.usage, "total_tokens", 0),
            "completion_tokens_details": {
                "reasoning_tokens": getattr(
                    response.usage, "reasoning_tokens", 0
                ),
            },
        }

    return {
        "choices": [
            {
                "message": {
                    "content": response.content,
                    "tool_calls": tool_calls,
                    "reasoning": getattr(response, "reasoning_content", None),
                },
                "finish_reason": finish_reason,
            }
        ],
        "model": model,
        "usage": usage,
    }
