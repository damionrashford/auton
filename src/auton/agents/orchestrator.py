"""Orchestrator agent — decomposes tasks and delegates to specialist workers.

The orchestrator never executes tools directly (except ``memory_recall``).
Instead it calls ``delegate_to_*`` tools which spawn specialist agents via
``run_agent()`` with role-specific ``AgentConfig`` instances.

For simple requests that the LLM decomposes into zero subtasks the
orchestrator runs as a RESEARCH agent by default so the user still
gets a useful answer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from auton.agents.registry import AgentRegistry
from auton.agents.roles import (
    AgentRole,
    DelegationResult,
    DelegationTask,
)
from auton.core.llm import LLMClient
from auton.models import (
    ChatMessage,
    ChatResponse,
    ChatRole,
    DelegationSummary,
    UsageStats,
)

if TYPE_CHECKING:
    from auton.bridge import MCPBridge
    from auton.config import Settings

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """Orchestrator that decomposes tasks and delegates to specialist agents."""

    def __init__(
        self,
        bridge: MCPBridge,
        llm: LLMClient,
        store: Any,  # NeonConversationStore or _InMemoryShim
        settings: Settings,
        registry: AgentRegistry,
    ) -> None:
        self._bridge = bridge
        self._llm = llm
        self._store = store
        self._settings = settings
        self._registry = registry

    # ── main entry point ─────────────────────────────────────────

    async def run(
        self,
        user_message: str,
        conversation_id: str | None = None,
        ctx: Any | None = None,
        memory_store: Any | None = None,
        confirmation_callback: Any | None = None,
    ) -> ChatResponse:
        """Decompose, delegate, synthesise.

        If decomposition yields zero tasks the request is simple — we
        fall back to running a RESEARCH agent directly.

        Args:
            confirmation_callback: Async callback for write-op approval
                from Slack (or other external UI).
        """
        from auton.core.agent import run_agent

        self._confirmation_callback = confirmation_callback

        cid = conversation_id or uuid.uuid4().hex[:12]

        # Phase 1 — decompose
        tasks = await self.decompose_task(user_message, cid)

        if not tasks:
            # Simple request — run as research agent directly
            logger.info("No delegation needed — running as research agent.")
            research_config = self._registry.get_config(AgentRole.RESEARCH)
            research_config.confirmation_callback = confirmation_callback
            return await run_agent(
                user_message=user_message,
                bridge=self._bridge,
                llm=self._llm,
                store=self._store,
                settings=self._settings,
                agent_config=research_config,
                conversation_id=cid,
                ctx=ctx,
                memory_store=memory_store,
            )

        if ctx is not None:
            try:
                roles = [t.target_role.value for t in tasks]
                await ctx.info(
                    f"Orchestrator delegating to {len(tasks)} agents: {roles}"
                )
            except Exception:
                pass

        # Phase 2 — execute
        results = await self.execute_tasks(tasks)

        # Phase 3 — synthesise
        synthesized = await self.synthesize_results(user_message, results, cid)

        # Build aggregate stats
        delegations = [
            DelegationSummary(
                task_id=r.task_id,
                target_role=r.target_role.value,
                instruction=tasks[i].instruction if i < len(tasks) else "",
                success=r.success,
                iterations_used=r.iterations_used,
                tools_called=r.tools_called,
                cost=r.cost,
            )
            for i, r in enumerate(results)
        ]
        total_cost = sum(r.cost for r in results)
        total_iters = sum(r.iterations_used for r in results)
        all_tools: list[str] = []
        for r in results:
            all_tools.extend(r.tools_called)

        return ChatResponse(
            reply=synthesized,
            conversation_id=cid,
            iterations_used=total_iters,
            tools_called=all_tools,
            model_used=self._settings.xai_model,
            usage=UsageStats(cost=total_cost),
            delegations=delegations,
            agent_role=AgentRole.ORCHESTRATOR.value,
        )

    # ── task decomposition ───────────────────────────────────────

    async def decompose_task(
        self,
        user_message: str,
        conversation_id: str,
    ) -> list[DelegationTask]:
        """Use the LLM to split *user_message* into specialist subtasks.

        Returns an empty list when the request is simple enough for a
        single agent.
        """
        decomposition_prompt = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content="""\
Analyse the user's request and decompose it into subtasks for specialist agents.

Available agents:

"research" — Has 10 RivalSearchMCP tools + Playwright browser:
  web_search, social_search (Reddit/HN/Dev.to/ProductHunt/Medium), \
news_aggregation (Google/DuckDuckGo/Yahoo News), github_search, \
scientific_research (papers/datasets), content_operations (retrieve/analyze URLs), \
map_website, document_analysis (PDF/Word/OCR), research_topic (end-to-end workflow), \
research_agent (autonomous AI research). Plus read-only browser and memory.

"browser" — Playwright interactive: click, type, fill forms, scroll, tabs, \
screenshots, PDF save. For web apps that need interaction.

"communication" — Slack (send/read/search messages, channels, threads, files), \
Gmail (send/draft/search/read emails), Google Chat (spaces, messages).

"workspace" — Google Calendar, Drive, Docs, Sheets, Slides, Forms, Tasks, \
Contacts, Apps Script. Full CRUD on all services.

"blockchain" — Coinbase AgentKit: wallet balance/transfers, token swaps, \
DeFi (Aave supply/borrow/repay), NFT mint/transfer, Superfluid streaming, \
.base.eth names, Pyth price feeds. ALL actions require user confirmation.

Output a JSON array of tasks:
[
  {"target_role": "research", "instruction": "...", "context": {}, "parallel": true},
  ...
]

Rules:
- Set "parallel": true if the task is independent of others.
- Set "parallel": false if the task depends on a previous result.
- If the request only needs web search/browsing, return an EMPTY array [].
- Maximum 5 subtasks.
- Only output the JSON array, nothing else.""",
            ),
            ChatMessage(
                role=ChatRole.USER,
                content=user_message,
            ),
        ]

        try:
            data = await self._llm.chat_completion(decomposition_prompt, tools=None)
            plan_text = (
                data.get("choices", [{}])[0].get("message", {}).get("content", "")
            )

            plan_text = plan_text.strip()
            if plan_text.startswith("```json"):
                plan_text = plan_text[7:]
            if plan_text.startswith("```"):
                plan_text = plan_text[3:]
            if plan_text.endswith("```"):
                plan_text = plan_text[:-3]
            plan_text = plan_text.strip()

            tasks_raw = json.loads(plan_text)

            if not isinstance(tasks_raw, list):
                logger.warning("Decomposition returned non-list: %s", type(tasks_raw))
                return []

            tasks: list[DelegationTask] = []
            for t in tasks_raw:
                role_str = t.get("target_role", "")
                try:
                    target_role = AgentRole(role_str)
                except ValueError:
                    logger.warning("Unknown agent role in plan: %s", role_str)
                    continue

                tasks.append(
                    DelegationTask(
                        task_id=uuid.uuid4().hex[:8],
                        target_role=target_role,
                        instruction=t.get("instruction", ""),
                        context=t.get("context", {}),
                        parent_conversation_id=conversation_id,
                        max_iterations=t.get("max_iterations", 10),
                        parallel=t.get("parallel", True),
                    )
                )

            logger.info(
                "Decomposed into %d tasks: %s",
                len(tasks),
                [t.target_role.value for t in tasks],
            )
            return tasks

        except Exception:
            logger.warning("Task decomposition failed", exc_info=True)
            return []

    # ── execution ────────────────────────────────────────────────

    async def execute_tasks(
        self,
        tasks: list[DelegationTask],
    ) -> list[DelegationResult]:
        """Run independent tasks in parallel, dependent ones sequentially."""
        parallel_tasks = [t for t in tasks if t.parallel]
        sequential_tasks = [t for t in tasks if not t.parallel]

        results: list[DelegationResult] = []

        # Run parallel tasks first
        if parallel_tasks:
            coros = [self.execute_single_task(t) for t in parallel_tasks]
            parallel_results = await asyncio.gather(*coros, return_exceptions=True)
            for i, r in enumerate(parallel_results):
                if isinstance(r, BaseException):
                    task = parallel_tasks[i]
                    logger.exception("Parallel task %s failed", task.task_id)
                    results.append(
                        DelegationResult(
                            task_id=task.task_id,
                            target_role=task.target_role,
                            success=False,
                            result="",
                            conversation_id="",
                            error=str(r),
                        )
                    )
                else:
                    results.append(r)

        # Then sequential tasks
        for task in sequential_tasks:
            result = await self.execute_single_task(task)
            results.append(result)

        return results

    async def execute_single_task(
        self,
        task: DelegationTask,
    ) -> DelegationResult:
        """Spawn a specialist agent for one delegation task."""
        from auton.core.agent import run_agent

        config = self._registry.get_config(task.target_role)
        config.parent_conversation_id = task.parent_conversation_id
        config.delegation_context = task.context
        config.confirmation_callback = self._confirmation_callback

        if task.max_iterations:
            config.max_iterations_override = task.max_iterations

        # Fetch RivalSearchMCP prompt for research tasks
        if task.target_role == AgentRole.RESEARCH:
            prompt_text = await self._fetch_rival_prompt(task)
            if prompt_text:
                config.delegation_context["rival_prompt"] = prompt_text
                task.instruction += (
                    f"\n\n--- Guided workflow from RivalSearchMCP ---"
                    f"\n{prompt_text}"
                )

        # Log delegation start
        delegation_id: int | None = None
        try:
            delegation_id = await self._store.log_delegation(
                parent_conversation_id=task.parent_conversation_id,
                child_conversation_id="",
                orchestrator_role=AgentRole.ORCHESTRATOR.value,
                worker_role=task.target_role.value,
                task_instruction=task.instruction,
                task_context=task.context,
            )
        except Exception:
            logger.warning("Failed to log delegation start", exc_info=True)

        try:
            resp = await asyncio.wait_for(
                run_agent(
                    user_message=task.instruction,
                    bridge=self._bridge,
                    llm=self._llm,
                    store=self._store,
                    settings=self._settings,
                    agent_config=config,
                    conversation_id=None,
                    ctx=None,
                    memory_store=None,
                    headless=True,
                ),
                timeout=task.timeout,
            )

            # Update delegation log
            if delegation_id is not None:
                try:
                    await self._store.update_delegation_result(
                        delegation_id=delegation_id,
                        status="completed",
                        result_summary=resp.reply[:500],
                        error_message=None,
                        iterations_used=resp.iterations_used,
                        tools_called=resp.tools_called,
                        cost=resp.usage.cost or 0.0,
                    )
                except Exception:
                    logger.warning("Failed to log delegation result", exc_info=True)

            return DelegationResult(
                task_id=task.task_id,
                target_role=task.target_role,
                success=True,
                result=resp.reply,
                conversation_id=resp.conversation_id,
                iterations_used=resp.iterations_used,
                tools_called=resp.tools_called,
                cost=resp.usage.cost or 0.0,
            )

        except TimeoutError:
            logger.error("Delegation timed out: %s (%s)", task.task_id, task.target_role)
            error_msg = f"Task timed out after {task.timeout:.0f}s"

            if delegation_id is not None:
                try:
                    await self._store.update_delegation_result(
                        delegation_id=delegation_id,
                        status="failed",
                        result_summary=None,
                        error_message=error_msg,
                        iterations_used=0,
                        tools_called=[],
                        cost=0.0,
                    )
                except Exception:
                    pass

            return DelegationResult(
                task_id=task.task_id,
                target_role=task.target_role,
                success=False,
                result="",
                conversation_id="",
                error=error_msg,
            )

        except Exception as exc:
            logger.exception("Delegation failed: %s", task.task_id)
            error_msg = str(exc)[:500]

            if delegation_id is not None:
                try:
                    await self._store.update_delegation_result(
                        delegation_id=delegation_id,
                        status="failed",
                        result_summary=None,
                        error_message=error_msg,
                        iterations_used=0,
                        tools_called=[],
                        cost=0.0,
                    )
                except Exception:
                    pass

            return DelegationResult(
                task_id=task.task_id,
                target_role=task.target_role,
                success=False,
                result="",
                conversation_id="",
                error=error_msg,
            )

    # ── RivalSearchMCP prompt fetching ─────────────────────────

    async def _fetch_rival_prompt(
        self,
        task: DelegationTask,
    ) -> str | None:
        """Pick the best RivalSearchMCP prompt for a research task.

        Maps task context hints to one of:
          - comprehensive_research(topic, depth)
          - multi_source_search(query, include_social, include_news)
          - deep_content_analysis(url, extract_documents)
          - academic_literature_review(research_question, max_papers)

        Returns rendered prompt text, or None if no match / error.
        """
        ctx = task.context
        instruction_lower = task.instruction.lower()

        try:
            # Academic / scientific hints
            if any(
                kw in instruction_lower
                for kw in ("academic", "paper", "journal", "arxiv", "pubmed")
            ):
                return await self._bridge.get_prompt(
                    "academic_literature_review",
                    {
                        "research_question": task.instruction,
                        "max_papers": str(ctx.get("max_papers", 5)),
                    },
                )

            # URL-specific deep analysis
            if ctx.get("url") or "http" in instruction_lower:
                url = ctx.get("url", "")
                return await self._bridge.get_prompt(
                    "deep_content_analysis",
                    {
                        "url": url or task.instruction,
                        "extract_documents": "true",
                    },
                )

            # Multi-source (social + news)
            if any(
                kw in instruction_lower
                for kw in (
                    "social", "reddit", "news", "trending",
                    "hacker news", "discussion",
                )
            ):
                return await self._bridge.get_prompt(
                    "multi_source_search",
                    {
                        "query": task.instruction,
                        "include_social": "true",
                        "include_news": "true",
                    },
                )

            # Default: comprehensive research
            return await self._bridge.get_prompt(
                "comprehensive_research",
                {
                    "topic": task.instruction,
                    "depth": ctx.get("depth", "detailed"),
                },
            )

        except Exception:
            logger.debug(
                "RivalSearch prompt fetch failed for task %s",
                task.task_id,
                exc_info=True,
            )
            return None

    # ── synthesis ────────────────────────────────────────────────

    async def synthesize_results(
        self,
        user_message: str,
        results: list[DelegationResult],
        conversation_id: str,
    ) -> str:
        """Combine specialist results into a unified response."""
        synthesis_prompt = [
            ChatMessage(
                role=ChatRole.SYSTEM,
                content="""\
Synthesise the following specialist agent results into one coherent response.
- Address the user's original question directly.
- Cite which specialist provided which information.
- If any specialist failed, acknowledge it.
- Use clear structure with headings and bullet points.""",
            ),
            ChatMessage(
                role=ChatRole.USER,
                content=f"Original request: {user_message}",
            ),
        ]

        for result in results:
            role = result.target_role.value
            if result.success:
                synthesis_prompt.append(
                    ChatMessage(
                        role=ChatRole.ASSISTANT,
                        content=f"[{role} agent]: {result.result}",
                    )
                )
            else:
                synthesis_prompt.append(
                    ChatMessage(
                        role=ChatRole.ASSISTANT,
                        content=f"[{role} agent FAILED]: {result.error}",
                    )
                )

        synthesis_prompt.append(
            ChatMessage(
                role=ChatRole.USER,
                content="Synthesise these into a single response.",
            )
        )

        try:
            data = await self._llm.chat_completion(synthesis_prompt, tools=None)
            return (
                data.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
        except Exception:
            logger.warning("Synthesis failed, returning raw results", exc_info=True)
            parts: list[str] = []
            for r in results:
                if r.success:
                    parts.append(f"**{r.target_role.value}**: {r.result}")
                else:
                    parts.append(f"**{r.target_role.value}** (failed): {r.error}")
            return "\n\n".join(parts)
