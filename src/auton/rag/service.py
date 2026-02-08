"""RAG service — orchestrates document ingestion and retrieval.

Coordinates the full pipeline: parse → chunk → embed → store → search.
Uses pgvector (384-dim HNSW index) for fast cosine similarity search
and the local ``bge-small-en-v1.5`` model for embedding.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from auton.rag.chunker import Chunk, chunk_text
from auton.rag.embedder import LocalEmbedder
from auton.rag.parser import PageContent, parse_document

logger = logging.getLogger(__name__)

# SQL for creating RAG tables (idempotent).
_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    filename    TEXT NOT NULL,
    file_type   TEXT NOT NULL,
    file_size   INTEGER DEFAULT 0,
    num_chunks  INTEGER DEFAULT 0,
    uploaded_by TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id          SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_text  TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER DEFAULT 0,
    section     TEXT DEFAULT '',
    embedding   VECTOR(384) NOT NULL,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast cosine similarity search.
CREATE INDEX IF NOT EXISTS idx_chunk_embedding
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_chunk_document_id
    ON document_chunks (document_id);
"""


class RAGService:
    """Document ingestion and semantic retrieval service."""

    def __init__(
        self,
        pool: Any,  # asyncpg.Pool
        embedder: LocalEmbedder,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._started = False

    @property
    def is_connected(self) -> bool:
        return self._started and self._embedder.is_ready

    async def start(self) -> None:
        """Run schema migration and verify embedder is ready."""
        if self._pool is None:
            logger.warning("RAG: requires Neon Postgres (no pool provided).")
            return

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(_SCHEMA_SQL)
            logger.info("RAG: schema migrated (documents + document_chunks).")
        except Exception:
            logger.warning("RAG: schema migration failed.", exc_info=True)
            return

        if not self._embedder.is_ready:
            logger.warning("RAG: embedder not ready — start it first.")
            return

        self._started = True
        logger.info("RAGService started: embedder=%s.", self._embedder._model_name)

    # ── Ingestion ────────────────────────────────────────────────

    async def ingest(
        self,
        filename: str,
        content: bytes,
        *,
        uploaded_by: str = "",
    ) -> dict[str, Any]:
        """Ingest a document: parse → chunk → embed → store.

        Returns metadata about the ingested document.
        """
        if not self._started:
            return {"error": "RAG service not started."}

        # 1. Parse
        from pathlib import Path

        file_type = Path(filename).suffix.lower().lstrip(".")
        pages: list[PageContent] = parse_document(filename, content)

        if not pages:
            return {"error": f"No content extracted from {filename}."}

        # 2. Chunk each page
        all_chunks: list[Chunk] = []
        for page in pages:
            page_chunks = chunk_text(
                page.text,
                page_number=page.page_number,
                section=page.section,
                metadata=page.metadata,
            )
            all_chunks.extend(page_chunks)

        if not all_chunks:
            return {"error": "No chunks generated after parsing."}

        # 3. Batch embed all chunks
        texts = [c.text for c in all_chunks]
        embeddings = self._embedder.embed_batch(texts)

        if len(embeddings) != len(all_chunks):
            return {"error": "Embedding count mismatch."}

        # 4. Store in Postgres
        async with self._pool.acquire() as conn:
            # Insert document record
            doc_id: int = await conn.fetchval(
                """
                INSERT INTO documents (filename, file_type, file_size, num_chunks, uploaded_by)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                filename,
                file_type,
                len(content),
                len(all_chunks),
                uploaded_by,
            )

            # Batch insert chunks
            chunk_records = [
                (
                    doc_id,
                    chunk.text,
                    chunk.chunk_index,
                    chunk.page_number,
                    chunk.section,
                    json.dumps(embeddings[i]),
                    json.dumps(chunk.metadata),
                )
                for i, chunk in enumerate(all_chunks)
            ]
            await conn.executemany(
                """
                INSERT INTO document_chunks
                    (document_id, chunk_text, chunk_index, page_number,
                     section, embedding, metadata)
                VALUES ($1, $2, $3, $4, $5, $6::vector, $7::jsonb)
                """,
                chunk_records,
            )

        logger.info(
            "RAG: ingested '%s' (%s) — %d pages, %d chunks.",
            filename,
            file_type,
            len(pages),
            len(all_chunks),
        )

        return {
            "document_id": doc_id,
            "filename": filename,
            "file_type": file_type,
            "file_size": len(content),
            "pages": len(pages),
            "chunks": len(all_chunks),
        }

    # ── Retrieval ────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        document_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search across document chunks.

        Args:
            query: Search query text.
            top_k: Number of top results to return.
            document_id: Optional filter to search within a specific document.

        Returns:
            List of matching chunks with scores and metadata.
        """
        if not self._started:
            return [{"error": "RAG service not started."}]

        # Embed the query
        query_embedding = self._embedder.embed_query(query)
        if not query_embedding:
            return [{"error": "Failed to embed query."}]

        embedding_str = json.dumps(query_embedding)

        # Build query with optional document filter
        if document_id is not None:
            rows = await self._pool.fetch(
                """
                SELECT
                    dc.chunk_text,
                    dc.page_number,
                    dc.section,
                    dc.metadata,
                    d.filename,
                    d.file_type,
                    1 - (dc.embedding <=> $1::vector) AS similarity
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE dc.document_id = $2
                ORDER BY dc.embedding <=> $1::vector
                LIMIT $3
                """,
                embedding_str,
                document_id,
                top_k,
            )
        else:
            rows = await self._pool.fetch(
                """
                SELECT
                    dc.chunk_text,
                    dc.page_number,
                    dc.section,
                    dc.metadata,
                    d.filename,
                    d.file_type,
                    1 - (dc.embedding <=> $1::vector) AS similarity
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                ORDER BY dc.embedding <=> $1::vector
                LIMIT $2
                """,
                embedding_str,
                top_k,
            )

        results: list[dict[str, Any]] = []
        for row in rows:
            results.append({
                "text": row["chunk_text"],
                "source": row["filename"],
                "file_type": row["file_type"],
                "page": row["page_number"],
                "section": row["section"],
                "score": round(float(row["similarity"]), 4),
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            })

        return results

    # ── Document management ──────────────────────────────────────

    async def list_documents(self) -> list[dict[str, Any]]:
        """List all uploaded documents."""
        if not self._started:
            return [{"error": "RAG service not started."}]

        rows = await self._pool.fetch(
            """
            SELECT id, filename, file_type, file_size, num_chunks,
                   uploaded_by, created_at
            FROM documents
            ORDER BY created_at DESC
            """
        )
        return [
            {
                "id": row["id"],
                "filename": row["filename"],
                "file_type": row["file_type"],
                "file_size": row["file_size"],
                "num_chunks": row["num_chunks"],
                "uploaded_by": row["uploaded_by"],
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    async def get_document(self, document_id: int) -> dict[str, Any]:
        """Get full document content (all chunks concatenated)."""
        if not self._started:
            return {"error": "RAG service not started."}

        doc = await self._pool.fetchrow(
            "SELECT * FROM documents WHERE id = $1", document_id
        )
        if doc is None:
            return {"error": f"Document {document_id} not found."}

        chunks = await self._pool.fetch(
            """
            SELECT chunk_text, chunk_index, page_number, section
            FROM document_chunks
            WHERE document_id = $1
            ORDER BY chunk_index
            """,
            document_id,
        )

        return {
            "id": doc["id"],
            "filename": doc["filename"],
            "file_type": doc["file_type"],
            "num_chunks": doc["num_chunks"],
            "content": "\n\n".join(row["chunk_text"] for row in chunks),
            "chunks": [
                {
                    "index": row["chunk_index"],
                    "page": row["page_number"],
                    "section": row["section"],
                    "text": row["chunk_text"][:200] + "..."
                    if len(row["chunk_text"]) > 200
                    else row["chunk_text"],
                }
                for row in chunks
            ],
        }

    async def delete_document(self, document_id: int) -> dict[str, Any]:
        """Delete a document and all its chunks."""
        if not self._started:
            return {"error": "RAG service not started."}

        doc = await self._pool.fetchrow(
            "SELECT filename FROM documents WHERE id = $1", document_id
        )
        if doc is None:
            return {"error": f"Document {document_id} not found."}

        await self._pool.execute(
            "DELETE FROM documents WHERE id = $1", document_id
        )
        return {
            "deleted": True,
            "document_id": document_id,
            "filename": doc["filename"],
        }
