#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {".docx", ".doc", ".txt", ".md"}


@dataclass
class ExtractionResult:
    source_path: str
    output_path: str
    title: str
    word_count: int
    char_count: int
    status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract plain-text corpus files from exported Google Drive documents."
    )
    parser.add_argument(
        "--input-dir",
        default="data/raw/google_drive_docs",
        help="Directory containing exported Google Drive files.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/corpus",
        help="Directory where extracted plain-text files will be written.",
    )
    parser.add_argument(
        "--manifest",
        default="data/metadata/extraction_manifest.json",
        help="Path to write a JSON manifest summarizing extracted files.",
    )
    return parser.parse_args()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_only).strip("_").lower()
    return slug or "document"


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        if line:
            cleaned.append(line)
            blank_run = 0
            continue
        if blank_run == 0:
            cleaned.append("")
        blank_run += 1
    normalized = "\n".join(cleaned).strip()
    return normalized + "\n" if normalized else ""


def allocate_output_stem(base_name: str, used_names: set[str]) -> str:
    candidate = base_name
    suffix = 1
    while candidate in used_names:
        candidate = f"{base_name}_{suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix in {".docx", ".doc"}:
        completed = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", str(path)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return completed.stdout.decode("utf-8", errors="ignore")
    raise ValueError(f"Unsupported file type: {path.suffix}")


def write_manifest(path: Path, results: list[ExtractionResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total_files": len(results),
        "written_files": sum(1 for item in results if item.status == "written"),
        "skipped_files": sum(1 for item in results if item.status == "skipped_empty"),
        "total_words": sum(item.word_count for item in results if item.status == "written"),
        "files": [asdict(item) for item in results],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    manifest_path = Path(args.manifest)

    if not input_dir.exists():
        print(f"Input directory does not exist: {input_dir}", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[ExtractionResult] = []
    used_names: set[str] = set()
    failed_files = 0

    files = sorted(
        path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    for path in files:
        title = path.stem
        try:
            raw_text = extract_text(path)
        except subprocess.CalledProcessError as exc:
            print(f"Failed to extract {path}: {exc}", file=sys.stderr)
            failed_files += 1
            continue
        except subprocess.TimeoutExpired:
            print(f"Timed out extracting {path}", file=sys.stderr)
            failed_files += 1
            continue

        cleaned_text = normalize_text(raw_text)
        words = cleaned_text.split()
        status = "written"

        base_name = slugify(path.relative_to(input_dir).with_suffix("").as_posix())
        unique_name = allocate_output_stem(base_name, used_names)
        output_path = output_dir / f"{unique_name}.txt"

        if len(words) == 0:
            status = "skipped_empty"
        else:
            output_path.write_text(cleaned_text, encoding="utf-8")

        results.append(
            ExtractionResult(
                source_path=str(path),
                output_path=str(output_path),
                title=title,
                word_count=len(words),
                char_count=len(cleaned_text),
                status=status,
            )
        )

    write_manifest(manifest_path, results)

    written = sum(1 for item in results if item.status == "written")
    skipped = sum(1 for item in results if item.status == "skipped_empty")
    total_words = sum(item.word_count for item in results if item.status == "written")
    print(f"Processed {len(results)} files")
    print(f"Wrote {written} corpus files")
    print(f"Skipped {skipped} empty files")
    print(f"Failed {failed_files} files")
    print(f"Total words written: {total_words}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
