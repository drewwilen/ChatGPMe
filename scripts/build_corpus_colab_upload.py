#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import zipfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a Colab-ready LoRA training bundle from a cleaned text corpus directory."
    )
    parser.add_argument("--input-dir", required=True, help="Directory containing cleaned .txt corpus files.")
    parser.add_argument("--bundle-name", required=True, help="Top-level folder name inside the zip archive.")
    parser.add_argument("--output-dir", required=True, help="Directory where the bundle folder and zip are written.")
    parser.add_argument("--dataset-filename", default="style_train.jsonl", help="Dataset file name in the bundle.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of raw text training rows to write. 0 means no cap.")
    return parser.parse_args()


def run_command(args: list[str]) -> None:
    subprocess.run(args, check=True)


def count_jsonl_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def adapter_dir_name(bundle_name: str) -> str:
    if bundle_name == "colab_upload":
        return "tinyllama-style-lora-colab"
    suffix = bundle_name.removeprefix("colab_upload_")
    return f"tinyllama-style-lora-colab-{suffix}"


def write_bundle_readme(
    path: Path,
    bundle_name: str,
    input_dir: Path,
    dataset_filename: str,
    dataset_rows: int,
) -> None:
    summary = {
        "bundle_name": bundle_name,
        "source_input_dir": str(input_dir),
        "dataset_filename": dataset_filename,
        "dataset_rows": dataset_rows,
    }
    text = (
        f"# {bundle_name}\n\n"
        "Colab-ready LoRA training bundle.\n\n"
        f"- Source corpus: `{input_dir}`\n"
        f"- Dataset file: `{dataset_filename}`\n"
        f"- Dataset rows: {dataset_rows}\n"
        "- No row cap is applied unless `--limit` is set.\n\n"
        "Train in Colab from `/content/<bundle-name>/train_lora.py` after unzipping into `/content`.\n\n"
        "```json\n"
        f"{json.dumps(summary, indent=2)}\n"
        "```\n"
    )
    path.write_text(text, encoding="utf-8")


def customize_runner_notebook(
    template_path: Path,
    output_path: Path,
    bundle_name: str,
    dataset_filename: str,
) -> None:
    nb = json.loads(template_path.read_text(encoding="utf-8"))
    bundle_zip = f"{bundle_name}.zip"
    bundle_dir = f"/content/{bundle_name}"
    adapter_name = adapter_dir_name(bundle_name)
    adapter_dir = f"/content/{adapter_name}"

    def set_cell(index: int, text: str) -> None:
        nb["cells"][index]["source"] = text.splitlines(keepends=True)

    set_cell(
        0,
        f"# ChatGPMe Colab Upload Runner\n\n"
        f"This notebook uses the minimal `{bundle_zip}` package for paper-aligned style training.\n\n"
        "Expected files after unzip:\n"
        f"- `{dataset_filename}`\n"
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
        f"!wc -l {dataset_filename}\n"
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
        f"    --dataset-path {bundle_dir}/{dataset_filename} \\\n"
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
    set_cell(19, f"!find {adapter_name} -maxdepth 2 -type f | sort\n")
    set_cell(
        23,
        f"%cd {bundle_dir}\n"
        "!nohup python -u remote_inference_server.py \\\n"
        "  --model-name TinyLlama/TinyLlama-1.1B-Chat-v1.0 \\\n"
        f"  --adapter-path {adapter_dir} \\\n"
        "  --port 8001 > "
        f"{bundle_dir}/server.log 2>&1 &\n"
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
    set_cell(30, f"!zip -r {adapter_name}.zip {adapter_name}\n")
    set_cell(
        31,
        "from google.colab import files\n"
        f"files.download('{adapter_name}.zip')\n",
    )

    output_path.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if "__pycache__" in path.parts or path.name == ".DS_Store" or path.suffix == ".zip":
                continue
            archive.write(path, arcname=path.relative_to(source_dir.parent))


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    bundle_dir = output_dir / args.bundle_name
    build_dir = output_dir / f"{args.bundle_name}_build"
    zip_path = output_dir / f"{args.bundle_name}.zip"

    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    run_command(
        [
            "python3",
            str(repo_root / "scripts" / "build_lora_dataset.py"),
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(build_dir),
        ]
    )

    dataset_path = bundle_dir / args.dataset_filename
    run_command(
        [
            "python3",
            str(repo_root / "scripts" / "build_style_train_dataset.py"),
            "--input-path",
            str(build_dir / "chunks.jsonl"),
            "--output-path",
            str(dataset_path),
            "--limit",
            str(args.limit),
        ]
    )

    shutil.copy2(repo_root / "scripts" / "train_lora.py", bundle_dir / "train_lora.py")
    shutil.copy2(repo_root / "scripts" / "generate_with_adapter.py", bundle_dir / "generate_with_adapter.py")
    shutil.copy2(repo_root / "scripts" / "remote_inference_server.py", bundle_dir / "remote_inference_server.py")
    shutil.copy2(repo_root / "requirements.txt", bundle_dir / "requirements.txt")

    template_path = repo_root / "chatgpme_colab_upload_runner.ipynb"
    if not template_path.exists():
        template_path = repo_root / "colab_upload" / "chatgpme_colab_upload_runner.ipynb"
    customize_runner_notebook(
        template_path=template_path,
        output_path=bundle_dir / "chatgpme_colab_upload_runner.ipynb",
        bundle_name=args.bundle_name,
        dataset_filename=args.dataset_filename,
    )

    dataset_rows = count_jsonl_rows(dataset_path)
    write_bundle_readme(
        bundle_dir / "README.md",
        bundle_name=args.bundle_name,
        input_dir=input_dir,
        dataset_filename=args.dataset_filename,
        dataset_rows=dataset_rows,
    )

    if zip_path.exists():
        zip_path.unlink()
    zip_directory(bundle_dir, zip_path)
    shutil.rmtree(build_dir)

    print(f"Built bundle: {bundle_dir}")
    print(f"Built zip: {zip_path}")
    print(f"Dataset rows: {dataset_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
