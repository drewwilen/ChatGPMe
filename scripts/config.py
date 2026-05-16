#!/usr/bin/env python3
"""Centralized configuration for ChatGPMe system."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ModelConfig:
    """Configuration for the language model."""

    name: str = os.environ.get("CHATGPME_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
    adapter_path: str | None = os.environ.get(
        "CHATGPME_ADAPTER",
        None,
    )
    device: str = "cuda" if os.environ.get("CHATGPME_DEVICE") != "cpu" else "cpu"


@dataclass
class GenerationConfig:
    """Default parameters for text generation."""

    max_new_tokens: int = 80
    temperature: float = 0.7
    top_p: float = 0.95
    editor_max_tokens: int = 20
    editor_temperature: float = 0.45
    assistant_max_tokens: int = 180
    assistant_temperature: float = 0.7


@dataclass
class ServerConfig:
    """Configuration for the web server."""

    host: str = os.environ.get("CHATGPME_HOST", "127.0.0.1")
    port: int = int(os.environ.get("CHATGPME_PORT", "8000"))
    remote_api: str = os.environ.get("CHATGPME_REMOTE_API", "").rstrip("/")
    debug: bool = os.environ.get("CHATGPME_DEBUG", "").lower() in ("1", "true", "yes")


@dataclass
class EvalConfig:
    """Configuration for evaluation."""

    judge_model: str = os.environ.get("CHATGPME_EVAL_MODEL", "gpt-4o-mini")
    openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")


@dataclass
class DataConfig:
    """Configuration for data paths."""

    root_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = None  # Set after root_dir
    corpus_dir: Path = None
    artifacts_dir: Path = None
    logs_dir: Path = None

    def __post_init__(self) -> None:
        """Initialize derived paths."""
        if self.data_dir is None:
            self.data_dir = self.root_dir / "data"
        if self.corpus_dir is None:
            self.corpus_dir = self.data_dir / "corpuses"
        if self.artifacts_dir is None:
            self.artifacts_dir = self.root_dir / "artifacts"
        if self.logs_dir is None:
            self.logs_dir = self.root_dir / "logs"


@dataclass
class LoggingConfig:
    """Configuration for logging."""

    level: str = os.environ.get("CHATGPME_LOG_LEVEL", "INFO")
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Path | None = None  # Set by data config

    def setup_file_path(self, data_config: DataConfig) -> None:
        """Set up the log file path."""
        if self.file_path is None:
            data_config.logs_dir.mkdir(parents=True, exist_ok=True)
            self.file_path = data_config.logs_dir / "chatgpme.log"


class ChatGPMeConfig:
    """Main configuration container."""

    def __init__(self) -> None:
        """Initialize all configuration sections."""
        self.model = ModelConfig()
        self.generation = GenerationConfig()
        self.server = ServerConfig()
        self.eval = EvalConfig()
        self.data = DataConfig()
        self.logging = LoggingConfig()
        self.logging.setup_file_path(self.data)

    def validate(self) -> list[str]:
        """Validate configuration and return any error messages."""
        errors = []

        if self.model.name and "/" not in self.model.name:
            errors.append(
                f"Model name should be in format 'owner/model' (got: {self.model.name})"
            )

        if self.model.adapter_path and not Path(self.model.adapter_path).exists():
            # Warn but don't error - adapter can be lazy-loaded
            pass

        if self.server.port < 1 or self.server.port > 65535:
            errors.append(f"Invalid port number: {self.server.port}")

        if self.logging.level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            errors.append(f"Invalid log level: {self.logging.level}")

        return errors

    def to_dict(self) -> dict[str, dict]:
        """Convert config to dictionary (for logging/display)."""
        return {
            "model": {
                "name": self.model.name,
                "adapter_path": self.model.adapter_path,
                "device": self.model.device,
            },
            "server": {
                "host": self.server.host,
                "port": self.server.port,
                "remote_api": self.server.remote_api if self.server.remote_api else "(none)",
                "debug": self.server.debug,
            },
            "eval": {
                "judge_model": self.eval.judge_model,
                "openai_available": bool(self.eval.openai_api_key),
                "anthropic_available": bool(self.eval.anthropic_api_key),
            },
            "data": {
                "root_dir": str(self.data.root_dir),
                "logs_dir": str(self.data.logs_dir),
            },
            "logging": {
                "level": self.logging.level,
                "file": str(self.logging.file_path),
            },
        }


# Global configuration instance
config = ChatGPMeConfig()
