"""Token counting using tiktoken for context window management.

Provides accurate token counting for OpenAI-compatible models used via
OpenRouter, enabling conversation compaction when approaching context limits.
"""

from __future__ import annotations

import logging
from typing import Any

import tiktoken

from fast_mcp_agent.models import ChatMessage

logger = logging.getLogger(__name__)

# Per-message overhead (OpenAI tokenization spec)
_MESSAGE_OVERHEAD = 4
_REPLY_PRIMING = 2


def _get_encoder(model: str) -> tiktoken.Encoding:
    """Get tiktoken encoder for model, stripping provider prefix if present.

    Args:
        model: Model name (may include provider prefix like "openai/gpt-4o").

    Returns:
        Tiktoken encoder for the model (or cl100k_base fallback).
    """
    # Strip provider prefix (e.g. "openai/gpt-4o" → "gpt-4o") for tiktoken
    base_model = model.split("/", 1)[-1] if "/" in model else model

    try:
        return tiktoken.encoding_for_model(base_model)
    except KeyError:
        # Fallback to cl100k_base for unknown models (GPT-4/3.5/Claude compatible)
        logger.warning(
            "Model '%s' not found in tiktoken registry. Using cl100k_base encoding.",
            base_model,
        )
        return tiktoken.get_encoding("cl100k_base")


def count_messages_tokens(
    messages: list[ChatMessage], model: str = "gpt-4o"
) -> int:
    """Count tokens for a list of messages using tiktoken.

    Args:
        messages: List of ChatMessage objects.
        model: Model name for tokenizer selection (default: gpt-4o).

    Returns:
        Total token count including message overhead.
    """
    enc = _get_encoder(model)

    total = 0

    for msg in messages:
        total += _MESSAGE_OVERHEAD

        # Count role
        if msg.role:
            total += len(enc.encode(msg.role))

        # Count content
        if msg.content:
            total += len(enc.encode(msg.content))

        # Count name
        if msg.name:
            total += len(enc.encode(msg.name))

        # Count tool_call_id
        if msg.tool_call_id:
            total += len(enc.encode(msg.tool_call_id))

        # Count tool_calls
        if msg.tool_calls:
            for tc in msg.tool_calls:
                total += len(enc.encode(tc.function.name))
                total += len(enc.encode(tc.function.arguments))

    # Reply priming
    total += _REPLY_PRIMING

    return total


def count_text_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens in a plain text string.

    Args:
        text: Input text.
        model: Model name for tokenizer selection.

    Returns:
        Token count.
    """
    enc = _get_encoder(model)
    return len(enc.encode(text))


def estimate_tool_schema_tokens(
    tools: list[dict[str, Any]], model: str = "gpt-4o"
) -> int:
    """Estimate token overhead for tool schemas in function-calling.

    Args:
        tools: List of OpenAI-format tool schemas.
        model: Model name for tokenizer selection.

    Returns:
        Estimated token count for tool schemas.
    """
    # Rough heuristic: JSON-encode all tools and count tokens
    # This is an approximation; actual tokenization depends on provider
    import json

    tools_json = json.dumps(tools)
    return count_text_tokens(tools_json, model)
