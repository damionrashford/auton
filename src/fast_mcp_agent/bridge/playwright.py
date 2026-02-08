"""Playwright MCP subprocess manager.

Spawns ``npx @playwright/mcp@latest`` as a child process with HTTP
transport, configured via a JSON configuration file.

All Playwright MCP settings are derived from the ``Settings`` object
and written to a temporary JSON config file that is passed to the
subprocess via ``--config``.  This replaces the previous approach of
building 15+ individual CLI flags and enables nested configuration
(browser.contextOptions, browser.initScript, network.blockedOrigins, etc.).
"""

from __future__ import annotations

import asyncio
import importlib.resources
import json
import logging
import os
import shutil
import tempfile

import httpx

from fast_mcp_agent.config import Settings

logger = logging.getLogger(__name__)

# How long to wait for the subprocess to become healthy.
_STARTUP_TIMEOUT_S = 30.0
_HEALTH_POLL_INTERVAL_S = 0.5


class PlaywrightProcess:
    """Manages the lifecycle of the Playwright MCP Node.js subprocess."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._process: asyncio.subprocess.Process | None = None
        self._config_path: str | None = None

    # ── config builder ───────────────────────────────────────────

    def _build_config(self) -> dict:
        """Build the full Playwright MCP JSON config dict from Settings.

        Maps flat Settings fields into the nested JSON schema expected by
        ``npx @playwright/mcp --config <path>``.

        Returns:
            A dict ready to be serialized to JSON.
        """
        s = self._settings

        # Parse viewport size (e.g. "1280x720" -> {"width": 1280, "height": 720})
        vw, vh = 1280, 720
        if s.playwright_mcp_viewport_size:
            try:
                vw, vh = (int(x) for x in s.playwright_mcp_viewport_size.split("x"))
            except (ValueError, AttributeError):
                pass

        # ── browser section ──────────────────────────────────────
        launch_options: dict = {
            "headless": s.playwright_mcp_headless,
        }
        if s.playwright_mcp_no_sandbox:
            launch_options["args"] = ["--no-sandbox", "--disable-setuid-sandbox"]

        # Proxy support (Phase 4)
        if s.playwright_mcp_proxy_server:
            proxy: dict = {"server": s.playwright_mcp_proxy_server}
            if s.playwright_mcp_proxy_bypass:
                proxy["bypass"] = s.playwright_mcp_proxy_bypass
            launch_options["proxy"] = proxy

        context_options: dict = {
            "viewport": {"width": vw, "height": vh},
            "ignoreHTTPSErrors": s.playwright_mcp_ignore_https_errors,
            "serviceWorkers": (
                "block" if s.playwright_mcp_block_service_workers else "allow"
            ),
        }
        if s.playwright_mcp_user_agent:
            context_options["userAgent"] = s.playwright_mcp_user_agent

        # Init scripts (Phase 2b: stealth.js)
        init_scripts: list[str] = []
        if s.playwright_mcp_stealth:
            stealth_path = self._resolve_stealth_js()
            if stealth_path:
                init_scripts.append(stealth_path)

        browser: dict = {
            "browserName": s.playwright_mcp_browser,
            "isolated": s.playwright_mcp_isolated,
            "launchOptions": launch_options,
            "contextOptions": context_options,
        }
        if init_scripts:
            browser["initScript"] = init_scripts

        # ── capabilities (Phase 3: PDF) ──────────────────────────
        capabilities: list[str] = []
        if s.playwright_mcp_caps:
            capabilities = [c.strip() for c in s.playwright_mcp_caps.split(",") if c.strip()]
        if not capabilities:
            capabilities = ["core"]

        # ── assemble config ──────────────────────────────────────
        config: dict = {
            "browser": browser,
            "server": {
                "port": s.playwright_mcp_port,
                "host": "localhost",
            },
            "capabilities": capabilities,
            "sharedBrowserContext": s.playwright_mcp_shared_browser_context,
            "imageResponses": s.playwright_mcp_image_responses,
            "codegen": s.playwright_mcp_codegen,
            "console": {
                "level": s.playwright_mcp_console_level,
            },
            "timeouts": {
                "action": s.playwright_mcp_timeout_action,
                "navigation": s.playwright_mcp_timeout_navigation,
            },
            "snapshot": {
                "mode": s.playwright_mcp_snapshot_mode,
            },
        }

        # ── network filtering (Phase 5: blocked origins) ─────────
        if s.playwright_mcp_blocked_origins:
            blocked = [
                o.strip()
                for o in s.playwright_mcp_blocked_origins.split(";")
                if o.strip()
            ]
            if blocked:
                config["network"] = {"blockedOrigins": blocked}

        # ── dev mode tracing (Phase 8) ───────────────────────────
        if s.playwright_mcp_save_trace:
            config["saveTrace"] = True
            config["outputDir"] = s.playwright_mcp_output_dir or "/tmp/pw-traces"
            config["outputMode"] = "file"

        return config

    def _resolve_stealth_js(self) -> str | None:
        """Resolve the absolute path to stealth.js.

        Uses importlib.resources for reliable resolution across install modes
        (editable, wheel, sdist).
        """
        try:
            ref = importlib.resources.files("fast_mcp_agent.browser") / "stealth.js"
            path = str(ref)
            if os.path.isfile(path):
                return path
        except Exception:
            pass

        # Fallback: relative path from this file
        fallback = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "browser",
            "stealth.js",
        )
        if os.path.isfile(fallback):
            return fallback

        logger.warning("stealth.js not found — stealth injection disabled.")
        return None

    # ── lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Spawn the Node subprocess and wait until it is reachable.

        Builds the JSON config file, writes it to a temp file, and passes
        ``--config <path>`` to the subprocess.

        Raises:
            RuntimeError: if npx is not found or the process fails to start.
            TimeoutError: if the process does not become healthy in time.
        """
        if self._process is not None:
            logger.info("Playwright MCP process already running.")
            return

        npx = shutil.which("npx")
        if npx is None:
            raise RuntimeError(
                "npx not found on PATH -- install Node.js 18+ to use Playwright MCP."
            )

        # Build and write config to temp file
        config = self._build_config()
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="pw-mcp-config-",
            delete=False,
        )
        try:
            json.dump(config, tmp, indent=2)
            tmp.close()
            self._config_path = tmp.name
        except Exception:
            tmp.close()
            os.unlink(tmp.name)
            raise

        logger.info(
            "Playwright MCP config written to %s:\n%s",
            self._config_path,
            json.dumps(config, indent=2),
        )

        cmd_args: list[str] = [
            npx,
            "@playwright/mcp@latest",
            "--config",
            self._config_path,
            "--port",
            str(self._settings.playwright_mcp_port),
        ]

        logger.info("Starting Playwright MCP: %s", " ".join(cmd_args))

        self._process = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await self._wait_until_healthy()
        logger.info(
            "Playwright MCP is ready on port %d (pid=%s).",
            self._settings.playwright_mcp_port,
            self._process.pid,
        )

    async def stop(self) -> None:
        """Gracefully terminate the subprocess and clean up config file."""
        if self._process is None:
            return

        logger.info("Stopping Playwright MCP (pid=%s)...", self._process.pid)
        try:
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=10.0)
        except (TimeoutError, ProcessLookupError):
            logger.warning("Force-killing Playwright MCP subprocess.")
            self._process.kill()
        finally:
            self._process = None

        # Clean up temp config file
        if self._config_path:
            try:
                os.unlink(self._config_path)
                logger.debug("Removed temp config: %s", self._config_path)
            except OSError:
                pass
            self._config_path = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    # ── health check ────────────────────────────────────────────────

    async def _wait_until_healthy(self) -> None:
        """Poll the HTTP endpoint until it responds or the timeout expires."""
        url = self._settings.playwright_mcp_url
        deadline = asyncio.get_event_loop().time() + _STARTUP_TIMEOUT_S

        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() < deadline:
                # Check if process died
                if self._process and self._process.returncode is not None:
                    stderr_bytes = b""
                    if self._process.stderr:
                        stderr_bytes = await self._process.stderr.read()
                    raise RuntimeError(
                        f"Playwright MCP exited with code {self._process.returncode}: "
                        f"{stderr_bytes.decode(errors='replace')}"
                    )
                try:
                    resp = await client.get(
                        url.replace("/mcp", ""),
                        timeout=2.0,
                    )
                    if resp.status_code < 500:
                        return
                except (httpx.ConnectError, httpx.ReadError, httpx.ConnectTimeout):
                    pass
                await asyncio.sleep(_HEALTH_POLL_INTERVAL_S)

        raise TimeoutError(
            f"Playwright MCP did not become healthy within {_STARTUP_TIMEOUT_S}s"
        )
