# ChatGPMe Backend MVP (Ingestion)

## What is implemented
- Connector interface: `BaseConnector`
- Local connector: `LocalFilesConnector` for `.txt` and `.md`
- Preprocessing: text cleaning + chunking
- Storage:
  - JSONL artifacts at `data/users/<user_id>/`
  - SQLite metadata at `data/chatgpme.db`
- CLI ingestion command

## Run
From repo root:

```bash
PYTHONPATH=backend python -m chatgpme.cli ingest \
  --user-id demo_user \
  --source-dir planning
```

You should see a JSON summary with `documents_ingested` and `chunks_created`.

Generate a draft from ingested data:

```bash
PYTHONPATH=backend python -m chatgpme.cli generate \
  --user-id demo_user \
  --mode personalized \
  --prompt "Write a short update about our MVP progress"
```

## API
Install dependencies:

```bash
pip install -r backend/requirements.txt
```

Start API:

```bash
PYTHONPATH=backend uvicorn chatgpme.api:app --reload
```

Example request:

```bash
curl -X POST http://127.0.0.1:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo_user",
    "source_type": "local_files",
    "source_config": {"source_dir": "planning"}
  }'
```

Generate request:

```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo_user",
    "mode": "personalized",
    "prompt": "Write a short update about our MVP progress",
    "top_k": 3
  }'
```
