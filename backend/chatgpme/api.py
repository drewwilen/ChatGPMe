from __future__ import annotations

import os
import shutil

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .bundles import ColabBundleBuilder
from .connectors import AccessTokenGoogleDriveConnector
from .generation import DraftGenerator
from .pipeline import IngestionPipeline

app = FastAPI(title="ChatGPMe MVP API", version="0.1.0")

# Allow the Vercel frontend (and local dev) to call this backend.
# Set FRONTEND_URL in your Railway/Render env to your Vercel deployment URL.
_allowed_origins = [
    "http://localhost:3000",
    os.environ.get("FRONTEND_URL", ""),
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in _allowed_origins if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = IngestionPipeline()
generator = DraftGenerator(store=pipeline.store)
bundle_builder = ColabBundleBuilder(store=pipeline.store)
token_connector = AccessTokenGoogleDriveConnector()


class IngestRequest(BaseModel):
    user_id: str = Field(min_length=1)
    source_type: str = "local_files"
    source_config: dict = Field(default_factory=dict)


class GDriveIngestRequest(BaseModel):
    user_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1)
    max_files: int = Field(default=25, ge=1, le=5000)
    owner_only: bool = True
    file_ids: list[str] = Field(default_factory=list)


class GDriveFilesRequest(BaseModel):
    access_token: str = Field(min_length=1)
    max_files: int = Field(default=25, ge=1, le=5000)
    owner_only: bool = True


class BundleBuildRequest(BaseModel):
    user_id: str = Field(min_length=1)
    bundle_name: str | None = None


class GenerateRequest(BaseModel):
    user_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    mode: str = Field(default="baseline")
    top_k: int = Field(default=3, ge=1, le=10)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestRequest) -> dict:
    try:
        summary = pipeline.ingest(
            user_id=req.user_id,
            source_type=req.source_type,
            source_config=req.source_config,
        )
        return {
            "user_id": summary.user_id,
            "source_type": summary.source_type,
            "documents_ingested": summary.documents_ingested,
            "chunks_created": summary.chunks_created,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected ingest error: {exc}") from exc


@app.post("/ingest/gdrive")
def ingest_gdrive(req: GDriveIngestRequest) -> dict:
    """Ingest Google Drive docs using an OAuth access token from the web frontend.

    The token is obtained by NextAuth on the Vercel frontend after the user
    clicks "Sign in with Google" — no credentials setup required for end users.
    """
    try:
        summary = pipeline.ingest(
            user_id=req.user_id,
            source_type="google_drive_token",
            source_config={
                "access_token": req.access_token,
                "max_files": req.max_files,
                "owner_only": req.owner_only,
                "file_ids": req.file_ids,
            },
        )
        return {
            "user_id": summary.user_id,
            "source_type": summary.source_type,
            "documents_ingested": summary.documents_ingested,
            "chunks_created": summary.chunks_created,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected Google Drive ingest error: {exc}") from exc


@app.post("/gdrive/files")
def list_gdrive_files(req: GDriveFilesRequest) -> dict:
    try:
        files = token_connector.list_user_files(
            req.access_token,
            max_files=req.max_files,
            owner_only=req.owner_only,
        )
        return {"files": files}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected Google Drive listing error: {exc}") from exc


@app.get("/users/{user_id}/state")
def get_user_state(user_id: str) -> dict:
    return pipeline.store.get_user_state(user_id)


@app.post("/bundle/build")
def build_bundle(req: BundleBuildRequest) -> dict:
    try:
        result = bundle_builder.build_for_user(req.user_id, req.bundle_name)
        return {
            "user_id": result.user_id,
            "bundle_name": result.bundle_name,
            "dataset_rows": result.dataset_rows,
            "adapter_dir_name": result.adapter_dir_name,
            "download_path": f"/bundle/download/{result.user_id}/{result.bundle_name}",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected bundle build error: {exc}") from exc


@app.get("/bundle/download/{user_id}/{bundle_name}")
def download_bundle(user_id: str, bundle_name: str, background_tasks: BackgroundTasks) -> FileResponse:
    try:
        result, bundle_path, temp_root = bundle_builder.create_bundle_archive(user_id, bundle_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected bundle download error: {exc}") from exc

    background_tasks.add_task(shutil.rmtree, temp_root, ignore_errors=True)
    return FileResponse(bundle_path, media_type="application/zip", filename=f"{result.bundle_name}.zip")


@app.post("/generate")
def generate(req: GenerateRequest) -> dict:
    try:
        draft = generator.generate_in_user_style(
            user_id=req.user_id,
            prompt=req.prompt,
            mode=req.mode,
            top_k=req.top_k,
        )
        return {
            "user_id": draft.user_id,
            "mode": draft.mode,
            "prompt": draft.prompt,
            "used_model": draft.used_model,
            "retrieved_examples": draft.retrieved_examples,
            "assembled_prompt": draft.assembled_prompt,
            "text": draft.text,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
