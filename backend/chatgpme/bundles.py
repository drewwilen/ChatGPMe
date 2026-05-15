from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .storage import CorpusStore


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "user"


def _adapter_name(bundle_name: str) -> str:
    suffix = bundle_name.removeprefix("colab_upload_")
    if suffix == bundle_name:
        return "tinyllama-style-lora-colab"
    return f"tinyllama-style-lora-colab-{suffix}"


@dataclass(slots=True)
class BundleResult:
    user_id: str
    bundle_name: str
    bundle_path: str
    dataset_rows: int
    adapter_dir_name: str


class ColabBundleBuilder:
    def __init__(self, store: CorpusStore | None = None) -> None:
        self.store = store or CorpusStore()
        self.repo_root = Path(__file__).resolve().parents[2]

    def build_for_user(self, user_id: str, bundle_name: str | None = None) -> BundleResult:
        state = self.store.get_user_state(user_id)
        style_train_path = Path(str(state["style_train_path"]))
        if not style_train_path.exists():
            raise ValueError(f"No style_train.jsonl found for user '{user_id}'. Ingest corpus data first.")

        resolved_bundle_name = bundle_name or f"colab_upload_{_slugify(user_id)}"
        adapter_dir_name = _adapter_name(resolved_bundle_name)
        user_dir = style_train_path.parent
        bundles_dir = user_dir / "bundles"
        bundle_dir = bundles_dir / resolved_bundle_name
        zip_path = bundles_dir / f"{resolved_bundle_name}.zip"

        bundles_dir.mkdir(parents=True, exist_ok=True)
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        bundle_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(style_train_path, bundle_dir / "style_train.jsonl")
        shutil.copy2(self.repo_root / "scripts" / "train_lora.py", bundle_dir / "train_lora.py")
        shutil.copy2(
            self.repo_root / "scripts" / "generate_with_adapter.py",
            bundle_dir / "generate_with_adapter.py",
        )
        shutil.copy2(
            self.repo_root / "scripts" / "remote_inference_server.py",
            bundle_dir / "remote_inference_server.py",
        )
        shutil.copy2(self.repo_root / "requirements.txt", bundle_dir / "requirements.txt")

        self._write_readme(bundle_dir / "README.md", user_id, resolved_bundle_name)
        self._write_runner_notebook(
            bundle_dir / "chatgpme_colab_upload_runner.ipynb",
            resolved_bundle_name,
            adapter_dir_name,
        )

        if zip_path.exists():
            zip_path.unlink()
        self._zip_directory(bundle_dir, zip_path)

        return BundleResult(
            user_id=user_id,
            bundle_name=resolved_bundle_name,
            bundle_path=str(zip_path),
            dataset_rows=int(state["style_train_rows"]),
            adapter_dir_name=adapter_dir_name,
        )

    def _write_readme(self, path: Path, user_id: str, bundle_name: str) -> None:
        path.write_text(
            "\n".join(
                [
                    f"# {bundle_name}",
                    "",
                    "Colab-ready LoRA training bundle generated from your ChatGPMe corpus.",
                    "",
                    f"- User: `{user_id}`",
                    "- Dataset file: `style_train.jsonl`",
                    "- Run the included `chatgpme_colab_upload_runner.ipynb` in Colab.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _write_runner_notebook(self, output_path: Path, bundle_name: str, adapter_dir_name: str) -> None:
        template_candidates = [
            self.repo_root / "chatgpme_colab_upload_runner.ipynb",
            self.repo_root / "notebooks" / "chatgpme_colab_upload_runner.ipynb",
            self.repo_root / "colab_upload" / "chatgpme_colab_upload_runner.ipynb",
        ]
        template_path = next((path for path in template_candidates if path.exists()), None)
        if template_path is None:
            raise ValueError("Could not find a Colab notebook template.")

        notebook = json.loads(template_path.read_text(encoding="utf-8"))
        bundle_zip = f"{bundle_name}.zip"
        bundle_dir = f"/content/{bundle_name}"
        adapter_dir = f"/content/{adapter_dir_name}"

        def set_cell(index: int, text: str) -> None:
            notebook["cells"][index]["source"] = text.splitlines(keepends=True)

        set_cell(
            0,
            f"# ChatGPMe Colab Upload Runner\n\n"
            f"This notebook uses the minimal `{bundle_zip}` package for paper-aligned style training.\n\n"
            "Expected files after unzip:\n"
            "- `style_train.jsonl`\n"
            "- `train_lora.py`\n"
            "- `generate_with_adapter.py`\n"
            "- `remote_inference_server.py`\n"
            "- `requirements.txt`\n",
        )
        set_cell(
            6,
            f"## 2. Upload and unzip `{bundle_zip}`\n\n"
            "If you already uploaded and unzipped it manually, skip the upload cell.\n",
        )
        set_cell(
            8,
            f"%cd /content\n"
            f"!rm -rf {bundle_dir} {adapter_dir} {adapter_dir}.zip\n"
            f"!unzip -o /content/{bundle_zip} -d /content\n"
            f"%cd {bundle_dir}\n"
            "!ls -la\n",
        )
        set_cell(
            10,
            "!ls -lh\n"
            "!wc -l style_train.jsonl\n"
            '!grep -n "learning-rate\\|max-length\\|build_prompt_prefix\\|instruction" train_lora.py || true\n',
        )
        set_cell(
            11,
            f"%cd /content\n"
            f"!rm -rf {bundle_dir}\n"
            f"!unzip -o /content/{bundle_zip} -d /content\n"
            f"!grep -n \"torch_dtype\\|dtype=\" {bundle_dir}/train_lora.py\n",
        )
        set_cell(
            13,
            f"!python {bundle_dir}/train_lora.py \\\n"
            "    --model-name TinyLlama/TinyLlama-1.1B-Chat-v1.0 \\\n"
            f"    --dataset-path {bundle_dir}/style_train.jsonl \\\n"
            f"    --output-dir {adapter_dir} \\\n"
            "    --epochs 3 \\\n"
            "    --batch-size 2 \\\n"
            "    --grad-accum 2 \\\n"
            "    --max-length 256 \\\n"
            "    --learning-rate 5e-5 \\\n"
            "    --save-steps 50\n",
        )
        set_cell(
            15,
            f"%cd /content\n"
            f"!rm -rf {bundle_dir}\n"
            f"!unzip -o /content/{bundle_zip} -d /content\n"
            f"!grep -n \"torch_dtype\\|dtype=\" {bundle_dir}/generate_with_adapter.py\n",
        )
        set_cell(
            16,
            f"!python {bundle_dir}/generate_with_adapter.py \\\n"
            "    --model-name TinyLlama/TinyLlama-1.1B-Chat-v1.0 \\\n"
            f"    --adapter-path {adapter_dir} \\\n"
            '    --prompt "My name is " \\\n'
            "    --max-new-tokens 120\n",
        )
        set_cell(
            17,
            f"!python {bundle_dir}/generate_with_adapter.py \\\n"
            "  --model-name TinyLlama/TinyLlama-1.1B-Chat-v1.0 \\\n"
            f"  --adapter-path {adapter_dir} \\\n"
            '  --prompt "When I sat down to write this application, I realized that the hardest part was not describing what I had done," \\\n'
            "  --max-new-tokens 120\n",
        )
        set_cell(19, f"!find {adapter_dir_name} -maxdepth 2 -type f | sort\n")
        set_cell(
            23,
            f"%cd {bundle_dir}\n"
            "!nohup python -u remote_inference_server.py \\\n"
            "  --model-name TinyLlama/TinyLlama-1.1B-Chat-v1.0 \\\n"
            f"  --adapter-path {adapter_dir} \\\n"
            f"  --port 8001 > {bundle_dir}/server.log 2>&1 &\n"
            "!sleep 5\n"
            f"!cat {bundle_dir}/server.log\n",
        )
        set_cell(24, "!curl http://127.0.0.1:8001/api/health\n")
        set_cell(
            25,
            "!curl http://127.0.0.1:8001/api/generate \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            "    -d '{\"text\":\"When I sat down to write this application, I realized that the hardest part was not describing what I had done,\",\"mode\":\"editor_continue\",\"max_new_tokens\":80,\"temperature\":0.8,\"top_p\":0.95}'\n",
        )
        set_cell(30, f"!zip -r {adapter_dir_name}.zip {adapter_dir_name}\n")
        set_cell(
            31,
            "from google.colab import files\n"
            f"files.download('{adapter_dir_name}.zip')\n",
        )

        output_path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def _zip_directory(self, source_dir: Path, zip_path: Path) -> None:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source_dir.rglob("*")):
                if "__pycache__" in path.parts or path.name == ".DS_Store" or path.suffix == ".zip":
                    continue
                archive.write(path, arcname=path.relative_to(source_dir.parent))
