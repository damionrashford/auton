#!/usr/bin/env python3
"""Automated Google Workspace MCP setup via gcloud CLI.

Creates a Google Cloud project, enables APIs, creates OAuth credentials,
and starts workspace-mcp for first-time auth.

Prerequisites:
    brew install google-cloud-sdk   # macOS
    gcloud auth login               # one-time browser login

Usage:
    python scripts/setup_google.py
    python scripts/setup_google.py --project my-agent-project --start
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ENV_PATH = Path(__file__).parent.parent / ".env"

REQUIRED_APIS = [
    "calendar-json.googleapis.com",
    "drive.googleapis.com",
    "gmail.googleapis.com",
    "docs.googleapis.com",
    "sheets.googleapis.com",
    "slides.googleapis.com",
    "forms.googleapis.com",
    "tasks.googleapis.com",
    "people.googleapis.com",
    "chat.googleapis.com",
]


def run(cmd: list[str], capture: bool = False) -> str:
    """Run a shell command, exit on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=True,
        )
        return result.stdout.strip() if capture else ""
    except FileNotFoundError:
        print(f"Command not found: {cmd[0]}")
        print("Install gcloud: https://cloud.google.com/sdk/docs/install")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        if capture and e.stderr:
            print(f"Error: {e.stderr.strip()}")
        return ""


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
        description="Set up Google Cloud project + APIs + OAuth for workspace-mcp."
    )
    parser.add_argument(
        "--project",
        default="fastmcp-agent",
        help="Google Cloud project ID (default: fastmcp-agent)",
    )
    parser.add_argument(
        "--port",
        default="8001",
        help="Port for workspace-mcp (default: 8001)",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start workspace-mcp after setup.",
    )
    args = parser.parse_args()

    project = args.project

    # Check gcloud is available
    print("Checking gcloud CLI...")
    account = run(["gcloud", "auth", "list", "--format=value(account)", "--filter=status:ACTIVE"], capture=True)
    if not account:
        print("No active gcloud account. Run: gcloud auth login")
        sys.exit(1)
    print(f"Authenticated as: {account}")

    # Create or select project
    print(f"\nCreating project: {project}")
    run(["gcloud", "projects", "create", project, "--set-as-default"], capture=True)
    run(["gcloud", "config", "set", "project", project])

    # Enable APIs
    print(f"\nEnabling {len(REQUIRED_APIS)} Google APIs...")
    for api in REQUIRED_APIS:
        name = api.split(".")[0].replace("-json", "")
        print(f"  Enabling {name}...")
        run(["gcloud", "services", "enable", api], capture=True)
    print("All APIs enabled.")

    # Configure OAuth consent screen
    print("\nConfiguring OAuth consent screen...")
    run([
        "gcloud", "alpha", "iap", "oauth-brands", "create",
        f"--application_title=FastMCP Agent",
        f"--support_email={account}",
    ], capture=True)

    # Create OAuth client
    print("\nCreating OAuth Desktop client...")
    run([
        "gcloud", "alpha", "iap", "oauth-clients", "create",
        f"projects/{project}/brands/-",
        "--display_name=FastMCP Agent Desktop",
    ], capture=True)

    # Try to get credentials via gcloud
    print("\nFetching OAuth credentials...")
    clients_json = run([
        "gcloud", "alpha", "iap", "oauth-clients", "list",
        f"projects/{project}/brands/-",
        "--format=json",
    ], capture=True)

    client_id = ""
    client_secret = ""

    if clients_json:
        try:
            clients = json.loads(clients_json)
            if clients:
                client_id = clients[0].get("name", "").split("/")[-1]
                client_secret = clients[0].get("secret", "")
        except (json.JSONDecodeError, IndexError, KeyError):
            pass

    if not client_id:
        print("\ngcloud alpha commands may not be available.")
        print("Create OAuth credentials manually:")
        print(f"  https://console.cloud.google.com/apis/credentials?project={project}")
        print("  -> Create Credentials -> OAuth Client ID -> Desktop Application")
        print()
        client_id = input("Client ID: ").strip()
        client_secret = input("Client Secret: ").strip()

    email = input(f"\nGoogle email [{account}]: ").strip() or account

    # Write to .env
    print("\nWriting to .env...")
    update_env("GOOGLE_WORKSPACE_MCP_URL", f"http://localhost:{args.port}/mcp")
    update_env("GOOGLE_WORKSPACE_MCP_ENABLED", "true")
    print("Done.")

    if args.start:
        print(f"\nStarting workspace-mcp on port {args.port}...")
        print("Browser will open for OAuth consent on first run.\n")
        try:
            subprocess.run(
                [
                    "uvx", "workspace-mcp",
                    "--transport", "streamable-http",
                    "--single-user",
                    "--tool-tier", "core",
                ],
                env={
                    **dict(__import__("os").environ),
                    "GOOGLE_OAUTH_CLIENT_ID": client_id,
                    "GOOGLE_OAUTH_CLIENT_SECRET": client_secret,
                    "USER_GOOGLE_EMAIL": email,
                    "WORKSPACE_MCP_PORT": args.port,
                    "OAUTHLIB_INSECURE_TRANSPORT": "1",
                },
                check=True,
            )
        except KeyboardInterrupt:
            print("\nServer stopped.")
    else:
        print(f"\nStart workspace-mcp with:")
        print(f"  GOOGLE_OAUTH_CLIENT_ID={client_id} \\")
        print(f"  GOOGLE_OAUTH_CLIENT_SECRET={client_secret} \\")
        print(f"  USER_GOOGLE_EMAIL={email} \\")
        print(f"  WORKSPACE_MCP_PORT={args.port} \\")
        print("  uvx workspace-mcp --transport streamable-http --single-user --tool-tier core")


if __name__ == "__main__":
    main()
