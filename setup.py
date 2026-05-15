#!/usr/bin/env python3
"""Setup script to initialize ChatGPMe environment."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    """Run setup steps."""
    print("\n" + "=" * 70)
    print("ChatGPMe Setup")
    print("=" * 70)

    root = Path(__file__).resolve().parent

    # Step 1: Create directories
    print("\n1. Creating data directories...")
    directories = [
        root / "data" / "corpus",
        root / "data" / "raw" / "google_drive_docs",
        root / "data" / "processed",
        root / "data" / "style_train",
        root / "data" / "metadata",
        root / "data" / "eval_demo",
        root / "artifacts",
        root / "logs",
    ]

    for d in directories:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {d.relative_to(root)}/")

    # Step 2: Create .env if it doesn't exist
    print("\n2. Setting up configuration...")
    env_file = root / ".env"
    env_example = root / ".env.example"

    if not env_file.exists() and env_example.exists():
        env_file.write_text(env_example.read_text())
        print(f"  ✓ Created .env from .env.example")
        print(f"    ⚠️  Edit .env with your API keys and settings")
    else:
        print(f"  ✓ .env already exists")

    # Step 3: Verify virtual environment
    print("\n3. Checking virtual environment...")
    venv_python = root / ".venv" / "bin" / "python"
    if venv_python.exists():
        print(f"  ✓ Virtual environment found at .venv/")
        print(f"    Run: source .venv/bin/activate")
    else:
        print(f"  ⚠️  Virtual environment not found")
        print(f"    Create one with: python -m venv .venv")

    # Step 4: Test imports
    print("\n4. Testing core module imports...")
    try:
        # Try importing from scripts directory
        sys.path.insert(0, str(root / "scripts"))

        try:
            import grader_types
            print(f"  ✓ Grader module")
        except ImportError as e:
            print(f"  ✗ Grader module: {e}")

        try:
            import config
            print(f"  ✓ Config module")
        except ImportError as e:
            print(f"  ✗ Config module: {e}")

        try:
            import cli
            print(f"  ✓ CLI module")
        except ImportError as e:
            print(f"  ✗ CLI module: {e}")

    except Exception as e:
        print(f"  ✗ Error testing imports: {e}")

    # Step 5: Summary
    print("\n" + "=" * 70)
    print("Setup Complete!")
    print("=" * 70)
    print("\nNext Steps:")
    print("\n1. Activate virtual environment (if not already done):")
    print("   source .venv/bin/activate")
    print("\n2. Configure your settings:")
    print("   Edit .env with your API keys and preferences")
    print("\n3. Verify configuration:")
    print("   python scripts/cli.py config")
    print("\n4. Start the web app:")
    print("   python scripts/cli.py serve")
    print("\n5. Open http://127.0.0.1:8000 in your browser")
    print("\n6. For more commands:")
    print("   python scripts/cli.py --help")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
