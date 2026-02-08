"""Recursive character text splitter for document chunking.

Splits text into overlapping chunks that respect natural boundaries
(paragraphs > lines > sentences > words).  Each chunk fits within
the embedding model's token window (512 tokens ≈ 500 characters
for ``bge-small-en-v1.5``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    """A single text chunk ready for embedding."""

    text: str
    chunk_index: int
    page_number: int = 0
    section: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# Separators ordered by priority (most natural boundary first).
_SEPARATORS = [
    "\n\n",   # Paragraph break
    "\n",     # Line break
    ". ",     # Sentence end
    "? ",     # Question end
    "! ",     # Exclamation end
    "; ",     # Semicolon
    ", ",     # Comma
    " ",      # Word boundary
    "",       # Character boundary (last resort)
]


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
    *,
    page_number: int = 0,
    section: str = "",
    metadata: dict[str, Any] | None = None,
) -> list[Chunk]:
    """Split text into overlapping chunks respecting natural boundaries.

    Args:
        text: The text to chunk.
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.
        page_number: Page number for metadata.
        section: Section heading for metadata.
        metadata: Additional metadata to attach to each chunk.

    Returns:
        List of Chunk objects.
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    if len(text) <= chunk_size:
        return [
            Chunk(
                text=text,
                chunk_index=0,
                page_number=page_number,
                section=section,
                metadata=metadata or {},
            )
        ]

    splits = _recursive_split(text, chunk_size, _SEPARATORS)
    return _merge_splits(
        splits,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        page_number=page_number,
        section=section,
        metadata=metadata or {},
    )


def _recursive_split(
    text: str,
    chunk_size: int,
    separators: list[str],
) -> list[str]:
    """Recursively split text using the highest-priority separator that works."""
    if len(text) <= chunk_size:
        return [text]

    # Find the best separator
    sep = ""
    for candidate in separators:
        if candidate in text:
            sep = candidate
            break

    if not sep:
        # No separator works — hard split by characters
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    parts = text.split(sep)
    # Filter out empty strings
    parts = [p for p in parts if p.strip()]

    # Recursively split any parts that are still too large
    result: list[str] = []
    for part in parts:
        if len(part) <= chunk_size:
            result.append(part)
        else:
            # Try next separator
            remaining_seps = separators[separators.index(sep) + 1:]
            result.extend(_recursive_split(part, chunk_size, remaining_seps))

    return result


def _merge_splits(
    splits: list[str],
    chunk_size: int,
    chunk_overlap: int,
    page_number: int,
    section: str,
    metadata: dict[str, Any],
) -> list[Chunk]:
    """Merge small splits into target-sized chunks with overlap."""
    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_len = 0
    chunk_idx = 0

    for split in splits:
        split_len = len(split)

        if current_len + split_len > chunk_size and current_parts:
            # Emit current chunk
            chunk_text_str = " ".join(current_parts).strip()
            if chunk_text_str:
                chunks.append(
                    Chunk(
                        text=chunk_text_str,
                        chunk_index=chunk_idx,
                        page_number=page_number,
                        section=section,
                        metadata=metadata,
                    )
                )
                chunk_idx += 1

            # Keep overlap from the end of current parts
            overlap_parts: list[str] = []
            overlap_len = 0
            for part in reversed(current_parts):
                if overlap_len + len(part) > chunk_overlap:
                    break
                overlap_parts.insert(0, part)
                overlap_len += len(part)

            current_parts = overlap_parts
            current_len = overlap_len

        current_parts.append(split)
        current_len += split_len

    # Emit final chunk
    if current_parts:
        chunk_text_str = " ".join(current_parts).strip()
        if chunk_text_str:
            chunks.append(
                Chunk(
                    text=chunk_text_str,
                    chunk_index=chunk_idx,
                    page_number=page_number,
                    section=section,
                    metadata=metadata,
                )
            )

    return chunks
