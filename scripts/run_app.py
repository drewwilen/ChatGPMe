#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import request
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "webapp"
DEFAULT_MODEL = os.environ.get("CHATGPME_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
DEFAULT_ADAPTER = os.environ.get(
    "CHATGPME_ADAPTER", str(ROOT / "artifacts" / "tinyllama-style-lora-mvp")
)
REMOTE_API = os.environ.get("CHATGPME_REMOTE_API", "").rstrip("/")
DEFAULT_HOST = os.environ.get("CHATGPME_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("CHATGPME_PORT", "8000"))


class RemoteGenerationBackend:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def status(self) -> dict[str, Any]:
        try:
            with request.urlopen(f"{self.base_url}/api/health", timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            backend = payload.get("backend", {})
            backend["remote_url"] = self.base_url
            return backend
        except Exception as exc:  # pragma: no cover - runtime dependent
            return {
                "ready": False,
                "loaded": False,
                "remote_url": self.base_url,
                "error": str(exc),
            }

    def generate(self, text: str, mode: str, max_new_tokens: int, temperature: float, top_p: float) -> dict[str, Any]:
        payload = json.dumps(
            {
                "text": text,
                "mode": mode,
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
                "top_p": top_p,
            }
        ).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))


class GenerationBackend:
    def __init__(self, model_name: str, adapter_path: str | None) -> None:
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
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            self._error = (
                "Missing inference dependencies. Activate .venv or install torch, transformers, and peft."
            )
            raise RuntimeError(self._error) from exc

        self._torch = torch
        try:
            tokenizer = AutoTokenizer.from_pretrained(self.model_name, use_fast=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            base_model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            )

            model = base_model
            if self.adapter_path:
                adapter_dir = Path(self.adapter_path)
                if adapter_dir.exists():
                    from peft import PeftModel

                    model = PeftModel.from_pretrained(base_model, str(adapter_dir))
                else:
                    self._error = f"Adapter path does not exist: {self.adapter_path}"
                    raise RuntimeError(self._error)

            model.eval()
            self._tokenizer = tokenizer
            self._model = model
            self._loaded = True
        except Exception as exc:  # pragma: no cover - runtime dependent
            self._error = str(exc)
            raise

    def status(self) -> dict[str, Any]:
        ready = self._loaded and self._error is None
        adapter_exists = Path(self.adapter_path).exists() if self.adapter_path else False
        return {
            "ready": ready,
            "loaded": self._loaded,
            "model_name": self.model_name,
            "adapter_path": self.adapter_path,
            "adapter_exists": adapter_exists,
            "error": self._error,
        }

    def generate(self, text: str, mode: str, max_new_tokens: int, temperature: float, top_p: float) -> dict[str, Any]:
        if not text.strip():
            return {"completion": "", "latency_ms": 0, "truncated": False}

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
        return {
            "completion": completion,
            "latency_ms": latency_ms,
            "truncated": False,
        }


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


BACKEND = RemoteGenerationBackend(REMOTE_API) if REMOTE_API else GenerationBackend(DEFAULT_MODEL, DEFAULT_ADAPTER)


class AppHandler(BaseHTTPRequestHandler):
    server_version = "ChatGPMeHTTP/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json_response(HTTPStatus.OK, {"status": "ok", "backend": BACKEND.status()})
            return
        if parsed.path == "/" or parsed.path == "/index.html":
            self._serve_file("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.css":
            self._serve_file("app.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._serve_file("app.js", "application/javascript; charset=utf-8")
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
        except Exception:
            self._json_response(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON payload."})
            return

        try:
            result = BACKEND.generate(text, mode, max_new_tokens, temperature, top_p)
            self._json_response(HTTPStatus.OK, result)
        except Exception as exc:  # pragma: no cover - runtime dependent
            self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": str(exc), "backend": BACKEND.status()},
            )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format % args))

    def _serve_file(self, filename: str, content_type: str) -> None:
        path = STATIC_DIR / filename
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _json_response(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> int:
    server = ThreadingHTTPServer((DEFAULT_HOST, DEFAULT_PORT), AppHandler)
    print(f"ChatGPMe app running at http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    if REMOTE_API:
        print(f"Remote inference: {REMOTE_API}")
    else:
        print(f"Model: {DEFAULT_MODEL}")
        print(f"Adapter: {DEFAULT_ADAPTER}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
