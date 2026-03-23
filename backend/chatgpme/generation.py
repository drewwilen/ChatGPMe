from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .retrieval import StyleRetriever
from .storage import CorpusStore

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
}


@dataclass(slots=True)
class GeneratedDraft:
    user_id: str
    mode: str
    prompt: str
    used_model: str
    retrieved_examples: list[str]
    assembled_prompt: str
    text: str


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _style_keywords(examples: list[str], top_n: int = 6) -> list[str]:
    counts: Counter[str] = Counter()
    for example in examples:
        for token in _tokenize(example):
            if token in STOPWORDS or len(token) < 4:
                continue
            counts[token] += 1
    return [word for word, _ in counts.most_common(top_n)]


class DraftGenerator:
    def __init__(self, store: CorpusStore | None = None) -> None:
        self.store = store or CorpusStore()
        self.retriever = StyleRetriever(store=self.store)

    def generate_in_user_style(
        self,
        user_id: str,
        prompt: str,
        mode: str,
        top_k: int = 3,
    ) -> GeneratedDraft:
        mode = mode.lower().strip()
        if mode not in {"baseline", "personalized"}:
            raise ValueError("mode must be one of: baseline, personalized")

        if mode == "baseline":
            assembled_prompt = (
                "Write a polished response to the user prompt in a clear, neutral voice.\n"
                f"Prompt: {prompt}"
            )
            text = (
                f"{prompt}\n\n"
                "This is a baseline draft generated without personal corpus retrieval. "
                "Connect your preferred model API here for production-quality output."
            )
            return GeneratedDraft(
                user_id=user_id,
                mode=mode,
                prompt=prompt,
                used_model="mock_local_baseline",
                retrieved_examples=[],
                assembled_prompt=assembled_prompt,
                text=text,
            )

        retrieved = self.retriever.retrieve(user_id=user_id, prompt=prompt, top_k=top_k)
        if not retrieved:
            raise ValueError(
                "No matching style examples were found for this user. "
                "Ingest more corpus data or try a broader prompt."
            )

        examples = [item.chunk.text[:600] for item in retrieved]
        keywords = _style_keywords(examples)
        joined_keywords = ", ".join(keywords) if keywords else "clear, specific language"
        numbered_examples = "\n\n".join(
            [f"Example {i + 1}:\n{text}" for i, text in enumerate(examples)]
        )
        assembled_prompt = (
            "You are writing in the user's style.\n"
            "Use the examples for voice, tone, and word choice.\n"
            f"User prompt: {prompt}\n\n"
            f"{numbered_examples}\n\n"
            "Now write a final response in that style."
        )
        text = (
            f"{prompt}\n\n"
            f"Personalized draft cues: {joined_keywords}. "
            "This draft path is wired for retrieval-conditioned generation; "
            "plug in your model API call here next."
        )

        return GeneratedDraft(
            user_id=user_id,
            mode=mode,
            prompt=prompt,
            used_model="mock_local_personalized",
            retrieved_examples=examples,
            assembled_prompt=assembled_prompt,
            text=text,
        )

