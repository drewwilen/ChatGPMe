from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Chunk
from .storage import CorpusStore


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


@dataclass(slots=True)
class RetrievedChunk:
    chunk: Chunk
    score: float


class StyleRetriever:
    def __init__(self, store: CorpusStore | None = None) -> None:
        self.store = store or CorpusStore()

    def retrieve(self, user_id: str, prompt: str, top_k: int = 3) -> list[RetrievedChunk]:
        query_tokens = set(_tokenize(prompt))
        if not query_tokens:
            return []

        candidates = self.store.get_user_chunks(user_id)
        scored: list[RetrievedChunk] = []
        for chunk in candidates:
            chunk_tokens = set(_tokenize(chunk.text))
            if not chunk_tokens:
                continue
            overlap = query_tokens.intersection(chunk_tokens)
            if not overlap:
                continue
            score = len(overlap) / len(query_tokens)
            scored.append(RetrievedChunk(chunk=chunk, score=score))

        scored.sort(key=lambda item: item.score, reverse=True)

        unique: list[RetrievedChunk] = []
        seen_texts: set[str] = set()
        for item in scored:
            normalized_text = " ".join(item.chunk.text.split())
            if normalized_text in seen_texts:
                continue
            seen_texts.add(normalized_text)
            unique.append(item)
            if len(unique) >= max(1, top_k):
                break

        return unique
