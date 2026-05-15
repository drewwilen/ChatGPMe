# ChatGPMe Quick Reference Guide

## 🚀 Quick Start (5 minutes)

```bash
# 1. Setup environment
python setup.py
source .venv/bin/activate

# 2. Configure (edit .env with your API keys)
cp .env.example .env
nano .env

# 3. Start web app
python scripts/cli.py serve

# 4. Open http://127.0.0.1:8000
```

## 📋 CLI Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `config` | Show/validate setup | `python scripts/cli.py config` |
| `serve` | Start web app | `python scripts/cli.py serve` |
| `demo` | Run eval demo | `python scripts/cli.py demo --model gpt-4o-mini` |
| `eval` | Evaluate outputs | `python scripts/cli.py eval --author "X" --prompts p.json ...` |
| `ingest` | Process corpus | `python scripts/cli.py ingest --input src --output data/corpus` |
| `generate` | Generate text | `python scripts/cli.py generate --prompt "..." --max-tokens 250` |

## 🔧 Configuration

| Setting | Env Var | Default |
|---------|---------|---------|
| Model | `CHATGPME_MODEL` | TinyLlama/TinyLlama-1.1B-Chat-v1.0 |
| Adapter | `CHATGPME_ADAPTER` | artifacts/tinyllama-style-lora-mvp |
| Device | `CHATGPME_DEVICE` | auto |
| Host | `CHATGPME_HOST` | 127.0.0.1 |
| Port | `CHATGPME_PORT` | 8000 |
| Eval Model | `CHATGPME_EVAL_MODEL` | gpt-4o-mini |
| Log Level | `CHATGPME_LOG_LEVEL` | INFO |

## 📁 Project Structure

```
ChatGPMe/
├── scripts/           # Core Python modules
│   ├── cli.py         # Main CLI
│   ├── config.py      # Configuration
│   ├── run_app.py     # Web server
│   ├── grader*.py     # Evaluation system
│   └── ...
├── webapp/            # Web interface (HTML/CSS/JS)
├── data/              # Data (gitignored)
├── artifacts/         # Models (gitignored)
├── logs/              # Logs (gitignored)
├── setup.py           # Initialization script
├── README.md          # Full documentation
├── GRADER_README.md   # Evaluation docs
└── .env.example       # Config template
```

## 🧪 Testing

```bash
# Test grader
python test_grader.py

# Test web app
python scripts/cli.py serve

# Run all checks
python setup.py
python scripts/cli.py config
```

## 🔄 Full Pipeline Example

```bash
# 1. Ingest corpus from documents
python scripts/cli.py ingest --input data/raw/docs --output data/corpus

# 2. Build training dataset
python scripts/build_lora_dataset.py --input-dir data/corpus --output-dir data/processed

# 3. Create style training set
python scripts/build_style_train_dataset.py \
  --input-path data/processed/chunks.jsonl \
  --output-path data/style_train/style_train.jsonl

# 4. Train LoRA adapter
python scripts/train_lora.py \
  --model-name TinyLlama/TinyLlama-1.1B-Chat-v1.0 \
  --dataset-path data/style_train/style_train.jsonl \
  --output-dir artifacts/my-style

# 5. Update .env with new adapter path
# CHATGPME_ADAPTER=artifacts/my-style

# 6. Start web app
python scripts/cli.py serve

# 7. Generate outputs and evaluate
python scripts/cli.py eval \
  --author "Your Name" \
  --prompts eval_prompts.json \
  --baseline baseline_outputs.json \
  --candidate candidate_outputs.json \
  --output report.json
```

## 📊 Evaluation System

```bash
# Run demo with Shakespeare
python scripts/cli.py demo --model gpt-4o-mini

# Evaluate your outputs
python scripts/cli.py eval \
  --author "AuthorName" \
  --prompts prompts.json \
  --baseline baseline.json \
  --candidate candidate.json \
  --samples author_samples.json \
  --output report.json

# View report
cat report.json
```

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Model not loading | Check `python scripts/cli.py config`, verify adapter path |
| Port in use | Change `CHATGPME_PORT` or kill process: `lsof -i :8000 \| xargs kill` |
| Evaluation errors | Set `OPENAI_API_KEY` environment variable |
| Memory issues | Set `CHATGPME_DEVICE=cpu` (slower but lower memory) |
| Import errors | Run `python setup.py` to validate environment |

## 📖 Documentation

- **README.md** - Full project documentation
- **GRADER_README.md** - Evaluation system details
- **IMPROVEMENTS.md** - Recent improvements summary
- **scripts/cli.py** - Run with `--help` for command reference

## 🔑 Key Modules

```python
# Configuration
from config import config
config.model.name
config.validate()

# Grader
from grader import OutputGrader
grader = OutputGrader(author="X")
report = grader.evaluate(prompts, baselines, candidates)

# CLI
python scripts/cli.py <command> [options]
```

## 🌐 Web Interface Features

- **Editor Tab**: Type naturally, get continuation suggestions (Tab to accept)
- **Assistant Tab**: Draft, rewrite, or continue in your style
- **Status**: Current model and latency shown in real-time

## 🚢 Deployment

```bash
# Start on different host/port
CHATGPME_HOST=0.0.0.0 CHATGPME_PORT=9000 python scripts/cli.py serve

# Use remote generation server
CHATGPME_REMOTE_API=http://remote:9000 python scripts/cli.py serve

# Enable debug logging
CHATGPME_LOG_LEVEL=DEBUG python scripts/cli.py -v serve
```

## 💾 Data Paths

| Type | Path | Note |
|------|------|------|
| Raw documents | `data/raw/google_drive_docs/` | gitignored |
| Extracted text | `data/corpus/` | gitignored |
| Training data | `data/processed/`, `data/style_train/` | gitignored |
| Models | `artifacts/` | gitignored |
| Logs | `logs/` | gitignored |
| Eval results | `data/eval_demo/` | gitignored |
| Config | `.env` | gitignored |

## 🎯 Common Tasks

### Change the model
```bash
CHATGPME_MODEL=meta-llama/Llama-2-7b python scripts/cli.py serve
```

### Train new adapter
```bash
python scripts/train_lora.py \
  --model-name <model> \
  --dataset-path data/style_train/style_train.jsonl \
  --output-dir artifacts/<new-name>
```

### Evaluate on multiple genres
```bash
# Create prompts with genre field
# [{"text": "...", "genre": "reflective"}, ...]
python scripts/cli.py eval ... --output report.json
# Report will include per-genre breakdown
```

### View logs
```bash
# Real-time log
tail -f logs/chatgpme.log

# All logs with level
grep ERROR logs/chatgpme.log
```

---

**For full documentation, see README.md**  
**For evaluation docs, see GRADER_README.md**  
**For recent changes, see IMPROVEMENTS.md**
