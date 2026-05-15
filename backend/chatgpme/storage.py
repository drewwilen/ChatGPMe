from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import Chunk, Document


class CorpusStore:
    def __init__(self, root_dir: str = "data") -> None:
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.sqlite_path = self.root / "chatgpme.db"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    created_at TEXT,
                    chunk_count INTEGER NOT NULL,
                    text_length INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    token_estimate INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id)
                )
                """
            )
            conn.commit()

    def save(self, user_id: str, documents: list[Document], chunks: list[Chunk]) -> None:
        user_dir = self.root / "users" / user_id
        user_dir.mkdir(parents=True, exist_ok=True)

        docs_path = user_dir / "documents.jsonl"
        chunks_path = user_dir / "chunks.jsonl"

        with docs_path.open("w", encoding="utf-8") as f:
            for doc in documents:
                payload = asdict(doc)
                created_at = payload.get("created_at")
                if isinstance(created_at, datetime):
                    payload["created_at"] = created_at.isoformat()
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        with chunks_path.open("w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")

        # style_train.jsonl — {"text": "..."} per chunk, ready for train_lora.py
        style_train_path = user_dir / "style_train.jsonl"
        with style_train_path.open("w", encoding="utf-8") as f:
            for chunk in chunks:
                text = chunk.text.strip()
                if text:
                    f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")

        with sqlite3.connect(self.sqlite_path) as conn:
            # Replace prior corpus snapshot for this user on each ingest.
            conn.execute(
                """
                DELETE FROM chunks
                WHERE document_id IN (
                    SELECT id FROM documents WHERE user_id = ?
                )
                """,
                (user_id,),
            )
            conn.execute("DELETE FROM documents WHERE user_id = ?", (user_id,))

            conn.executemany(
                """
                INSERT OR REPLACE INTO documents
                (id, user_id, source, source_path, doc_type, created_at, chunk_count, text_length)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        d.id,
                        d.user_id,
                        d.source,
                        d.source_path,
                        d.doc_type,
                        d.created_at.isoformat() if d.created_at else None,
                        len(d.chunk_ids),
                        len(d.text),
                    )
                    for d in documents
                ],
            )

            chunks_by_id = {c.id: c for c in chunks}
            conn.executemany(
                """
                INSERT OR REPLACE INTO chunks
                (id, document_id, chunk_index, token_estimate, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.id,
                        c.document_id,
                        c.chunk_index,
                        c.token_estimate,
                        c.text,
                    )
                    for c in chunks_by_id.values()
                ],
            )
            conn.commit()

    def get_user_chunks(self, user_id: str) -> list[Chunk]:
        with sqlite3.connect(self.sqlite_path) as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.document_id, c.text, c.chunk_index, c.token_estimate
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.user_id = ?
                ORDER BY d.source_path, c.chunk_index
                """,
                (user_id,),
            ).fetchall()

        return [
            Chunk(
                id=row[0],
                document_id=row[1],
                text=row[2],
                chunk_index=row[3],
                token_estimate=row[4],
            )
            for row in rows
        ]

    def get_user_state(self, user_id: str) -> dict[str, object]:
        user_dir = self.root / "users" / user_id
        docs_path = user_dir / "documents.jsonl"
        chunks_path = user_dir / "chunks.jsonl"
        style_train_path = user_dir / "style_train.jsonl"
        bundles_dir = user_dir / "bundles"

        with sqlite3.connect(self.sqlite_path) as conn:
            doc_count = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]
            chunk_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.user_id = ?
                """,
                (user_id,),
            ).fetchone()[0]

        available_bundles: list[dict[str, object]] = []
        if bundles_dir.exists():
            for path in sorted(bundles_dir.glob("*.zip")):
                available_bundles.append(
                    {
                        "name": path.name,
                        "size_bytes": path.stat().st_size,
                    }
                )

        style_train_rows = 0
        if style_train_path.exists():
            with style_train_path.open("r", encoding="utf-8") as handle:
                style_train_rows = sum(1 for line in handle if line.strip())

        return {
            "user_id": user_id,
            "has_corpus": docs_path.exists() and chunks_path.exists(),
            "documents_ingested": int(doc_count),
            "chunks_created": int(chunk_count),
            "style_train_path": str(style_train_path),
            "style_train_rows": style_train_rows,
            "bundle_dir": str(bundles_dir),
            "available_bundles": available_bundles,
        }
