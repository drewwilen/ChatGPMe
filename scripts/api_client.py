#!/usr/bin/env python3
"""Python API client for ChatGPMe.

Usage:
    from api_client import ChatGPMeClient
    
    client = ChatGPMeClient(base_url="http://localhost:8000")
    result = client.generate("Your prompt here")
    print(result.completion)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import request
from urllib.error import URLError


@dataclass
class GenerationResult:
    """Result of a text generation request."""

    completion: str
    latency_ms: int
    truncated: bool
    error: str | None = None

    @property
    def success(self) -> bool:
        """Whether generation succeeded."""
        return self.error is None


@dataclass
class HealthStatus:
    """Health check result."""

    ready: bool
    loaded: bool
    model_name: str
    adapter_path: str | None
    error: str | None = None
    remote_url: str | None = None


@dataclass
class EvalResult:
    """Result of an evaluation."""

    author: str
    num_prompts: int
    candidate_wins: int
    baseline_wins: int
    avg_baseline_score: float
    avg_candidate_score: float
    avg_advantage: float
    candidate_win_rate: float
    error: str | None = None

    @property
    def success(self) -> bool:
        """Whether evaluation succeeded."""
        return self.error is None


class ChatGPMeClient:
    """Client for ChatGPMe REST API.
    
    Provides convenient methods to interact with a running ChatGPMe server.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: int = 120) -> None:
        """Initialize the client.
        
        Args:
            base_url: Base URL of the ChatGPMe server (default: http://127.0.0.1:8000)
            timeout: Request timeout in seconds (default: 120)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> HealthStatus:
        """Get server health status.
        
        Returns:
            HealthStatus with model info and readiness
        """
        try:
            response = self._request("GET", "/api/health")
            backend = response.get("backend", {})
            return HealthStatus(
                ready=backend.get("ready", False),
                loaded=backend.get("loaded", False),
                model_name=backend.get("model_name", "unknown"),
                adapter_path=backend.get("adapter_path"),
                error=backend.get("error"),
                remote_url=backend.get("remote_url"),
            )
        except Exception as e:
            return HealthStatus(
                ready=False,
                loaded=False,
                model_name="unknown",
                adapter_path=None,
                error=str(e),
            )

    def generate(
        self,
        text: str,
        mode: str = "editor_continue",
        max_new_tokens: int = 80,
        temperature: float = 0.7,
        top_p: float = 0.95,
    ) -> GenerationResult:
        """Generate text continuation.
        
        Args:
            text: Input prompt
            mode: Generation mode (editor_continue, assistant_draft, assistant_rewrite, assistant_continue)
            max_new_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-2.0)
            top_p: Top-p sampling parameter
            
        Returns:
            GenerationResult with completion text
        """
        try:
            response = self._request(
                "POST",
                "/api/generate",
                {
                    "text": text,
                    "mode": mode,
                    "max_new_tokens": max_new_tokens,
                    "temperature": temperature,
                    "top_p": top_p,
                },
            )
            return GenerationResult(
                completion=response.get("completion", ""),
                latency_ms=response.get("latency_ms", 0),
                truncated=response.get("truncated", False),
            )
        except Exception as e:
            return GenerationResult(completion="", latency_ms=0, truncated=False, error=str(e))

    def generate_draft(
        self, prompt: str, max_tokens: int = 180, temperature: float = 0.7
    ) -> GenerationResult:
        """Generate a draft from a writing prompt.
        
        Args:
            prompt: Writing request (e.g., "Write about your experience with this project")
            max_tokens: Maximum tokens (default 180)
            temperature: Sampling temperature
            
        Returns:
            GenerationResult with draft text
        """
        return self.generate(
            prompt,
            mode="assistant_draft",
            max_new_tokens=max_tokens,
            temperature=temperature,
        )

    def generate_rewrite(
        self, text: str, max_tokens: int = 180, temperature: float = 0.7
    ) -> GenerationResult:
        """Rewrite text in the user's style.
        
        Args:
            text: Text to rewrite
            max_tokens: Maximum tokens (default 180)
            temperature: Sampling temperature
            
        Returns:
            GenerationResult with rewritten text
        """
        return self.generate(
            text,
            mode="assistant_rewrite",
            max_new_tokens=max_tokens,
            temperature=temperature,
        )

    def generate_continuation(
        self, text: str, max_tokens: int = 120, temperature: float = 0.7
    ) -> GenerationResult:
        """Continue text from a given starting point.
        
        Args:
            text: Text to continue from
            max_tokens: Maximum tokens (default 120)
            temperature: Sampling temperature
            
        Returns:
            GenerationResult with continuation
        """
        return self.generate(
            text,
            mode="assistant_continue",
            max_new_tokens=max_tokens,
            temperature=temperature,
        )

    def editor_suggestion(self, text: str) -> GenerationResult:
        """Get editor completion suggestion (short).
        
        Args:
            text: Current editor text
            
        Returns:
            GenerationResult with suggestion (max 20 tokens)
        """
        return self.generate(
            text,
            mode="editor_continue",
            max_new_tokens=20,
            temperature=0.45,
        )

    def _request(self, method: str, path: str, data: dict[str, Any] | None = None) -> dict:
        """Make HTTP request to API.
        
        Args:
            method: HTTP method (GET, POST)
            path: API path (e.g., "/api/generate")
            data: Optional JSON data for POST requests
            
        Returns:
            Response as dictionary
            
        Raises:
            URLError: If request fails
            json.JSONDecodeError: If response is not valid JSON
        """
        url = f"{self.base_url}{path}"

        if method == "GET":
            with request.urlopen(url, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        elif method == "POST":
            if data is None:
                data = {}
            payload = json.dumps(data).encode("utf-8")
            req = request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        raise ValueError(f"Unsupported HTTP method: {method}")


# Convenience functions
_default_client: ChatGPMeClient | None = None


def set_default_client(client: ChatGPMeClient) -> None:
    """Set the default client for convenience functions."""
    global _default_client
    _default_client = client


def get_default_client() -> ChatGPMeClient:
    """Get or create the default client."""
    global _default_client
    if _default_client is None:
        _default_client = ChatGPMeClient()
    return _default_client


def health() -> HealthStatus:
    """Get server health status using default client."""
    return get_default_client().health()


def generate(
    text: str,
    mode: str = "editor_continue",
    max_new_tokens: int = 80,
    temperature: float = 0.7,
    top_p: float = 0.95,
) -> GenerationResult:
    """Generate text using default client."""
    return get_default_client().generate(text, mode, max_new_tokens, temperature, top_p)


def generate_draft(prompt: str, max_tokens: int = 180) -> GenerationResult:
    """Generate a draft using default client."""
    return get_default_client().generate_draft(prompt, max_tokens)


def generate_rewrite(text: str, max_tokens: int = 180) -> GenerationResult:
    """Rewrite text using default client."""
    return get_default_client().generate_rewrite(text, max_tokens)


def generate_continuation(text: str, max_tokens: int = 120) -> GenerationResult:
    """Continue text using default client."""
    return get_default_client().generate_continuation(text, max_tokens)


def editor_suggestion(text: str) -> GenerationResult:
    """Get editor suggestion using default client."""
    return get_default_client().editor_suggestion(text)
