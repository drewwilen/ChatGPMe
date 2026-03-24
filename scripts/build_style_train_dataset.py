#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a raw-text style training dataset from chunked corpus JSONL.")
    parser.add_argument("--input-path", default="data/processed/chunks.jsonl", help="Input chunk JSONL path.")
    parser.add_argument("--output-path", required=True, help="Output JSONL path with only `text` rows.")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum number of rows to write.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path)
    output_path = Path(args.output_path)
    if not input_path.exists():
        raise SystemExit(f"Input path does not exist: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            text = (obj.get("text") or "").strip()
            if not text:
                continue
            dst.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
            written += 1
            if args.limit and written >= args.limit:
                break

    print(f"Wrote {written} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
