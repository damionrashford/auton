"""Local embedding model using sentence-transformers.

Loads ``BAAI/bge-small-en-v1.5`` (384-dim, 130MB) once at startup and
keeps it in memory for fast CPU inference.  Supports both single-text
and batch embedding.

The model runs entirely on CPU — no GPU required.  Typical latency:
  - Single text: <5ms
  - Batch of 100: ~50ms
  - Batch of 1000: ~500ms
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Default model — best quality/speed ratio at 384 dimensions.
_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
_EMBEDDING_DIM = 384


class LocalEmbedder:
    """Wraps sentence-transformers for local CPU embedding."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model: Any = None
        self._started = False

    @property
    def is_ready(self) -> bool:
        return self._started

    @property
    def dimension(self) -> int:
        return _EMBEDDING_DIM

    def start(self) -> None:
        """Load the model into memory (blocking, ~2s on first run)."""
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self._model_name,
                device="cpu",
            )
            self._started = True
            logger.info(
                "LocalEmbedder ready: model=%s, dim=%d",
                self._model_name,
                _EMBEDDING_DIM,
            )
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers. "
                "RAG embedding will not be available."
            )
        except Exception:
            logger.warning(
                "LocalEmbedder initialization failed.",
                exc_info=True,
            )

    def embed(self, text: str) -> list[float]:
        """Embed a single text string. Returns a 384-dim vector."""
        if self._model is None:
            return []
        # bge models benefit from prefixing queries with "Represent ..."
        # but for document chunks we skip the prefix.
        embedding: np.ndarray = self._model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding.tolist()  # type: ignore[no-any-return]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single batch (much faster)."""
        if self._model is None:
            return []
        embeddings: np.ndarray = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=64,
        )
        return embeddings.tolist()  # type: ignore[no-any-return]

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query (with retrieval prefix for bge models)."""
        if self._model is None:
            return []
        # bge models use a query prefix for better retrieval performance.
        prefixed = f"Represent this sentence for searching relevant passages: {query}"
        embedding: np.ndarray = self._model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding.tolist()  # type: ignore[no-any-return]
