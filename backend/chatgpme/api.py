from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .generation import DraftGenerator
from .pipeline import IngestionPipeline

app = FastAPI(title="ChatGPMe MVP API", version="0.1.0")
pipeline = IngestionPipeline()
generator = DraftGenerator(store=pipeline.store)


class IngestRequest(BaseModel):
    user_id: str = Field(min_length=1)
    source_type: str = "local_files"
    source_config: dict = Field(default_factory=dict)


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
