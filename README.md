# ChatGPMe

Initial tooling for building a local writing-style corpus from exported Google Drive documents.

Data flow:

1. `data/raw/google_drive_docs/` stores exported source files from Google Drive.
2. `scripts/extract_corpus.py` converts those files into plain text under `data/corpus/`.
3. The extraction step also writes metadata to `data/metadata/extraction_manifest.json`.
4. `scripts/build_lora_dataset.py` turns the corpus into chunked training artifacts under `data/processed/`.
5. `scripts/build_style_train_dataset.py` converts chunked corpus text into raw JSONL for paper-aligned style training.
6. `scripts/train_lora.py` trains a style adapter from raw text sequences.

Privacy:

- Everything under `data/` is gitignored except `data/README.md`.
- That keeps raw files, extracted text, manifests, and training data out of git.

## Extract corpus text

Run:

```bash
python3 scripts/extract_corpus.py
```

This reads files from `data/raw/google_drive_docs/`, converts supported documents to plain text, writes corpus files under `data/corpus/`, and writes extraction metadata to `data/metadata/extraction_manifest.json`.

## Build chunked LoRA dataset

Run:

```bash
python3 scripts/build_lora_dataset.py
```

This reads extracted text from `data/corpus/`, creates cleaned chunks, and writes:

- `data/processed/chunks.jsonl`
- `data/processed/train.jsonl`
- `data/processed/summary.json`

## Build a Raw Style Dataset

```bash
python3 scripts/build_style_train_dataset.py \
  --input-path data/processed/chunks.jsonl \
  --output-path data/style_train/style_train.jsonl
```

## Train a LoRA adapter

Install the Hugging Face stack first, then run:

```bash
python3 scripts/train_lora.py \
  --model-name TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --dataset-path data/style_train/style_train.jsonl \
  --output-dir artifacts/tinyllama-style-lora
```

## Generate with the adapter

```bash
python3 scripts/generate_with_adapter.py \
  --model-name TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --adapter-path artifacts/tinyllama-style-lora \
  --prompt "When I sat down to write this application, I realized that the hardest part was not describing what I had done,"
```

## Run the Local MVP App

Activate the virtual environment first, then run:

```bash
.venv/bin/python scripts/run_app.py
```

Open `http://127.0.0.1:8000`.

Optional environment variables:

- `CHATGPME_MODEL`
- `CHATGPME_ADAPTER`
- `CHATGPME_HOST`
- `CHATGPME_PORT`

The app includes:

- `Editor` tab: continuation suggestions with accept-by-tab
- `Assistant` tab: draft, rewrite, and continue tools using the same backend

## Use the repo directly from Colab

If you want a cleaner path than bundling files, use:

- [notebooks/chatgpme_colab_mvp.ipynb](/Users/Drew/ChatGPMe/notebooks/chatgpme_colab_mvp.ipynb)

That notebook runs the repo scripts directly in Colab or the VS Code Colab extension.
