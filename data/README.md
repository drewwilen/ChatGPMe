# Data Layout

This repository keeps code and documentation in git, but ignores all personal data artifacts under `data/`.

Flow:

1. `data/raw/google_drive_docs/`
   Exported source documents from Google Drive.
2. `data/corpus/`
   Extracted plain-text `.txt` files derived from the raw exports.
3. `data/metadata/extraction_manifest.json`
   Metadata for the extraction step, including source and output paths.
4. `data/processed/`
   Chunked training data and summaries derived from the corpus.

Privacy:

- `data/raw/` contains your original files.
- `data/corpus/` contains your extracted writing.
- `data/metadata/` contains filenames and path metadata tied to your documents.
- `data/processed/` contains chunked training examples built from your writing.

All of those directories are gitignored so personal content does not get committed.
