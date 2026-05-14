#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the style adapter as a small HTTP inference API.")
    parser.add_argument("--model-name", required=True, help="Base Hugging Face model name or path.")
    parser.add_argument("--adapter-path", required=True, help="Path to the adapter directory.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host.")
    parser.add_argument("--port", type=int, default=8001, help="Bind port.")
    return parser.parse_args()


def build_prompt(text: str, mode: str) -> str:
    normalized = text.rstrip()
    if mode == "editor_continue":
        return normalized
    if mode == "assistant_continue":
        return normalized
    if mode == "assistant_rewrite":
        return (
            "Rewrite the following in the same writing voice, preserving the meaning while improving clarity.\n\n"
            f"{normalized}\n\nRewritten version:"
        )
    if mode == "assistant_draft":
        return (
            "Draft the following request in the same writing voice and level of formality.\n\n"
            f"{normalized}\n\nDraft:"
        )
    return normalized


class InferenceEngine:
    def __init__(self, model_name: str, adapter_path: str) -> None:
        self.model_name = model_name
        self.adapter_path = adapter_path
        self._loaded = False
        self._error: str | None = None
        self._tokenizer = None
        self._model = None
        self._torch = None

    def _load(self) -> None:
        if self._loaded or self._error:
            return
        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            self._error = str(exc)
            raise

        self._torch = torch
        tokenizer = AutoTokenizer.from_pretrained(self.model_name, use_fast=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        base_model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )
        adapter_dir = Path(self.adapter_path)
        if not adapter_dir.exists():
            self._error = f"Adapter path does not exist: {self.adapter_path}"
            raise RuntimeError(self._error)

        model = PeftModel.from_pretrained(base_model, str(adapter_dir))
        model.eval()
        self._tokenizer = tokenizer
        self._model = model
        self._loaded = True

    def status(self) -> dict[str, Any]:
        return {
            "ready": self._loaded and self._error is None,
            "loaded": self._loaded,
            "model_name": self.model_name,
            "adapter_path": self.adapter_path,
            "adapter_exists": Path(self.adapter_path).exists(),
            "error": self._error,
        }

    def generate(self, text: str, mode: str, max_new_tokens: int, temperature: float, top_p: float) -> dict[str, Any]:
        self._load()
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._torch is not None

        prompt = build_prompt(text, mode)
        started = time.time()
        encoded = self._tokenizer(prompt, return_tensors="pt")
        if self._torch.cuda.is_available():
            encoded = {key: value.cuda() for key, value in encoded.items()}
            self._model = self._model.cuda()

        output = self._model.generate(
            **encoded,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=temperature > 0,
            pad_token_id=self._tokenizer.eos_token_id,
        )
        full_text = self._tokenizer.decode(output[0], skip_special_tokens=True)
        completion = full_text[len(prompt) :] if full_text.startswith(prompt) else full_text
        latency_ms = int((time.time() - started) * 1000)
        return {"completion": completion, "latency_ms": latency_ms, "truncated": False}


ENGINE: InferenceEngine | None = None


class Handler(BaseHTTPRequestHandler):
    server_version = "ChatGPMeRemote/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            assert ENGINE is not None
            self._json(HTTPStatus.OK, {"status": "ok", "backend": ENGINE.status()})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/generate":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
            text = str(payload.get("text", ""))
            mode = str(payload.get("mode", "editor_continue"))
            max_new_tokens = int(payload.get("max_new_tokens", 80))
            temperature = float(payload.get("temperature", 0.7))
            top_p = float(payload.get("top_p", 0.95))
            assert ENGINE is not None
            result = ENGINE.generate(text, mode, max_new_tokens, temperature, top_p)
            self._json(HTTPStatus.OK, result)
        except Exception as exc:  # pragma: no cover - runtime dependent
            backend = ENGINE.status() if ENGINE else {}
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc), "backend": backend})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> int:
    global ENGINE
    args = parse_args()
    ENGINE = InferenceEngine(args.model_name, args.adapter_path)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Remote inference server running on {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
