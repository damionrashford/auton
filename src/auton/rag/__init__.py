"""Retrieval-Augmented Generation (RAG) pipeline.

Provides document upload, parsing, chunking, local embedding, and
semantic search across uploaded documents.  Uses ``sentence-transformers``
with ``bge-small-en-v1.5`` for fast local 384-dim embeddings and
pgvector for HNSW cosine similarity search.
"""

from auton.rag.service import RAGService
from auton.rag.tools import RAG_TOOLS, handle_rag_tool

__all__ = ["RAGService", "RAG_TOOLS", "handle_rag_tool"]
