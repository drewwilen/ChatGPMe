# ChatGPMe Backend MVP (Ingestion)

## What is implemented
- Connector interface: `BaseConnector`
- Local connector: `LocalFilesConnector` for `.txt` and `.md`
- Google Drive connector: `GoogleDriveConnector` (OAuth + text/doc ingestion)
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

Ingest from Google Drive (OAuth on first run):

```bash
PYTHONPATH=backend python -m chatgpme.cli ingest \
  --user-id demo_user \
  --source-type google_drive \
  --source-config-json '{
    "credentials_path":"backend/secrets/google_credentials.json",
    "token_path":"backend/secrets/google_token.json",
    "owner_only":true,
    "max_files":20
  }'
```

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

Google Drive ingest request:

```bash
curl -X POST http://127.0.0.1:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo_user",
    "source_type": "google_drive",
    "source_config": {
      "credentials_path": "backend/secrets/google_credentials.json",
      "token_path": "backend/secrets/google_token.json",
      "owner_only": true,
      "max_files": 20
    }
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

## Google Drive Setup
1. In Google Cloud Console, create/select a project.
2. Enable `Google Drive API`.
3. Configure OAuth consent screen (External is fine for dev).
4. Create OAuth client credentials for Desktop app.
5. Download the JSON and place it at `backend/secrets/google_credentials.json`.
6. Run ingest with `source_type=google_drive`; first run opens browser auth.
7. Token cache is saved to `backend/secrets/google_token.json`.
8. Defaults are owner-only and Google Docs-only. Override with:
   - `owner_only=false` to include shared files
   - `include_mime_types=["application/vnd.google-apps.document","text/plain"]` for additional text files
