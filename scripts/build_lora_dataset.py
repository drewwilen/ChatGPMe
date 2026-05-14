#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ChunkRecord:
    chunk_id: str
    document_id: str
    title: str
    source_path: str
    text: str
    word_count: int
    tags: list[str]


@dataclass
class TrainExample:
    instruction: str
    input: str
    output: str
    source_chunk_id: str
    source_path: str
    tags: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build chunked corpus and LoRA-style training examples from extracted text files."
    )
    parser.add_argument("--input-dir", default="data/corpus", help="Directory with extracted .txt corpus files.")
    parser.add_argument("--output-dir", default="data/processed", help="Directory for chunks and training JSONL.")
    parser.add_argument(
        "--min-words",
        type=int,
        default=80,
        help="Skip documents and chunks shorter than this many words.",
    )
    parser.add_argument(
        "--target-chunk-words",
        type=int,
        default=350,
        help="Approximate chunk size in words.",
    )
    parser.add_argument(
        "--max-chunk-words",
        type=int,
        default=500,
        help="Hard upper bound for chunk size in words.",
    )
    return parser.parse_args()


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if len(stripped) <= 2:
            continue
        if re.fullmatch(r"[\W_]+", stripped):
            continue
        lines.append(stripped)
    text = "\n".join(lines).strip()
    return text


def infer_tags(source_path: str, text: str) -> list[str]:
    haystack = f"{source_path.lower()} {text[:1500].lower()}"
    tags: list[str] = []
    for keyword, tag in (
        ("essay", "essay_like"),
        ("speech", "speech_like"),
        ("cover letter", "professional"),
        ("application", "professional"),
        ("email", "email_like"),
        ("notes", "notes_like"),
        ("homework", "academic"),
        ("project", "project_like"),
        ("reflection", "reflective"),
    ):
        if keyword in haystack:
            tags.append(tag)
    if not tags:
        tags.append("general")
    return sorted(set(tags))


def split_paragraphs(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return parts


def paragraph_word_count(paragraph: str) -> int:
    return len(paragraph.split())


def build_chunks(text: str, target_words: int, max_words: int) -> list[str]:
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for paragraph in paragraphs:
        words = paragraph_word_count(paragraph)
        if words == 0:
            continue

        if words > max_words:
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            sentence_buffer: list[str] = []
            sentence_words = 0
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                count = len(sentence.split())
                if sentence_buffer and sentence_words + count > max_words:
                    chunks.append(" ".join(sentence_buffer).strip())
                    sentence_buffer = [sentence]
                    sentence_words = count
                else:
                    sentence_buffer.append(sentence)
                    sentence_words += count
            if sentence_buffer:
                chunks.append(" ".join(sentence_buffer).strip())
            continue

        if current and current_words + words > target_words:
            chunks.append("\n\n".join(current).strip())
            current = [paragraph]
            current_words = words
        else:
            current.append(paragraph)
            current_words += words

    if current:
        chunks.append("\n\n".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def build_examples(chunk: ChunkRecord) -> list[TrainExample]:
    words = chunk.text.split()
    if len(words) < 140:
        return []

    split_index = max(80, int(len(words) * 0.6))
    split_index = min(split_index, len(words) - 40)
    prompt_text = " ".join(words[:split_index]).strip()
    continuation_text = " ".join(words[split_index:]).strip()
    if not prompt_text or not continuation_text:
        return []

    return [
        TrainExample(
            instruction="Continue the passage in the same voice, tone, and structure as the user's writing.",
            input=prompt_text,
            output=continuation_text,
            source_chunk_id=chunk.chunk_id,
            source_path=chunk.source_path,
            tags=chunk.tags,
        )
    ]


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = output_dir / "chunks.jsonl"
    train_path = output_dir / "train.jsonl"
    summary_path = output_dir / "summary.json"

    chunk_records: list[ChunkRecord] = []
    train_examples: list[TrainExample] = []
    skipped_documents = 0

    for path in sorted(input_dir.glob("*.txt")):
        text = clean_text(path.read_text(encoding="utf-8", errors="ignore"))
        word_count = len(text.split())
        if word_count < args.min_words:
            skipped_documents += 1
            continue

        title = path.stem
        tags = infer_tags(path.name, text)
        chunks = build_chunks(text, args.target_chunk_words, args.max_chunk_words)
        valid_chunks = [chunk for chunk in chunks if len(chunk.split()) >= args.min_words]
        for index, chunk_text in enumerate(valid_chunks, start=1):
            chunk = ChunkRecord(
                chunk_id=f"{path.stem}:{index}",
                document_id=path.stem,
                title=title,
                source_path=str(path),
                text=chunk_text,
                word_count=len(chunk_text.split()),
                tags=tags,
            )
            chunk_records.append(chunk)
            train_examples.extend(build_examples(chunk))

    with chunks_path.open("w", encoding="utf-8") as handle:
        for record in chunk_records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    with train_path.open("w", encoding="utf-8") as handle:
        for example in train_examples:
            handle.write(json.dumps(asdict(example), ensure_ascii=False) + "\n")

    summary = {
        "documents_processed": len(list(input_dir.glob("*.txt"))),
        "documents_skipped": skipped_documents,
        "chunks_written": len(chunk_records),
        "train_examples_written": len(train_examples),
        "average_chunk_words": round(
            sum(chunk.word_count for chunk in chunk_records) / len(chunk_records), 2
        )
        if chunk_records
        else 0,
        "tag_counts": {},
    }
    tag_counts: dict[str, int] = {}
    for chunk in chunk_records:
        for tag in chunk.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    summary["tag_counts"] = dict(sorted(tag_counts.items()))
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Processed documents: {summary['documents_processed']}")
    print(f"Skipped short documents: {summary['documents_skipped']}")
    print(f"Chunks written: {summary['chunks_written']}")
    print(f"Train examples written: {summary['train_examples_written']}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
