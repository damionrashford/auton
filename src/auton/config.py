"""Centralised application configuration loaded from environment variables.

Uses pydantic-settings for type-safe, validated configuration with automatic
.env file loading.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings sourced from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── xAI LLM (via xai-sdk, gRPC) ─────────────────────────────────
    xai_api_key: str = Field(
        default="",
        description="xAI API key (XAI_API_KEY env var).",
    )
    xai_model: str = Field(
        default="grok-4.1-fast",
        description="Primary Grok model identifier.",
    )
    xai_temperature: float | None = Field(
        default=None,
        description="Sampling temperature. None = model default.",
    )
    xai_max_tokens: int | None = Field(
        default=None,
        description="Max completion tokens. None = model default.",
    )
    xai_reasoning_effort: str = Field(
        default="",
        description="Reasoning effort: 'low' or 'high'. Empty = disabled.",
    )
    xai_embedding_model: str = Field(
        default="grok-embedding-small",
        description="xAI embedding model for semantic memory.",
    )

    # ── RivalSearchMCP ──────────────────────────────────────────────
    rival_search_url: str = Field(
        default="https://RivalSearchMCP.fastmcp.app/mcp",
        description="Remote HTTP URL for RivalSearchMCP.",
    )

    # ── Playwright MCP (required, always started) ───────────────────
    playwright_mcp_port: int = Field(
        default=8931,
        description="Port for the Playwright MCP HTTP server.",
    )
    playwright_mcp_headless: bool = Field(
        default=True,
        description="Run browser in headless mode (no GUI). Required for servers.",
    )
    playwright_mcp_browser: str = Field(
        default="chromium",
        description=(
            "Browser engine to use: 'chromium', 'chrome', 'firefox', "
            "'webkit', 'msedge'. Chromium is bundled with Playwright."
        ),
    )
    playwright_mcp_isolated: bool = Field(
        default=True,
        description=(
            "Keep browser profile in memory only — no disk persistence. "
            "Each session starts clean with no cookies or history."
        ),
    )
    playwright_mcp_no_sandbox: bool = Field(
        default=False,
        description=(
            "Disable Chromium sandbox. Required in Docker/container "
            "environments where kernel capabilities are restricted."
        ),
    )
    playwright_mcp_block_service_workers: bool = Field(
        default=True,
        description=(
            "Block service workers to prevent cached/stale content from "
            "interfering with page reads."
        ),
    )
    playwright_mcp_ignore_https_errors: bool = Field(
        default=True,
        description=(
            "Ignore SSL/TLS certificate errors. Prevents the agent from "
            "failing on sites with expired or self-signed certs."
        ),
    )
    playwright_mcp_image_responses: str = Field(
        default="omit",
        description=(
            "'allow' or 'omit'. Omit strips image data from tool responses "
            "to save context tokens — agent uses accessibility snapshots."
        ),
    )
    playwright_mcp_console_level: str = Field(
        default="error",
        description=(
            "Console message capture level: 'error', 'warning', 'info', "
            "'debug'. 'error' keeps responses lean."
        ),
    )
    playwright_mcp_codegen: str = Field(
        default="none",
        description=(
            "Code generation language: 'typescript' or 'none'. "
            "Set to 'none' — agent is not writing tests."
        ),
    )
    playwright_mcp_shared_browser_context: bool = Field(
        default=True,
        description=(
            "Reuse the same browser context across all HTTP connections. "
            "Required so sequential tool calls share tabs/cookies/state."
        ),
    )
    playwright_mcp_viewport_size: str = Field(
        default="1280x720",
        description="Browser viewport dimensions in pixels (WIDTHxHEIGHT).",
    )
    playwright_mcp_timeout_action: int = Field(
        default=10000,
        description=(
            "Default action timeout in ms (click, fill, etc.). "
            "Raised from default 5000 for slow/heavy sites."
        ),
    )
    playwright_mcp_timeout_navigation: int = Field(
        default=30000,
        description=(
            "Navigation timeout in ms. Lowered from default 60000 — "
            "if a page hasn't loaded in 30s it's likely broken."
        ),
    )
    playwright_mcp_user_agent: str = Field(
        default="",
        description=(
            "Custom User-Agent string. Set a real-looking UA to avoid "
            "headless browser detection blocks. Empty = Playwright default."
        ),
    )

    # ── Playwright MCP: JSON-config-only fields ──────────────────
    playwright_mcp_caps: str = Field(
        default="core,pdf",
        description=(
            "Comma-separated capabilities for Playwright MCP. "
            "Options: 'core', 'pdf', 'vision', 'devtools'. "
            "Default includes PDF for saving pages as PDFs."
        ),
    )
    playwright_mcp_proxy_server: str = Field(
        default="",
        description=(
            "HTTP/SOCKS proxy URL for Playwright browser traffic. "
            "e.g. 'http://myproxy:3128' or 'socks5://myproxy:8080'."
        ),
    )
    playwright_mcp_proxy_bypass: str = Field(
        default="",
        description=(
            "Comma-separated domains to bypass the proxy. "
            "e.g. '.com,chromium.org,.domain.com'."
        ),
    )
    playwright_mcp_blocked_origins: str = Field(
        default=(
            "https://www.googletagmanager.com;"
            "https://www.google-analytics.com;"
            "https://connect.facebook.net;"
            "https://cdn.segment.com"
        ),
        description=(
            "Semicolon-separated origins to block. Blocks ad trackers "
            "to speed up page loads and reduce snapshot noise."
        ),
    )
    playwright_mcp_output_dir: str = Field(
        default="",
        description="Directory for session output files (traces, snapshots, etc.).",
    )
    playwright_mcp_save_trace: bool = Field(
        default=False,
        description="Save Playwright trace into output directory. Useful for debugging.",
    )
    playwright_mcp_snapshot_mode: str = Field(
        default="incremental",
        description=(
            "Snapshot mode: 'incremental' (deltas), 'full' (whole page), "
            "or 'none'. Incremental is token-efficient for most cases."
        ),
    )
    playwright_mcp_stealth: bool = Field(
        default=True,
        description=(
            "Inject anti-bot stealth script into every page. "
            "Overrides navigator.webdriver, plugins, languages etc."
        ),
    )

    # ── Google Workspace MCP (optional) ──────────────────────────
    google_workspace_mcp_url: str = Field(
        default="",
        description="Streamable HTTP URL for the Google Workspace MCP server.",
    )
    google_workspace_mcp_enabled: bool = Field(
        default=True,
        description="Whether to attempt connecting to Google Workspace MCP on startup.",
    )

    # ── Slack Bolt Python (optional) ─────────────────────────────
    slack_bot_token: str = Field(
        default="",
        description="Slack Bot Token (xoxb-...) for Slack Bolt.",
    )
    slack_app_token: str = Field(
        default="",
        description="Slack App Token (xapp-...) for Socket Mode.",
    )
    slack_signing_secret: str = Field(
        default="",
        description="Slack signing secret for request verification.",
    )
    slack_enabled: bool = Field(
        default=True,
        description="Whether to initialize Slack Bolt on startup.",
    )

    # ── Cron Scheduler (optional) ────────────────────────────────
    cron_enabled: bool = Field(
        default=True,
        description="Whether to start the cron scheduler on startup.",
    )
    cron_timezone: str = Field(
        default="UTC",
        description="Timezone for cron job evaluation (e.g. 'America/New_York').",
    )

    # ── Neon Postgres (persistent storage) ─────────────────────────
    neon_database_url: str = Field(
        default="",
        description="Neon Postgres connection string (postgresql://...@...neon.tech/...).",
    )
    neon_api_key: str = Field(
        default="",
        description="Neon platform API key for resource management (optional).",
    )

    # ── Redis (required) ────────────────────────────────────────────
    redis_host: str = Field(
        default="localhost",
        description="Redis server hostname.",
    )
    redis_port: int = Field(
        default=6379,
        description="Redis server port.",
    )
    redis_db: int = Field(
        default=0,
        description="Redis database number for response caching.",
    )
    redis_session_db: int = Field(
        default=1,
        description="Redis database number for session state.",
    )

    # ── Docket (background tasks) ──────────────────────────────────
    docket_url: str = Field(
        default="redis://localhost:6379/2",
        description="Redis URL for Docket task queue backend.",
    )

    # ── Agent behaviour ─────────────────────────────────────────────
    max_iterations: int = Field(
        default=25,
        description="Maximum agentic loop iterations per request.",
    )
    max_tool_result_length: int = Field(
        default=15_000,
        description="Truncate tool results beyond this character count.",
    )
    tool_timeout: float = Field(
        default=120.0,
        description="Foreground tool timeout in seconds.",
    )

    # ── Context Window Management ────────────────────────────────────
    context_window_limit: int = Field(
        default=128000,
        description="Model context window in tokens.",
    )
    compaction_threshold: float = Field(
        default=0.75,
        description="Compact when usage exceeds this fraction of context window.",
    )
    compaction_tail_messages: int = Field(
        default=10,
        description="Messages to preserve during compaction.",
    )

    # ── Cost and Safety Guardrails ──────────────────────────────────
    max_cost_per_conversation: float = Field(
        default=1.0,
        description="Max USD cost per conversation.",
    )
    max_cost_per_day: float = Field(
        default=10.0,
        description="Max USD cost per day.",
    )
    max_tokens_per_conversation: int = Field(
        default=500000,
        description="Max total tokens per conversation.",
    )
    require_confirmation: bool = Field(
        default=True,
        description="Require user approval for write actions.",
    )

    # ── Multi-Agent Orchestration ────────────────────────────────────
    multi_agent_max_delegation_depth: int = Field(
        default=2,
        description="Max delegation chain depth (prevents infinite recursion).",
    )
    multi_agent_orchestrator_timeout: float = Field(
        default=600.0,
        description="Total timeout for orchestrator task synthesis (seconds).",
    )
    multi_agent_orchestrator_max_iterations: int = Field(
        default=15,
        description="Max iterations for the orchestrator agent.",
    )
    multi_agent_research_max_iterations: int = Field(
        default=20,
        description="Max iterations for the research agent.",
    )
    multi_agent_browser_max_iterations: int = Field(
        default=25,
        description="Max iterations for the browser agent.",
    )
    multi_agent_communication_max_iterations: int = Field(
        default=10,
        description="Max iterations for the communication agent.",
    )
    multi_agent_workspace_max_iterations: int = Field(
        default=15,
        description="Max iterations for the workspace agent.",
    )
    multi_agent_blockchain_max_iterations: int = Field(
        default=10,
        description="Max iterations for the blockchain agent.",
    )

    # ── Coinbase AgentKit (optional) ─────────────────────────────────
    blockchain_enabled: bool = Field(
        default=False,
        description="Enable Coinbase AgentKit blockchain tools.",
    )
    blockchain_network: str = Field(
        default="base-mainnet",
        description="Blockchain network (base-mainnet, base-sepolia, etc.).",
    )
    cdp_api_key_id: str = Field(
        default="",
        description="Coinbase Developer Platform API key ID.",
    )
    cdp_api_key_secret: str = Field(
        default="",
        description="Coinbase Developer Platform API key secret.",
    )
    cdp_wallet_secret: str = Field(
        default="",
        description="CDP wallet secret for server wallets.",
    )

    # ── Server ──────────────────────────────────────────────────────
    server_host: str = Field(default="0.0.0.0", description="Bind host.")
    server_port: int = Field(default=8000, description="Bind port.")

    @property
    def playwright_mcp_url(self) -> str:
        """Derive the full Playwright MCP endpoint URL."""
        return f"http://localhost:{self.playwright_mcp_port}/mcp"

    @property
    def effective_context_window(self) -> int:
        """Get context window for current model."""
        return _MODEL_CONTEXT_WINDOWS.get(
            self.xai_model, self.context_window_limit
        )


# Known Grok model context window sizes.
_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "grok-4.1-fast": 2_000_000,
    "grok-4-fast": 2_000_000,
    "grok-4": 256_000,
    "grok-3": 131_072,
    "grok-3-mini": 131_072,
}

_cached_settings: Settings | None = None


def get_settings() -> Settings:
    """Factory that returns a cached Settings singleton."""
    global _cached_settings  # noqa: PLW0603
    if _cached_settings is None:
        _cached_settings = Settings()
    return _cached_settings
