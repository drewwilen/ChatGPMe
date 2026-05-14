from __future__ import annotations

from dataclasses import dataclass

from .connectors import (
    AccessTokenGoogleDriveConnector,
    BaseConnector,
    GoogleDriveConnector,
    LocalFilesConnector,
)
from .preprocess import preprocess_documents
from .storage import CorpusStore


@dataclass(slots=True)
class IngestSummary:
    user_id: str
    source_type: str
    documents_ingested: int
    chunks_created: int


class IngestionPipeline:
    def __init__(self, store: CorpusStore | None = None) -> None:
        self.store = store or CorpusStore()
        self.connector_registry: dict[str, BaseConnector] = {
            "local_files": LocalFilesConnector(),
            "google_drive": GoogleDriveConnector(),
            "google_drive_token": AccessTokenGoogleDriveConnector(),
        }

    def ingest(self, user_id: str, source_type: str, source_config: dict) -> IngestSummary:
        connector = self.connector_registry.get(source_type)
        if connector is None:
            supported = ", ".join(sorted(self.connector_registry.keys()))
            raise ValueError(f"Unsupported source_type '{source_type}'. Supported: {supported}")

        docs = connector.load_user_corpus(user_id=user_id, source_config=source_config)
        docs, chunks = preprocess_documents(docs)
        self.store.save(user_id=user_id, documents=docs, chunks=chunks)

        return IngestSummary(
            user_id=user_id,
            source_type=source_type,
            documents_ingested=len(docs),
            chunks_created=len(chunks),
        )
