from __future__ import annotations

import re
import uuid

from .models import Chunk, Document


def clean_text(text: str) -> str:
    """Light cleanup: normalize newlines/spaces and strip noisy blank runs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def estimate_tokens(text: str) -> int:
    # Rough approximation for MVP planning/eval bookkeeping.
    return max(1, len(text) // 4)


def chunk_text(text: str, chunk_size_chars: int = 1200, overlap_chars: int = 200) -> list[str]:
    if chunk_size_chars <= overlap_chars:
        raise ValueError("chunk_size_chars must be > overlap_chars")

    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    step = chunk_size_chars - overlap_chars
    while start < len(text):
        end = min(start + chunk_size_chars, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start += step

    return chunks


def preprocess_documents(
    documents: list[Document],
    chunk_size_chars: int = 1200,
    overlap_chars: int = 200,
) -> tuple[list[Document], list[Chunk]]:
    all_chunks: list[Chunk] = []

    for doc in documents:
        doc.text = clean_text(doc.text)
        chunk_texts = chunk_text(doc.text, chunk_size_chars=chunk_size_chars, overlap_chars=overlap_chars)

        doc_chunks: list[Chunk] = []
        for i, text in enumerate(chunk_texts):
            chunk = Chunk(
                id=str(uuid.uuid4()),
                document_id=doc.id,
                text=text,
                chunk_index=i,
                token_estimate=estimate_tokens(text),
            )
            doc_chunks.append(chunk)

        doc.chunk_ids = [c.id for c in doc_chunks]
        all_chunks.extend(doc_chunks)

    return documents, all_chunks
