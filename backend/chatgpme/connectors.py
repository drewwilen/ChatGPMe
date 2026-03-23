from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import uuid

from .models import Document


class BaseConnector(ABC):
    @abstractmethod
    def load_user_corpus(self, user_id: str, source_config: dict) -> list[Document]:
        """Return normalized documents for a user corpus source."""


class LocalFilesConnector(BaseConnector):
    SUPPORTED_EXTENSIONS = {".txt", ".md"}

    def load_user_corpus(self, user_id: str, source_config: dict) -> list[Document]:
        source_dir = source_config.get("source_dir")
        if not source_dir:
            raise ValueError("source_config must include 'source_dir'")

        directory = Path(source_dir).expanduser().resolve()
        if not directory.exists() or not directory.is_dir():
            raise ValueError(f"Invalid source directory: {directory}")

        documents: list[Document] = []
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")
            if not text.strip():
                continue

            doc = Document(
                id=str(uuid.uuid4()),
                user_id=user_id,
                source="local_files",
                source_path=str(path),
                text=text,
                doc_type=path.suffix.lower().lstrip("."),
            )
            documents.append(doc)

        return documents
