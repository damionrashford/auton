#!/usr/bin/env python3
"""Automated Slack app setup from manifest.

Creates the Slack app, enables Socket Mode, generates tokens,
and writes them to .env.

Usage:
    1. Go to https://api.slack.com/apps
    2. Click your profile > "Generate a config token"
    3. Run: python scripts/setup_slack.py --config-token xoxe-...

The script will:
    - Create the app from slack-manifest.json
    - Enable Socket Mode and generate an app-level token
    - Request installation to your workspace
    - Write SLACK_BOT_TOKEN and SLACK_APP_TOKEN to .env
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

SLACK_API = "https://slack.com/api"
MANIFEST_PATH = Path(__file__).parent.parent / "slack-manifest.json"
ENV_PATH = Path(__file__).parent.parent / ".env"


def create_app(config_token: str, manifest: dict) -> dict:
    """Create a Slack app from manifest."""
    resp = httpx.post(
        f"{SLACK_API}/apps.manifest.create",
        headers={"Authorization": f"Bearer {config_token}"},
        json={"manifest": manifest},
    )
    data = resp.json()
    if not data.get("ok"):
        print(f"Failed to create app: {data.get('error')}")
        if data.get("errors"):
            for err in data["errors"]:
                print(f"  - {err}")
        sys.exit(1)
    return data


def generate_app_token(config_token: str, app_id: str) -> str:
    """Generate an app-level token for Socket Mode."""
    resp = httpx.post(
        f"{SLACK_API}/apps.connections.token.generate",
        headers={"Authorization": f"Bearer {config_token}"},
        json={
            "app_id": app_id,
            "scopes": ["connections:write"],
        },
    )
    data = resp.json()
    if not data.get("ok"):
        print(f"Failed to generate app token: {data.get('error')}")
        print(
            "You may need to manually generate it at "
            "https://api.slack.com/apps > Your App > Basic Information "
            "> App-Level Tokens"
        )
        return ""
    return data.get("token", "")


def update_env(key: str, value: str) -> None:
    """Add or update a key in .env file."""
    if not ENV_PATH.exists():
        ENV_PATH.write_text("")

    lines = ENV_PATH.read_text().splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create Slack app from manifest and configure tokens."
    )
    parser.add_argument(
        "--config-token",
        required=True,
        help=(
            "Slack configuration token (xoxe-...). "
            "Generate at https://api.slack.com/apps > Your profile"
        ),
    )
    parser.add_argument(
        "--manifest",
        default=str(MANIFEST_PATH),
        help="Path to manifest JSON file.",
    )
    args = parser.parse_args()

    # Load manifest
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}")
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text())
    print(f"Loaded manifest: {manifest['display_information']['name']}")

    # Create the app
    print("Creating Slack app...")
    result = create_app(args.config_token, manifest)

    app_id = result.get("app_id", "")
    credentials = result.get("credentials", {})
    bot_token = credentials.get("bot_token", "")
    signing_secret = credentials.get("signing_secret", "")

    print(f"App created: {app_id}")

    # Generate app-level token for Socket Mode
    print("Generating Socket Mode app token...")
    app_token = generate_app_token(args.config_token, app_id)

    # Write to .env
    if bot_token:
        update_env("SLACK_BOT_TOKEN", bot_token)
        print(f"SLACK_BOT_TOKEN written to .env")
    else:
        print(
            "Bot token not returned. Install the app to your workspace at:"
        )
        print(
            f"  https://api.slack.com/apps/{app_id}/install-on-team"
        )

    if app_token:
        update_env("SLACK_APP_TOKEN", app_token)
        print(f"SLACK_APP_TOKEN written to .env")

    if signing_secret:
        update_env("SLACK_SIGNING_SECRET", signing_secret)
        print(f"SLACK_SIGNING_SECRET written to .env")

    update_env("SLACK_ENABLED", "true")

    print()
    print("Done. Next steps:")
    if not bot_token:
        print(
            f"  1. Install the app: "
            f"https://api.slack.com/apps/{app_id}/install-on-team"
        )
        print(
            "  2. Copy the Bot User OAuth Token (xoxb-...) "
            "to SLACK_BOT_TOKEN in .env"
        )
    print("  3. Start the server: uv run uvicorn fast_mcp_agent.app:app")
    print("  4. @mention the bot in Slack or DM it")


if __name__ == "__main__":
    main()
