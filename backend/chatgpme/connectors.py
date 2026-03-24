from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import io
from pathlib import Path
from typing import Any
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


class GoogleDriveConnector(BaseConnector):
    # Keep MVP scope tight: owner-only Google Docs by default.
    DEFAULT_MIME_TYPES = {"application/vnd.google-apps.document"}

    DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

    def load_user_corpus(self, user_id: str, source_config: dict) -> list[Document]:
        creds_path = source_config.get("credentials_path")
        if not creds_path:
            raise ValueError("source_config must include 'credentials_path' for google_drive")

        token_path = source_config.get("token_path", "backend/secrets/google_token.json")
        folder_id = source_config.get("folder_id")
        custom_query = source_config.get("query")
        owner_only = bool(source_config.get("owner_only", True))
        max_files = int(source_config.get("max_files", 25))
        include_mime_types = set(source_config.get("include_mime_types", self.DEFAULT_MIME_TYPES))

        service = self._build_drive_service(
            credentials_path=creds_path,
            token_path=token_path,
        )
        files = self._list_files(
            service=service,
            folder_id=folder_id,
            custom_query=custom_query,
            owner_only=owner_only,
            max_files=max_files,
            include_mime_types=include_mime_types,
        )

        documents: list[Document] = []
        for file_meta in files:
            text = self._download_text(service, file_meta)
            if not text or not text.strip():
                continue

            modified_time = file_meta.get("modifiedTime")
            created_at = None
            if isinstance(modified_time, str):
                # Example: 2026-03-24T16:31:42.123Z
                created_at = datetime.fromisoformat(modified_time.replace("Z", "+00:00"))

            documents.append(
                Document(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    source="google_drive",
                    source_path=f"gdrive://{file_meta['id']}",
                    text=text,
                    doc_type=self._doc_type_from_mime(file_meta.get("mimeType", "")),
                    created_at=created_at,
                )
            )

        return documents

    def _build_drive_service(self, credentials_path: str, token_path: str):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise ValueError(
                "Google Drive dependencies are missing. Install with: "
                "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            ) from exc

        creds = None
        token_file = Path(token_path).expanduser().resolve()
        token_file.parent.mkdir(parents=True, exist_ok=True)
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), self.DRIVE_SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                creds_file = Path(credentials_path).expanduser().resolve()
                if not creds_file.exists():
                    raise ValueError(f"credentials_path not found: {creds_file}")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(creds_file),
                    self.DRIVE_SCOPES,
                )
                creds = flow.run_local_server(port=0)

            token_file.write_text(creds.to_json(), encoding="utf-8")

        return build("drive", "v3", credentials=creds)

    def _list_files(
        self,
        service,
        folder_id: str | None,
        custom_query: str | None,
        owner_only: bool,
        max_files: int,
        include_mime_types: set[str],
    ) -> list[dict[str, Any]]:
        mime_filter = " or ".join([f"mimeType='{mime}'" for mime in sorted(include_mime_types)])
        base_parts = ["trashed=false"]
        if mime_filter:
            base_parts.append(f"({mime_filter})")
        if folder_id:
            base_parts.append(f"'{folder_id}' in parents")
        if owner_only:
            base_parts.append("'me' in owners")
        if custom_query:
            base_parts.append(f"({custom_query})")
        query = " and ".join(base_parts)

        response = (
            service.files()
            .list(
                q=query,
                pageSize=max_files,
                fields="files(id,name,mimeType,modifiedTime)",
                orderBy="modifiedTime desc",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        return response.get("files", [])

    def _download_text(self, service, file_meta: dict[str, Any]) -> str:
        try:
            from googleapiclient.http import MediaIoBaseDownload
        except ImportError as exc:
            raise ValueError(
                "Google Drive dependencies are missing. Install with: "
                "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            ) from exc

        file_id = file_meta["id"]
        mime_type = file_meta.get("mimeType", "")
        if mime_type == "application/vnd.google-apps.document":
            request = service.files().export_media(fileId=file_id, mimeType="text/plain")
        else:
            request = service.files().get_media(fileId=file_id)

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        return buffer.getvalue().decode("utf-8", errors="ignore")

    def _doc_type_from_mime(self, mime_type: str) -> str:
        mapping = {
            "application/vnd.google-apps.document": "gdoc",
            "text/plain": "txt",
        }
        return mapping.get(mime_type, mime_type.replace("/", "_"))
