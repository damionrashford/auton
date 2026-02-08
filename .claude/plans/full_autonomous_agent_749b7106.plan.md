---
name: Full Autonomous Agent
overview: ""
todos: []
---

# Full Autonomous Agent Upgrade

Twelve gaps stand between the current agent and a truly autonomous system. This plan addresses each one, organized into 9 implementation phases based on dependencies.

```mermaid
flowchart TD
    subgraph phase0 [Phase 0: MCPBridge Notifications]
        P0[MessageHandler on Client instances]
    end

    subgraph phase1 [Phase 1: Long-Term Memory]
        P1A[embed method in LLMClient]
        P1B[pgvector schema + MemoryStore]
        P1C[Memory internal tools]
        P1A --> P1B --> P1C
    end

    subgraph phase2 [Phase 2: Context Window]
        P2A[tiktoken token counting]
        P2B[Conversation compaction]
    end

    subgraph phase3 [Phase 3: Cron via Docket]
        P3[Wire _execute_job through Docket]
    end

    subgraph phase4 [Phase 4: Approval Gate]
        P4A[Action classification]
        P4B[ctx.elicit confirmation]
    end

    subgraph phase5 [Phase 5: Planning]
        P5[Agent plan-then-execute]
    end

    subgraph phase6 [Phase 6: Parallel + Guardrails]
        P6A[asyncio.gather for tools]
        P6B[Cost/token guardrails]
    end

    subgraph phase7 [Phase 7: chat_async Tool]
        P7[Background tool with Docket + Progress]
    end

    subgraph phase8 [Phase 8: Observability]
        P8A[Decision logging + resources]
    end

    subgraph phase9 [Phase 9: Final Integration]
        P9[System prompt + config + lint]
    end

    P0 --> P9
    P1C --> P9
    P2B --> P3
    P2B --> P5
    P4B --> P5
    P5 --> P9
    P6A --> P9
    P6B --> P9
    P3 --> P7
    P7 --> P9
    P8A --> P9
```

---

## Phase 0: MCPBridge Client Notifications

**New addition** -- Currently [`bridge/manager.py`](src/fast_mcp_agent/bridge/manager.py) creates `Client()` instances with no `message_handler`. If RivalSearch, Playwright, or Google Workspace MCP servers update their tool lists at runtime, our cached tool registry goes stale silently.

Add a `BridgeNotificationHandler` subclass of `MessageHandler`:

```python
# In bridge/manager.py
from fastmcp.client.messages import MessageHandler

class BridgeNotificationHandler(MessageHandler):
    """Auto-refresh tool caches when connected MCP servers change their tools."""

    def __init__(self, bridge: "MCPBridge", source: str):
        self._bridge = bridge
        self._source = source

    async def on_tool_list_changed(self, notification) -> None:
        client = self._bridge._get_client(self._source)
        if client:
            new_tools = await self._bridge._discover_tools(client, self._source)
            if self._source == "rival":
                self._bridge._rival_tools = new_tools
            elif self._source == "pw":
                self._bridge._pw_tools = new_tools
            elif self._source == "gw":
                self._bridge._gw_tools = new_tools
            self._bridge._build_routing()
            logger.info("Tool list refreshed for %s (%d tools).", self._source, len(new_tools))
```

Pass it when creating each client:

```python
self._rival_client = Client(
    self._settings.rival_search_url,
    message_handler=BridgeNotificationHandler(self, "rival"),
)
```

---

## Phase 1: Long