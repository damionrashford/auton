"""Agentic loop -- the fully autonomous reasoning engine.

Orchestrates the conversation between the LLM (via OpenRouter) and the
external MCP tools (via MCPBridge). Supports progress reporting (via
FastMCP Context.report_progress) and OpenTelemetry span instrumentation.

All conversation store calls are ``await``-ed because the
NeonConversationStore is async (backed by Postgres).

OpenRouter features integrated in this loop:
  - Usage accounting (token counts, cost) extracted from every response
  - Reasoning tokens passed through in ChatMessage
  - Model fallbacks — the *actual* model used is tracked in ChatResponse
  - Conversation-level user tracking (conversation_id → user param)

Self-correction features:
  - Single tool retry on error
  - Stuck-loop detection (same tool + same args twice)
  - Consecutive failure tracking with strategy-change injection
  - Graceful degradation message on max iterations

Autonomous agent features:
  - Long-term memory recall injection at conversation start
  - Context window management with automatic compaction
  - Human-in-the-loop confirmation for write operations (ctx.elicit)
  - Multi-step planning for complex requests
  - Parallel tool execution for independent tool calls
  - Cost and token guardrails (per-conversation and daily limits)
  - Decision logging for full observability
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any

from fastmcp.server.elicitation import AcceptedElicitation

from fast_mcp_agent.agents.prompts import get_system_prompt
from fast_mcp_agent.agents.registry import AgentRegistry
from fast_mcp_agent.agents.roles import AgentConfig
from fast_mcp_agent.bridge import MCPBridge
from fast_mcp_agent.config import Settings
from fast_mcp_agent.core.llm import LLMClient, OpenRouterError
from fast_mcp_agent.core.safety import requires_confirmation
from fast_mcp_agent.core.tokenizer import count_messages_tokens
from fast_mcp_agent.models import (
    ChatMessage,
    ChatResponse,
    ChatRole,
    FunctionPayload,
    ToolCallPayload,
    UsageStats,
)
from fast_mcp_agent.telemetry import trace_llm_call, trace_tool_call

logger = logging.getLogger(__name__)

# Maximum consecutive tool failures before injecting a strategy-change message.
_MAX_CONSECUTIVE_FAILURES = 3


async def run_agent(
    user_message: str,
    bridge: MCPBridge,
    llm: LLMClient,
    store: Any,  # NeonConversationStore or _InMemoryShim
    settings: Settings,
    agent_config: AgentConfig,
    conversation_id: str | None = None,
    ctx: Any | None = None,
    memory_store: Any | None = None,
    headless: bool = False,
) -> ChatResponse:
    """Execute the full agentic loop for a single user turn.

    Parameters
    ----------
    user_message:
        The human's latest message.
    bridge:
        Connected MCPBridge (RivalSearch + Playwright + Google Workspace + internal tools).
    llm:
        Initialised LLMClient.
    store:
        NeonConversationStore for multi-turn persistence.
    settings:
        Application settings.
    agent_config:
        Agent role configuration — determines tool access, system prompt,
        and iteration limits.
    conversation_id:
        Optional existing conversation to continue.
    ctx:
        Optional FastMCP Context for logging and progress reporting
        via ``ctx.report_progress(progress, total)``.
    memory_store:
        Optional MemoryStore for long-term semantic memory.
    headless:
        If True, runs without user interaction (no confirmations).
        Used for cron job execution and delegated agent tasks.

    Returns
    -------
    ChatResponse with the final LLM answer, usage stats, and model used.
    """
    # Resolve role-specific system prompt
    system_prompt_content = (
        agent_config.system_prompt_override
        or get_system_prompt(agent_config.role)
    )

    cid, messages = await store.get_or_create(
        conversation_id,
        parent_conversation_id=agent_config.parent_conversation_id,
        agent_role=agent_config.role.value,
        system_prompt_override=system_prompt_content,
    )

    # ── Phase 1: Check daily cost guardrails ────────────────────────
    try:
        daily_cost = await store.get_daily_cost()
        if daily_cost >= settings.max_cost_per_day:
            return ChatResponse(
                reply=(
                    f"Daily cost limit reached (${daily_cost:.4f} / "
                    f"${settings.max_cost_per_day:.2f}). Please try again tomorrow."
                ),
                conversation_id=cid,
                iterations_used=0,
                tools_called=[],
                model_used=settings.xai_model,
                usage=UsageStats(),
            )
    except Exception:
        logger.warning("Failed to check daily cost", exc_info=True)

    # ── Phase 2: Memory recall injection ─────────────────────────────
    if memory_store is not None:
        try:
            recalled = await memory_store.recall(user_message, top_k=3)
            if recalled:
                memory_text = "Relevant memories from past conversations:\n"
                for i, mem in enumerate(recalled, 1):
                    memory_text += f"{i}. {mem['content'][:200]}\n"
                memory_msg = ChatMessage(
                    role=ChatRole.SYSTEM,
                    content=memory_text,
                )
                messages.append(memory_msg)
                await store.append(cid, memory_msg)
                logger.info("Injected %d memories into conversation.", len(recalled))
        except Exception:
            logger.warning("Memory recall failed", exc_info=True)

    # Append the new user message.
    user_msg = ChatMessage(role=ChatRole.USER, content=user_message)
    messages.append(user_msg)
    await store.append(cid, user_msg)

    # Prepare OpenAI-formatted tool schemas filtered by agent role.
    registry = AgentRegistry(settings)
    allowed_tools = registry.get_allowed_tools(agent_config.role, bridge.list_tool_names())
    openai_tools = bridge.get_openai_tools_filtered(allowed_tools)

    tools_called: list[str] = []
    max_iter = agent_config.max_iterations_override or settings.max_iterations

    # Resolve confirmation requirement
    require_confirmation = (
        agent_config.require_confirmation_override
        if agent_config.require_confirmation_override is not None
        else settings.require_confirmation
    )

    # Accumulate usage across all LLM calls in this agentic loop.
    total_usage = UsageStats()
    model_used = settings.xai_model

    # Self-correction state
    consecutive_failures = 0
    recent_tool_calls: deque[str] = deque(maxlen=5)  # Last 5 tool keys for stuck-loop detection

    # Planning state
    plan: list[dict[str, Any]] | None = None

    for iteration in range(1, max_iter + 1):
        # ── report progress via Context ─────────────────────────
        if ctx is not None:
            try:
                await ctx.report_progress(progress=iteration - 1, total=max_iter)
                await ctx.info(f"Agent iteration {iteration}/{max_iter}")
            except Exception:
                pass

        # ── Phase 3: Context window compaction ──────────────────
        try:
            token_count = count_messages_tokens(messages, model=settings.xai_model)
            ctx_window = settings.effective_context_window
            compaction_limit = int(ctx_window * settings.compaction_threshold)
            if token_count > compaction_limit:
                messages = await _compact_conversation(
                    messages, llm, store, cid, iteration, settings
                )
                logger.info(
                    "Conversation compacted: %d -> %d tokens",
                    token_count,
                    count_messages_tokens(messages, model=settings.xai_model),
                )
        except Exception:
            logger.warning("Context compaction failed", exc_info=True)

        # ── Phase 4: Multi-step planning (on first iteration) ────
        if iteration == 1 and plan is None and len(user_message) > 100:
            plan = await _generate_plan(user_message, llm, store, cid)
            if plan:
                logger.info("Generated plan with %d steps", len(plan))
                try:
                    await store.log_decision(
                        cid, iteration, "plan_generated", {"steps": plan}
                    )
                except Exception:
                    pass

                # Inject plan into conversation so the LLM follows it
                plan_text = "Multi-step execution plan:\n"
                for step in plan:
                    step_num = step.get("step", "?")
                    action = step.get("action", "")
                    tool_hint = step.get("tool_hint", "")
                    plan_text += f"{step_num}. {action}"
                    if tool_hint:
                        plan_text += f" (suggested tool: {tool_hint})"
                    plan_text += "\n"
                plan_text += "\nFollow this plan systematically."

                plan_msg = ChatMessage(
                    role=ChatRole.SYSTEM,
                    content=plan_text,
                )
                messages.append(plan_msg)
                await store.append(cid, plan_msg)

        # ── call LLM ────────────────────────────────────────────
        try:
            with trace_llm_call(settings.xai_model, len(messages)):
                data = await llm.chat_completion(
                    messages,
                    openai_tools or None,
                    conversation_id=cid,
                )
        except OpenRouterError as exc:
            logger.error(
                "OpenRouter error on iteration %d: %s", iteration, exc
            )
            try:
                await store.log_decision(
                    cid, iteration, "llm_error", {"error": str(exc)}
                )
            except Exception:
                pass
            return ChatResponse(
                reply=f"LLM request failed: {exc.message}",
                conversation_id=cid,
                iterations_used=iteration,
                tools_called=tools_called,
                model_used=model_used,
                usage=total_usage,
            )
        except Exception as exc:
            logger.exception("LLM call failed on iteration %d", iteration)
            return ChatResponse(
                reply=f"LLM request failed: {exc}",
                conversation_id=cid,
                iterations_used=iteration,
                tools_called=tools_called,
                model_used=model_used,
                usage=total_usage,
            )

        # ── extract usage stats ─────────────────────────────────
        iter_usage = UsageStats.from_response(data)
        total_usage = _accumulate_usage(total_usage, iter_usage)

        # ── Phase 5: Cost guardrails per-conversation ───────────
        try:
            conv_cost = await store.get_conversation_cost(cid)
            if conv_cost + (total_usage.cost or 0.0) >= settings.max_cost_per_conversation:
                await store.log_usage(cid, model_used, total_usage)
                return ChatResponse(
                    reply=(
                        f"Conversation cost limit reached (${conv_cost:.4f} / "
                        f"${settings.max_cost_per_conversation:.2f}). "
                        f"Please start a new conversation."
                    ),
                    conversation_id=cid,
                    iterations_used=iteration,
                    tools_called=tools_called,
                    model_used=model_used,
                    usage=total_usage,
                )
        except Exception:
            logger.warning("Failed to check conversation cost", exc_info=True)

        # ── Token guardrails ────────────────────────────────────
        if total_usage.total_tokens >= settings.max_tokens_per_conversation:
            await store.log_usage(cid, model_used, total_usage)
            return ChatResponse(
                reply=(
                    f"Token limit reached ({total_usage.total_tokens} / "
                    f"{settings.max_tokens_per_conversation}). "
                    f"Please start a new conversation."
                ),
                conversation_id=cid,
                iterations_used=iteration,
                tools_called=tools_called,
                model_used=model_used,
                usage=total_usage,
            )

        # Track the actual model used (may differ if fallbacks triggered).
        model_used = data.get("model", settings.xai_model)

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "")

        # ── extract reasoning tokens (if present) ───────────────
        reasoning_content = msg.get("reasoning")

        # ── final text response (no tool calls) ─────────────────
        raw_tool_calls = msg.get("tool_calls")
        if not raw_tool_calls or finish_reason == "stop":
            assistant_text = msg.get("content", "") or ""
            assistant_msg = ChatMessage(
                role=ChatRole.ASSISTANT,
                content=assistant_text,
                reasoning=reasoning_content,
            )
            messages.append(assistant_msg)
            await store.append(cid, assistant_msg)

            if ctx is not None:
                try:
                    await ctx.report_progress(progress=max_iter, total=max_iter)
                except Exception:
                    pass

            # Log final usage to Neon
            try:
                await store.log_usage(
                    conversation_id=cid,
                    model=model_used,
                    usage=total_usage,
                )
            except Exception:
                logger.warning("Failed to log usage stats to Neon", exc_info=True)

            return ChatResponse(
                reply=assistant_text,
                conversation_id=cid,
                iterations_used=iteration,
                tools_called=tools_called,
                model_used=model_used,
                usage=total_usage,
            )

        # ── process tool calls ──────────────────────────────────
        tool_call_payloads = _parse_tool_calls(raw_tool_calls)

        # Record assistant message with tool_calls attached.
        assistant_msg = ChatMessage(
            role=ChatRole.ASSISTANT,
            content=msg.get("content"),
            tool_calls=tool_call_payloads,
            reasoning=reasoning_content,
        )
        messages.append(assistant_msg)
        await store.append(cid, assistant_msg)

        # Log tool selection decision
        try:
            await store.log_decision(
                cid,
                iteration,
                "tools_selected",
                {
                    "tools": [tc.function.name for tc in tool_call_payloads],
                    "count": len(tool_call_payloads),
                },
            )
        except Exception:
            pass

        # ── Phase 6: Parallel tool execution ────────────────────
        tool_results = await _execute_tools_parallel(
            tool_call_payloads,
            bridge,
            store,
            cid,
            iteration,
            ctx,
            settings,
            recent_tool_calls,
            headless,
            require_confirmation,
            agent_config,
        )

        # Update state from results
        for tc, result_text, success, duration_ms in tool_results:
            fn_name = tc.function.name
            tools_called.append(fn_name)

            if not success:
                consecutive_failures += 1
            else:
                consecutive_failures = 0

            # Tool message
            tool_msg = ChatMessage(
                role=ChatRole.TOOL,
                content=result_text,
                tool_call_id=tc.id,
                name=fn_name,
            )
            messages.append(tool_msg)
            await store.append(cid, tool_msg)

            # Update recent_tool_calls for stuck-loop detection
            try:
                fn_args = json.loads(tc.function.arguments)
                recent_tool_calls.append(_make_tool_key(fn_name, fn_args))
            except Exception:
                pass

        # ── consecutive failure detection ───────────────────────
        if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
            strategy_msg = ChatMessage(
                role=ChatRole.SYSTEM,
                content=(
                    f"WARNING: {consecutive_failures} consecutive tool calls have "
                    "failed. You need to CHANGE STRATEGY. Consider:\n"
                    "- Using a completely different tool\n"
                    "- Searching with different keywords\n"
                    "- Trying a different website URL\n"
                    "- Answering based on information already gathered\n"
                    "- Admitting you cannot find the information"
                ),
            )
            messages.append(strategy_msg)
            await store.append(cid, strategy_msg)
            consecutive_failures = 0  # reset after warning

    # ── max iterations exhausted — graceful degradation ─────────
    # Log final usage even on exhaustion
    try:
        await store.log_usage(
            conversation_id=cid,
            model=model_used,
            usage=total_usage,
        )
    except Exception:
        logger.warning("Failed to log usage stats to Neon", exc_info=True)

    # Build a summary of what was accomplished
    summary_parts = [
        f"I reached the maximum of {max_iter} reasoning steps.",
    ]
    if tools_called:
        unique_tools = list(dict.fromkeys(tools_called))  # preserve order, deduplicate
        summary_parts.append(
            f"Tools used: {', '.join(unique_tools[:10])} "
            f"({len(tools_called)} total calls)."
        )
    summary_parts.append(
        "Here is what I have gathered so far. "
        "If you need more detail, please continue the conversation."
    )

    return ChatResponse(
        reply=" ".join(summary_parts),
        conversation_id=cid,
        iterations_used=max_iter,
        tools_called=tools_called,
        model_used=model_used,
        usage=total_usage,
    )


# ── helpers ─────────────────────────────────────────────────────────


async def _compact_conversation(
    messages: list[ChatMessage],
    llm: LLMClient,
    store: Any,
    conversation_id: str,
    iteration: int,
    settings: Settings,
) -> list[ChatMessage]:
    """Compact conversation by summarizing older messages.

    Keeps the system prompt and last N messages intact, summarizes the rest.
    """
    tail_count = settings.compaction_tail_messages

    if len(messages) <= tail_count + 1:
        return messages  # Not enough messages to compact

    # Split: system prompt + old messages + tail
    # Walk boundary backward to avoid splitting tool-call/result pairs
    system_msg = messages[0]  # Always the system prompt
    safe_tail_start = len(messages) - tail_count
    while safe_tail_start > 1 and safe_tail_start < len(messages):
        msg_at_boundary = messages[safe_tail_start]
        if msg_at_boundary.role == ChatRole.TOOL or (
            msg_at_boundary.tool_calls and len(msg_at_boundary.tool_calls) > 0
        ):
            safe_tail_start -= 1
        else:
            break

    if safe_tail_start <= 1:
        return messages  # Can't compact safely

    old_messages = messages[1:safe_tail_start]
    tail_messages = messages[safe_tail_start:]

    if len(old_messages) == 0:
        return messages  # Nothing to compact

    # Ask LLM to summarize old messages
    summary_prompt = [
        ChatMessage(
            role=ChatRole.SYSTEM,
            content=(
                "Summarize the following conversation history into a single "
                "compact paragraph, preserving key facts and context:"
            ),
        ),
        *old_messages,
    ]

    try:
        data = await llm.chat_completion(summary_prompt, tools=None)
        summary_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        if summary_text:
            summary_msg = ChatMessage(
                role=ChatRole.SYSTEM,
                content=f"[Previous conversation summary]: {summary_text}",
            )

            # Log decision
            try:
                await store.log_decision(
                    conversation_id,
                    iteration,
                    "compaction",
                    {
                        "original_count": len(messages),
                        "compacted_count": 1 + 1 + len(tail_messages),
                        "summary_length": len(summary_text),
                    },
                )
            except Exception:
                pass

            return [system_msg, summary_msg, *tail_messages]
    except Exception:
        logger.warning("Conversation compaction failed", exc_info=True)

    return messages


async def _generate_plan(
    user_message: str,
    llm: LLMClient,
    store: Any,
    conversation_id: str,
) -> list[dict[str, Any]] | None:
    """Generate a multi-step plan for complex requests."""
    planning_prompt = [
        ChatMessage(
            role=ChatRole.SYSTEM,
            content="""\
Analyze this request and create a brief execution plan if it's complex.
Output a JSON array of steps (3-7 steps max). Each step should have:
- "step": step number
- "action": description
- "tool_hint": suggested tool name

ONLY output the JSON array, no other text. If the request is simple, output an empty array [].""",
        ),
        ChatMessage(role=ChatRole.USER, content=user_message),
    ]

    try:
        data = await llm.chat_completion(planning_prompt, tools=None)
        plan_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Try to parse as JSON
        plan_text = plan_text.strip()
        if plan_text.startswith("```json"):
            plan_text = plan_text[7:]
        if plan_text.startswith("```"):
            plan_text = plan_text[3:]
        if plan_text.endswith("```"):
            plan_text = plan_text[:-3]
        plan_text = plan_text.strip()

        plan = json.loads(plan_text)
        if isinstance(plan, list) and len(plan) > 0:
            return plan
    except Exception:
        logger.debug("Plan generation failed or returned empty", exc_info=True)

    return None


async def _execute_tools_parallel(
    tool_calls: list[ToolCallPayload],
    bridge: MCPBridge,
    store: Any,
    conversation_id: str,
    iteration: int,
    ctx: Any,
    settings: Settings,
    recent_tool_calls: deque[str],
    headless: bool,
    require_confirmation: bool,
    agent_config: AgentConfig,
) -> list[tuple[ToolCallPayload, str, bool, int]]:
    """Execute tool calls in parallel when possible, sequentially when dependent."""
    # Heuristic: if all tool calls use different tools, run in parallel
    tool_names = [tc.function.name for tc in tool_calls]
    has_duplicates = len(tool_names) != len(set(tool_names))

    # If browser tools, run sequentially (they're stateful)
    has_browser = any("browser" in name or "pw_" in name for name in tool_names)

    if has_duplicates or has_browser or len(tool_calls) == 1:
        # Sequential execution
        results: list[tuple[ToolCallPayload, str, bool, int]] = []
        for tc in tool_calls:
            result = await _execute_single_tool(
                tc, bridge, store, conversation_id, iteration, ctx, settings,
                recent_tool_calls, headless, require_confirmation, agent_config,
            )
            results.append(result)
            # Update recent_tool_calls for next sequential call
            if result[2]:  # success
                try:
                    fn_args = json.loads(tc.function.arguments)
                    recent_tool_calls.append(_make_tool_key(tc.function.name, fn_args))
                except Exception:
                    pass
        return results

    # Parallel execution (with resilient exception handling)
    tasks = [
        _execute_single_tool(
            tc, bridge, store, conversation_id, iteration, ctx, settings,
            recent_tool_calls, headless, require_confirmation, agent_config,
        )
        for tc in tool_calls
    ]
    results_or_excs = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert any exceptions to error tuples
    final_results: list[tuple[ToolCallPayload, str, bool, int]] = []
    for i, result in enumerate(results_or_excs):
        if isinstance(result, BaseException):
            tc = tool_calls[i]
            logger.exception(
                "Parallel tool execution raised exception: %s", tc.function.name,
            )
            final_results.append((
                tc,
                f"[error] Tool execution failed: {result}",
                False,
                0,
            ))
        else:
            final_results.append(result)

    return final_results


async def _execute_single_tool(
    tc: ToolCallPayload,
    bridge: MCPBridge,
    store: Any,
    conversation_id: str,
    iteration: int,
    ctx: Any,
    settings: Settings,
    recent_tool_calls: deque[str],
    headless: bool,
    require_confirmation: bool,
    agent_config: AgentConfig,
) -> tuple[ToolCallPayload, str, bool, int]:
    """Execute a single tool call with confirmation, retry, timeout, and logging."""
    fn_name = tc.function.name

    try:
        fn_args: dict[str, Any] = json.loads(tc.function.arguments)
    except json.JSONDecodeError:
        fn_args = {}

    # ── stuck-loop detection (window of recent calls) ────
    current_tool_key = _make_tool_key(fn_name, fn_args)
    if current_tool_key in recent_tool_calls:
        logger.warning(
            "Stuck-loop detected: %s called with same args recently (last %d calls).",
            fn_name,
            len(recent_tool_calls),
        )
        return (
            tc,
            "[error] You recently called this tool with identical arguments. "
            "The approach is not working. Try a completely different strategy.",
            False,
            0,
        )

    logger.info("Tool call: %s(%s)", fn_name, fn_args)

    if ctx is not None:
        try:
            await ctx.info(f"Executing tool: {fn_name}")
        except Exception:
            pass

    # ── Confirmation gate (3 paths) ──────────────────────
    if require_confirmation and requires_confirmation(fn_name, fn_args):
        approved = False

        if ctx and not headless:
            # Path A: MCP context — use FastMCP elicitation
            try:
                await store.log_decision(
                    conversation_id, iteration,
                    "confirmation_requested",
                    {"tool": fn_name, "args": fn_args},
                )
                confirmation_result = await ctx.elicit(
                    message=(
                        f"The agent wants to execute: {fn_name}"
                        f"({json.dumps(fn_args, indent=2)})\n\n"
                        "Approve this action?"
                    ),
                    response_type=None,
                )
                approved = isinstance(confirmation_result, AcceptedElicitation)
                status = "approved" if approved else "declined"
                await store.log_decision(
                    conversation_id, iteration,
                    f"confirmation_{status}", {"tool": fn_name},
                )
            except Exception as exc:
                logger.warning("MCP elicitation failed: %s", exc)
                approved = True  # fall through on elicitation error

        elif agent_config.confirmation_callback is not None:
            # Path B: Slack/external callback
            try:
                await store.log_decision(
                    conversation_id, iteration,
                    "confirmation_requested",
                    {"tool": fn_name, "args": fn_args},
                )
                approved = await agent_config.confirmation_callback(
                    fn_name, fn_args,
                )
                status = "approved" if approved else "declined"
                await store.log_decision(
                    conversation_id, iteration,
                    f"confirmation_{status}", {"tool": fn_name},
                )
            except Exception as exc:
                logger.warning("Confirmation callback failed: %s", exc)
                approved = False  # deny on error for safety

        else:
            # Path C: No confirmation mechanism — block write ops
            logger.warning(
                "Write op %s blocked: no confirmation mechanism.",
                fn_name,
            )
            return (
                tc,
                f"[blocked] {fn_name} requires user approval but no "
                "confirmation mechanism is available.",
                False,
                0,
            )

        if not approved:
            return (
                tc,
                f"[declined] User did not approve {fn_name}. "
                "Try a different approach or ask for guidance.",
                False,
                0,
            )

    # Execute with timeout protection
    t0 = time.monotonic()
    success = True
    try:
        with trace_tool_call(fn_name, fn_args):
            result_text = await asyncio.wait_for(
                bridge.call_tool(fn_name, fn_args),
                timeout=settings.tool_timeout,
            )
    except TimeoutError:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.error("Tool '%s' timed out after %.0fs", fn_name, settings.tool_timeout)
        return (
            tc,
            f"[error] Tool '{fn_name}' timed out after {settings.tool_timeout:.0f} seconds. "
            "Try a different approach or break the task into smaller steps.",
            False,
            duration_ms,
        )

    duration_ms = int((time.monotonic() - t0) * 1000)

    if result_text.startswith("[error]"):
        success = False

        # ── single retry on error (also with timeout) ────
        logger.warning(
            "Tool '%s' failed, retrying once: %s",
            fn_name,
            result_text[:200],
        )
        t0_retry = time.monotonic()
        try:
            with trace_tool_call(fn_name, fn_args):
                retry_result = await asyncio.wait_for(
                    bridge.call_tool(fn_name, fn_args),
                    timeout=settings.tool_timeout,
                )
            retry_duration = int((time.monotonic() - t0_retry) * 1000)

            if not retry_result.startswith("[error]"):
                result_text = retry_result
                duration_ms += retry_duration
                success = True
                logger.info("Tool '%s' retry succeeded.", fn_name)
            else:
                duration_ms += retry_duration
                logger.warning("Tool '%s' retry also failed.", fn_name)
        except TimeoutError:
            retry_duration = int((time.monotonic() - t0_retry) * 1000)
            duration_ms += retry_duration
            logger.error("Tool '%s' retry also timed out.", fn_name)

    # Log tool call to Neon for analytics
    try:
        await store.log_tool_call(
            conversation_id=conversation_id,
            tool_name=fn_name,
            arguments=fn_args,
            result_text=result_text,
            duration_ms=duration_ms,
            success=success,
        )
    except Exception:
        logger.warning("Failed to log tool call to Neon", exc_info=True)

    return (tc, result_text, success, duration_ms)


def _parse_tool_calls(
    raw: list[dict[str, Any]],
) -> list[ToolCallPayload]:
    """Convert raw LLM tool_calls dicts into typed payloads."""
    payloads: list[ToolCallPayload] = []
    for tc in raw:
        fn = tc.get("function", {})
        payloads.append(
            ToolCallPayload(
                id=tc.get("id", ""),
                type=tc.get("type", "function"),
                function=FunctionPayload(
                    name=fn.get("name", ""),
                    arguments=fn.get("arguments", "{}"),
                ),
            )
        )
    return payloads


def _accumulate_usage(a: UsageStats, b: UsageStats) -> UsageStats:
    """Sum two UsageStats objects together.

    Cost is accumulated as well (may be None on some responses).
    """
    cost: float | None = None
    if a.cost is not None or b.cost is not None:
        cost = (a.cost or 0.0) + (b.cost or 0.0)

    return UsageStats(
        prompt_tokens=a.prompt_tokens + b.prompt_tokens,
        completion_tokens=a.completion_tokens + b.completion_tokens,
        total_tokens=a.total_tokens + b.total_tokens,
        cost=cost,
        reasoning_tokens=a.reasoning_tokens + b.reasoning_tokens,
        cached_tokens=a.cached_tokens + b.cached_tokens,
        cache_write_tokens=a.cache_write_tokens + b.cache_write_tokens,
    )


def _make_tool_key(fn_name: str, fn_args: dict[str, Any]) -> str:
    """Create a hashable key for stuck-loop detection."""
    try:
        sorted_args = json.dumps(fn_args, sort_keys=True)
    except (TypeError, ValueError):
        sorted_args = str(fn_args)
    return f"{fn_name}:{sorted_args}"
