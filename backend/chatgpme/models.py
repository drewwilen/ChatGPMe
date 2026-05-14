from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Chunk:
    id: str
    document_id: str
    text: str
    chunk_index: int
    token_estimate: int


@dataclass(slots=True)
class Document:
    id: str
    user_id: str
    source: str
    source_path: str
    text: str
    doc_type: str
    created_at: datetime | None = None
    chunk_ids: list[str] = field(default_factory=list)
