from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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


class IngestRequest(BaseModel):
    user_id: str = Field(min_length=1)
    source_type: str = "local_files"
    source_config: dict = Field(default_factory=dict)


class GDriveIngestRequest(BaseModel):
    user_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1)
    max_files: int = Field(default=25, ge=1, le=200)
    owner_only: bool = True


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
