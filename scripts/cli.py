#!/usr/bin/env python3
"""Main CLI interface for ChatGPMe pipeline."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from config import config


def setup_logging() -> None:
    """Configure logging for the system."""
    # Create logs directory
    config.data.logs_dir.mkdir(parents=True, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.logging.level),
        format=config.logging.format,
        handlers=[
            logging.FileHandler(config.logging.file_path),
            logging.StreamHandler(),
        ],
    )

    # Set up loggers for main modules
    logging.getLogger("chatgpme.grader").setLevel(logging.INFO)
    logging.getLogger("chatgpme.generation").setLevel(logging.INFO)
    logging.getLogger("chatgpme.webapp").setLevel(logging.INFO)


def cmd_config(args: argparse.Namespace) -> int:
    """Display or validate configuration."""
    logger = logging.getLogger("chatgpme.cli")

    config_dict = config.to_dict()
    print("\n" + "=" * 70)
    print("ChatGPMe Configuration")
    print("=" * 70)
    print(json.dumps(config_dict, indent=2))

    # Validate config
    errors = config.validate()
    if errors:
        print("\n⚠️  Configuration Issues:")
        for error in errors:
            print(f"  - {error}")
            logger.warning(error)
        return 1

    print("\n✅ Configuration is valid")
    return 0


def cmd_webapp(args: argparse.Namespace) -> int:
    """Start the web application server."""
    logger = logging.getLogger("chatgpme.webapp")
    logger.info(f"Starting ChatGPMe webapp on {config.server.host}:{config.server.port}")

    try:
        from run_app import main as webapp_main

        return webapp_main()
    except Exception as e:
        logger.error(f"Failed to start webapp: {e}")
        print(f"Error starting webapp: {e}", file=sys.stderr)
        return 1


def cmd_grader_demo(args: argparse.Namespace) -> int:
    """Run the grader demo with sample data."""
    logger = logging.getLogger("chatgpme.grader")

    try:
        from grader_demo import main as demo_main

        sys.argv = [sys.argv[0], "--model", args.model, "--output-dir", args.output]
        return demo_main()
    except Exception as e:
        logger.error(f"Grader demo failed: {e}")
        print(f"Error running grader demo: {e}", file=sys.stderr)
        return 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Run output evaluation."""
    logger = logging.getLogger("chatgpme.grader")

    try:
        from evaluate import main as eval_main

        # Reconstruct argv for evaluate.py
        sys_argv = [
            sys.argv[0],
            "--author",
            args.author,
            "--prompts",
            str(args.prompts),
            "--baseline",
            str(args.baseline),
            "--candidate",
            str(args.candidate),
            "--model",
            args.model,
        ]
        if args.samples:
            sys_argv.extend(["--samples", str(args.samples)])
        if args.output:
            sys_argv.extend(["--output", str(args.output)])
        if args.print_comparisons:
            sys_argv.append("--print-comparisons")

        sys.argv = sys_argv
        return eval_main()
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        print(f"Error running evaluation: {e}", file=sys.stderr)
        return 1


def cmd_ingest(args: argparse.Namespace) -> int:
    """Ingest and process a corpus."""
    logger = logging.getLogger("chatgpme.ingest")
    logger.info(f"Ingesting corpus from {args.input}")

    try:
        from extract_corpus import main as ingest_main

        sys.argv = [
            sys.argv[0],
            "--input-dir",
            str(args.input),
            "--output-dir",
            str(args.output),
            "--manifest",
            str(args.manifest),
        ]
        return ingest_main()
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        print(f"Error ingesting corpus: {e}", file=sys.stderr)
        return 1


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate text with the model."""
    logger = logging.getLogger("chatgpme.generation")

    try:
        from generate_with_adapter import main as gen_main

        sys.argv = [
            sys.argv[0],
            "--model-name",
            args.model,
            "--adapter-path",
            str(args.adapter),
            "--prompt",
            args.prompt,
            "--max-new-tokens",
            str(args.max_tokens),
            "--temperature",
            str(args.temperature),
            "--top-p",
            str(args.top_p),
        ]
        return gen_main()
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        print(f"Error generating text: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="chatgpme",
        description="ChatGPMe: Style-aware writing assistant and evaluation system.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Config command
    config_parser = subparsers.add_parser(
        "config",
        help="Show or validate configuration",
    )
    config_parser.set_defaults(func=cmd_config)

    # Webapp command
    webapp_parser = subparsers.add_parser(
        "serve",
        help="Start the web application server",
    )
    webapp_parser.set_defaults(func=cmd_webapp)

    # Grader demo command
    demo_parser = subparsers.add_parser(
        "demo",
        help="Run grader demo with sample Shakespeare data",
    )
    demo_parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="LLM model for evaluation (default: gpt-4o-mini)",
    )
    demo_parser.add_argument(
        "--output",
        default="data/eval_demo",
        help="Directory to save demo results (default: data/eval_demo)",
    )
    demo_parser.set_defaults(func=cmd_grader_demo)

    # Evaluate command
    eval_parser = subparsers.add_parser(
        "eval",
        help="Evaluate generated outputs against baselines",
    )
    eval_parser.add_argument("--author", required=True, help="Name of the author")
    eval_parser.add_argument(
        "--prompts",
        required=True,
        type=Path,
        help="JSON file with evaluation prompts",
    )
    eval_parser.add_argument(
        "--baseline",
        required=True,
        type=Path,
        help="JSON file with baseline outputs",
    )
    eval_parser.add_argument(
        "--candidate",
        required=True,
        type=Path,
        help="JSON file with candidate outputs",
    )
    eval_parser.add_argument(
        "--samples",
        type=Path,
        help="Optional JSON file with author samples",
    )
    eval_parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="LLM model for judging (default: gpt-4o-mini)",
    )
    eval_parser.add_argument(
        "--output",
        type=Path,
        help="Path to save report JSON",
    )
    eval_parser.add_argument(
        "--print-comparisons",
        action="store_true",
        help="Print detailed comparison results",
    )
    eval_parser.set_defaults(func=cmd_evaluate)

    # Ingest command
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Ingest and process a corpus",
    )
    ingest_parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Directory with source documents",
    )
    ingest_parser.add_argument(
        "--output",
        type=Path,
        default="data/corpus",
        help="Directory for extracted text (default: data/corpus)",
    )
    ingest_parser.add_argument(
        "--manifest",
        type=Path,
        default="data/metadata/extraction_manifest.json",
        help="Path for extraction manifest (default: data/metadata/extraction_manifest.json)",
    )
    ingest_parser.set_defaults(func=cmd_ingest)

    # Generate command
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate text with the model",
    )
    gen_parser.add_argument("--model", default=config.model.name, help="Model name")
    gen_parser.add_argument(
        "--adapter",
        type=Path,
        default=config.model.adapter_path or "artifacts/tinyllama-style-lora-mvp",
        help="Path to LoRA adapter",
    )
    gen_parser.add_argument("--prompt", required=True, help="Prompt text")
    gen_parser.add_argument(
        "--max-tokens",
        type=int,
        default=250,
        help="Maximum tokens to generate (default: 250)",
    )
    gen_parser.add_argument(
        "--temperature",
        type=float,
        default=0.8,
        help="Sampling temperature (default: 0.8)",
    )
    gen_parser.add_argument(
        "--top-p",
        type=float,
        default=0.95,
        help="Top-p sampling (default: 0.95)",
    )
    gen_parser.set_defaults(func=cmd_generate)

    # Parse arguments
    args = parser.parse_args()

    # Set up logging
    if args.verbose:
        config.logging.level = "DEBUG"
    setup_logging()

    logger = logging.getLogger("chatgpme.cli")
    logger.info("ChatGPMe CLI started")

    # Show config if verbose
    if args.verbose:
        logger.debug(json.dumps(config.to_dict(), indent=2))

    # Run command
    if not args.command:
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except Exception as e:
        logger.exception(f"Command {args.command} failed: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
