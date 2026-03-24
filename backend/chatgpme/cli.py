from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .generation import DraftGenerator
from .pipeline import IngestionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ChatGPMe MVP ingestion CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Ingest local files for a user")
    ingest.add_argument("--user-id", required=True)
    ingest.add_argument("--source-type", default="local_files")
    ingest.add_argument("--source-dir")
    ingest.add_argument(
        "--source-config-json",
        help="JSON string merged into source_config (useful for google_drive)",
    )

    generate = subparsers.add_parser("generate", help="Generate baseline or personalized draft")
    generate.add_argument("--user-id", required=True)
    generate.add_argument("--prompt", required=True)
    generate.add_argument("--mode", default="baseline", choices=["baseline", "personalized"])
    generate.add_argument("--top-k", type=int, default=3)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        pipeline = IngestionPipeline()
        source_config = {}
        if args.source_config_json:
            source_config.update(json.loads(args.source_config_json))
        if args.source_dir:
            source_config["source_dir"] = args.source_dir

        summary = pipeline.ingest(
            user_id=args.user_id,
            source_type=args.source_type,
            source_config=source_config,
        )
        print(json.dumps(asdict(summary), indent=2))
    elif args.command == "generate":
        generator = DraftGenerator()
        draft = generator.generate_in_user_style(
            user_id=args.user_id,
            prompt=args.prompt,
            mode=args.mode,
            top_k=args.top_k,
        )
        print(json.dumps(asdict(draft), indent=2))


if __name__ == "__main__":
    main()
