"""RAG tool definitions and handler.

These are registered on the MCPBridge with ``rag_`` prefix so agents
can upload documents, search across them, and manage the document store.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from auton.rag.service import RAGService

logger = logging.getLogger(__name__)

# ── Tool schemas (OpenAI function-calling format) ────────────────

RAG_TOOLS: list[dict[str, Any]] = [
    {
        "name": "rag_upload",
        "description": (
            "Upload and index a document for RAG retrieval. "
            "Provide a URL to download the file from, or a file path. "
            "Supports PDF, Word, Excel, CSV, Jupyter notebooks, images "
            "(OCR), Markdown, code files, and more."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": (
                        "URL to download the file from (Slack file URL, "
                        "web URL, or local file path)."
                    ),
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "Filename with extension (e.g. 'report.pdf'). "
                        "Used for format detection."
                    ),
                },
            },
            "required": ["url", "filename"],
        },
    },
    {
        "name": "rag_search",
        "description": (
            "Semantic search across all uploaded documents. "
            "Returns the most relevant text chunks with source "
            "files, page numbers, and similarity scores."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (natural language).",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "rag_search_doc",
        "description": (
            "Search within a specific uploaded document by ID. "
            "Useful when you know which document to look in."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                },
                "document_id": {
                    "type": "integer",
                    "description": "Document ID to search within.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return.",
                    "default": 5,
                },
            },
            "required": ["query", "document_id"],
        },
    },
    {
        "name": "rag_list",
        "description": "List all uploaded documents with metadata (name, type, size, chunks).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "rag_get",
        "description": "Get the full content of a specific document by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "integer",
                    "description": "Document ID.",
                },
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "rag_delete",
        "description": "Delete an uploaded document and all its indexed chunks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "integer",
                    "description": "Document ID to delete.",
                },
            },
            "required": ["document_id"],
        },
    },
]


# ── Handler ──────────────────────────────────────────────────────


async def handle_rag_tool(
    service: RAGService,
    name: str,
    args: dict[str, Any],
) -> str:
    """Route a RAG tool call to the correct service method."""
    try:
        result = await _dispatch(service, name, args)
        if isinstance(result, dict | list):
            return json.dumps(result, indent=2, default=str)
        return str(result)
    except Exception as exc:
        logger.exception("RAG tool '%s' failed", name)
        return f"[error] RAG tool '{name}' failed: {exc}"


async def _dispatch(
    svc: RAGService,
    name: str,
    args: dict[str, Any],
) -> Any:
    """Map tool name to the appropriate service method."""

    if name == "rag_upload":
        # Download the file content first
        content = await _download_file(args["url"])
        if content is None:
            return {"error": f"Failed to download file from: {args['url']}"}
        return await svc.ingest(
            filename=args["filename"],
            content=content,
            uploaded_by=args.get("uploaded_by", "agent"),
        )

    if name == "rag_search":
        return await svc.search(
            query=args["query"],
            top_k=args.get("top_k", 5),
        )

    if name == "rag_search_doc":
        return await svc.search(
            query=args["query"],
            top_k=args.get("top_k", 5),
            document_id=args["document_id"],
        )

    if name == "rag_list":
        return await svc.list_documents()

    if name == "rag_get":
        return await svc.get_document(args["document_id"])

    if name == "rag_delete":
        return await svc.delete_document(args["document_id"])

    return {"error": f"Unknown RAG tool: {name}"}


async def _download_file(url: str) -> bytes | None:
    """Download a file from a URL or read from a local path."""
    from pathlib import Path

    import httpx

    # Check if it's a local file path
    path = Path(url)
    if path.exists() and path.is_file():
        return path.read_bytes()

    # Download from URL
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return resp.content
    except Exception:
        logger.warning("Failed to download file from %s", url, exc_info=True)
        return None
