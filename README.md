# ChatGPMe: Style-Aware Writing Assistant

A backend-first MVP system that ingest writing samples, retrieves style-relevant context, generates text in that style, and evaluates whether it outperforms generic baselines.

## Quick Start

### 1. Set Up Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings (API keys, ports, etc.)
# Then activate the virtual environment
source .venv/bin/activate
```

### 2. Start the Web App

```bash
python scripts/cli.py serve
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

Features:
- **Editor tab**: Type naturally, get continuation suggestions (Tab to accept, Esc to dismiss)
- **Assistant tab**: Draft, rewrite, or continue in your style (demo uses TinyLlama + LoRA adapter)

### 3. Check Configuration

```bash
python scripts/cli.py config
```

This displays your current configuration and validates settings.

## Full Pipeline

### Step 1: Ingest Corpus

Extract and process writing samples:

```bash
# Extract from local documents
python scripts/cli.py ingest \
  --input data/raw/google_drive_docs \
  --output data/corpus \
  --manifest data/metadata/extraction_manifest.json
```

Supported formats: `.txt`, `.md`, `.docx`, `.doc`

### Step 2: Build LoRA Dataset

Prepare data for training:

```bash
python scripts/build_lora_dataset.py \
  --input-dir data/corpus \
  --output-dir data/processed
```

This creates:
- `data/processed/chunks.jsonl` - Cleaned chunks with metadata
- `data/processed/train.jsonl` - Training examples
- `data/processed/summary.json` - Dataset statistics

### Step 3: Convert to Style Training Format

```bash
python scripts/build_style_train_dataset.py \
  --input-path data/processed/chunks.jsonl \
  --output-path data/style_train/style_train.jsonl
```

### Step 4: Train LoRA Adapter

```bash
python scripts/train_lora.py \
  --model-name TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --dataset-path data/style_train/style_train.jsonl \
  --output-dir artifacts/my-style-lora \
  --epochs 3
```

### Step 5: Generate Text

With your trained adapter:

```bash
python scripts/cli.py generate \
  --model TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --adapter artifacts/my-style-lora \
  --prompt "Your writing starts here" \
  --max-tokens 250
```

Or use the web interface after updating `CHATGPME_ADAPTER` in `.env`.

### Step 6: Evaluate Outputs

Compare baseline vs. personalized outputs:

```bash
python scripts/cli.py demo  # See example with Shakespeare data

# Or evaluate your own outputs:
python scripts/cli.py eval \
  --author "Author Name" \
  --prompts eval_prompts.json \
  --baseline baseline_outputs.json \
  --candidate candidate_outputs.json \
  --model gpt-4o-mini \
  --output report.json
```

See [GRADER_README.md](GRADER_README.md) for evaluation system details.

## CLI Commands

```bash
# Show all commands
python scripts/cli.py --help

# Configuration
python scripts/cli.py config

# Start web server
python scripts/cli.py serve

# Run grader demo (Shakespeare example)
python scripts/cli.py demo --model gpt-4o-mini

# Evaluate outputs
python scripts/cli.py eval \
  --author "AuthorName" \
  --prompts prompts.json \
  --baseline baseline.json \
  --candidate candidate.json

# Ingest corpus
python scripts/cli.py ingest --input <path> --output <path>

# Generate text
python scripts/cli.py generate --prompt "..." --max-tokens 250
```

Add `-v` or `--verbose` flag for detailed logging:

```bash
python scripts/cli.py -v serve
```

## Configuration

Configuration is centralized in `scripts/config.py` and can be overridden via environment variables or `.env` file.

### Key Settings

| Setting | Env Var | Default | Purpose |
|---------|---------|---------|---------|
| Model | `CHATGPME_MODEL` | `TinyLlama/TinyLlama-1.1B-Chat-v1.0` | Base language model |
| Adapter | `CHATGPME_ADAPTER` | `artifacts/tinyllama-style-lora-mvp` | LoRA adapter path |
| Device | `CHATGPME_DEVICE` | `auto` | `cuda`, `cpu`, or `auto` |
| Host | `CHATGPME_HOST` | `127.0.0.1` | Server bind address |
| Port | `CHATGPME_PORT` | `8000` | Server port |
| Remote API | `CHATGPME_REMOTE_API` | (none) | Remote generation endpoint |
| Eval Model | `CHATGPME_EVAL_MODEL` | `gpt-4o-mini` | LLM for evaluation |
| OpenAI API | `OPENAI_API_KEY` | (none) | Required for evaluation |
| Log Level | `CHATGPME_LOG_LEVEL` | `INFO` | Logging verbosity |

### Example .env

```bash
CHATGPME_MODEL=TinyLlama/TinyLlama-1.1B-Chat-v1.0
CHATGPME_ADAPTER=artifacts/my-custom-adapter
CHATGPME_DEVICE=cuda
CHATGPME_HOST=0.0.0.0
CHATGPME_PORT=8000
CHATGPME_LOG_LEVEL=DEBUG
OPENAI_API_KEY=sk-...
```

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Web UI (webapp/)                        │
│  Editor tab (suggestions) | Assistant tab (drafting)        │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│              Backend API (run_app.py)                       │
│  - Health checks                                            │
│  - Text generation (with/without adapter)                  │
│  - Mode selection (continue, draft, rewrite)               │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
┌───────┴────┐  ┌──────┴──────┐ ┌──────┴──────┐
│ Generation │  │  Evaluation │ │  Ingestion  │
├────────────┤  ├─────────────┤ ├─────────────┤
│ Base model │  │ LLM Judge   │ │ Corpus proc │
│ LoRA adapt │  │ Grading     │ │ Chunking    │
│ Inference  │  │ Aggregation │ │ Cleanup     │
└────────────┘  └─────────────┘ └─────────────┘
```

### Data Flow

1. **Ingestion** (`extract_corpus.py`, `build_lora_dataset.py`)
   - Raw files → Cleaned text
   - Text → Chunks with metadata

2. **Training** (`train_lora.py`)
   - Chunks → LoRA adapter
   - Saves to `artifacts/`

3. **Generation** (`run_app.py`, `generate_with_adapter.py`)
   - Prompt + model + adapter → Completion
   - Supports multiple modes (continue, draft, rewrite)

4. **Evaluation** (`grader.py`, `evaluate.py`)
   - Baseline + candidate outputs
   - LLM judge scores style dimensions
   - Aggregates metrics per author/genre

## File Structure

```
ChatGPMe/
├── scripts/                   # Core Python modules
│   ├── cli.py                 # Main CLI interface
│   ├── config.py              # Configuration management
│   ├── run_app.py             # Web server
│   ├── generate_with_adapter.py
│   ├── train_lora.py
│   ├── extract_corpus.py
│   ├── build_lora_dataset.py
│   ├── grader.py              # Evaluation orchestrator
│   ├── grader_types.py        # Eval data structures
│   ├── grader_judge.py        # LLM judge
│   ├── grader_comparator.py   # Comparison logic
│   ├── grader_aggregator.py   # Result aggregation
│   └── ...
├── webapp/                    # Web interface
│   ├── index.html
│   ├── app.js
│   └── app.css
├── data/                      # Data (gitignored)
│   ├── corpus/                # Extracted text
│   ├── processed/             # Training data
│   ├── style_train/           # Style training set
│   ├── eval_demo/             # Demo evaluation results
│   └── ...
├── artifacts/                 # Models (gitignored)
│   └── tinyllama-style-lora-mvp/
├── logs/                      # Logs (gitignored)
├── planning/                  # Project planning
├── notebooks/                 # Jupyter notebooks
├── .env.example               # Configuration template
├── GRADER_README.md           # Evaluation documentation
└── requirements.txt           # Python dependencies
```

## Development

### Testing

```bash
# Test grader
python test_grader.py

# Test webapp
python scripts/run_app.py  # Then visit http://127.0.0.1:8000
```

### Adding Dependencies

```bash
pip install <package>
pip freeze > requirements.txt
```

### Logging

Logs are written to `logs/chatgpme.log` and printed to stderr. Control verbosity with `CHATGPME_LOG_LEVEL`:

```bash
CHATGPME_LOG_LEVEL=DEBUG python scripts/cli.py serve
```

## Use from Colab

See [notebooks/chatgpme_colab_mvp.ipynb](notebooks/chatgpme_colab_mvp.ipynb) for a complete Colab example.

## Troubleshooting

### Model Not Loading
- Check `python scripts/cli.py config` output
- Verify `CHATGPME_ADAPTER` path exists
- Try `CHATGPME_DEVICE=cpu` if GPU issues

### Evaluation API Errors
- Set `OPENAI_API_KEY` environment variable
- Check API key validity and quota

### Port Already in Use
- Change `CHATGPME_PORT` environment variable
- Or kill the process: `lsof -i :8000 | xargs kill`

### Memory Issues
- Reduce `CHATGPME_DEVICE` to `cpu` (slower but lower memory)
- Use smaller model than TinyLlama

## Privacy

Everything under `data/` and `artifacts/` is gitignored. Only code and configs are version controlled.

## License & Attribution

Training data (Shakespeare, Trump speeches) is public domain or fair use for research.

## Next Steps

- [ ] Integration with Google Drive corpus ingestion
- [ ] Gmail connector for writing samples
- [ ] Web-based corpus management UI
- [ ] Batch evaluation across authors
- [ ] Cost tracking for LLM evaluations
- [ ] Human evaluation comparison
- [ ] Chrome extension integration
