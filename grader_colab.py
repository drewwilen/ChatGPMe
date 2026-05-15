#!/usr/bin/env python3
"""Self-contained grader for use in Google Colab.

Setup:
    !pip install openai anthropic -q

    import os
    os.environ["OPENAI_API_KEY"] = "sk-..."      # for gpt-4o-mini (default)
    # os.environ["ANTHROPIC_API_KEY"] = "sk-ant-..." # for claude models

Basic usage:
    report = grade(
        author="Shakespeare",
        prompts=[{"text": "Write about ambition: what drives people to want more.", "genre": "philosophical"}],
        baselines=[{"text": "Ambition is a common human trait that motivates people..."}],
        candidates=[{"text": "What burning flame of glory doth consume the restless soul..."}],
    )
    print_report(report)

File-based usage:
    report = grade_from_files(
        author="Shakespeare",
        prompts_file="prompts.json",
        baseline_file="baseline.json",
        candidate_file="candidate.json",
    )
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class StyleScore:
    style_similarity: float
    tone_match: float
    vocabulary_specificity: float
    authenticity: float

    def average(self) -> float:
        return (self.style_similarity + self.tone_match +
                self.vocabulary_specificity + self.authenticity) / 4


@dataclass
class GeneratedOutput:
    text: str
    source: str  # "baseline" or "candidate"
    prompt_id: str
    model_name: str = "unknown"
    score: StyleScore | None = None
    judge_reasoning: str = ""


@dataclass
class EvalPrompt:
    prompt_id: str
    text: str
    genre: str = ""
    difficulty: str = "medium"


@dataclass
class PromptComparison:
    prompt: EvalPrompt
    baseline_output: GeneratedOutput
    candidate_output: GeneratedOutput
    candidate_advantage: float = 0.0
    winner: str = ""


@dataclass
class AuthorMetrics:
    author: str
    num_comparisons: int = 0
    candidate_wins: int = 0
    baseline_wins: int = 0
    ties: int = 0
    avg_baseline_score: float = 0.0
    avg_candidate_score: float = 0.0
    avg_candidate_advantage: float = 0.0
    candidate_win_rate: float = 0.0


@dataclass
class GenreMetrics:
    genre: str
    num_comparisons: int = 0
    candidate_wins: int = 0
    baseline_wins: int = 0
    avg_baseline_score: float = 0.0
    avg_candidate_score: float = 0.0
    avg_candidate_advantage: float = 0.0


@dataclass
class EvalReport:
    author: str
    num_prompts: int = 0
    comparisons: list[PromptComparison] = field(default_factory=list)
    author_metrics: AuthorMetrics | None = None
    genre_metrics: dict[str, GenreMetrics] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        def _score(s: StyleScore | None) -> dict | None:
            return asdict(s) if s else None

        return {
            "author": self.author,
            "num_prompts": self.num_prompts,
            "created_at": self.created_at,
            "author_metrics": asdict(self.author_metrics) if self.author_metrics else None,
            "genre_metrics": {g: asdict(m) for g, m in self.genre_metrics.items()},
            "comparisons": [
                {
                    "prompt_id": c.prompt.prompt_id,
                    "genre": c.prompt.genre,
                    "winner": c.winner,
                    "candidate_advantage": c.candidate_advantage,
                    "baseline_score": c.baseline_output.score.average() if c.baseline_output.score else None,
                    "candidate_score": c.candidate_output.score.average() if c.candidate_output.score else None,
                    "baseline_text": c.baseline_output.text,
                    "candidate_text": c.candidate_output.text,
                }
                for c in self.comparisons
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

class LLMStyleJudge:
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        local_model=None,
        local_tokenizer=None,
    ) -> None:
        if local_model is not None:
            self.provider = "local"
            self.local_model = local_model
            self.local_tokenizer = local_tokenizer
            self.model = "local"
        elif "claude" in model.lower():
            self.provider = "anthropic"
            self.model = model
            self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        elif "gemini" in model.lower():
            self.provider = "gemini"
            self.model = model
            self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        else:
            self.provider = "openai"
            self.model = model
            self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def evaluate_output(
        self, output: GeneratedOutput, author_name: str, author_samples: list[str] | None = None
    ) -> StyleScore:
        prompt = self._build_prompt(output.text, author_name, author_samples)
        response = self._call_llm(prompt)
        output.judge_reasoning = response
        return self._parse_response(response)

    def _build_prompt(self, text: str, author_name: str, author_samples: list[str] | None) -> str:
        samples_text = ""
        if author_samples:
            samples_text = "\n\nExamples of the author's writing:\n"
            for i, s in enumerate(author_samples[:3], 1):
                samples_text += f"\nExample {i}:\n{s[:300]}{'...' if len(s) > 300 else ''}\n"

        return f"""You are a literary style evaluator. Score how closely the following text resembles the actual writing of {author_name}.

1 = nothing like {author_name} at all
10 = indistinguishable from {author_name}'s real writing
{samples_text}
Text to evaluate:
\"\"\"{text}\"\"\"

Score each dimension 1-10 and give a one-sentence reason. Respond with ONLY valid JSON, no markdown:
{{
  "style_similarity": <int 1-10>,
  "style_similarity_reason": "<one sentence>",
  "tone_match": <int 1-10>,
  "tone_match_reason": "<one sentence>",
  "vocabulary_specificity": <int 1-10>,
  "vocabulary_specificity_reason": "<one sentence>",
  "authenticity": <int 1-10>,
  "authenticity_reason": "<one sentence>",
  "overall_verdict": "<two sentences: does this sound like {author_name} and what gives it away>"
}}"""

    def _call_llm(self, prompt: str) -> str:
        if self.provider == "local":
            return self._call_local(prompt)
        try:
            if self.provider == "openai":
                return self._call_openai(prompt)
            if self.provider == "gemini":
                return self._call_gemini(prompt)
            return self._call_anthropic(prompt)
        except ImportError as e:
            raise SystemExit(f"Missing dependency. Run: pip install openai anthropic google-generativeai\n{e}") from e

    def _call_local(self, prompt: str) -> str:
        import torch
        inputs = self.local_tokenizer(
            prompt, return_tensors="pt", truncation=True, max_length=2048
        ).to(self.local_model.device)
        with torch.no_grad():
            out = self.local_model.generate(
                **inputs,
                max_new_tokens=300,
                temperature=0.3,
                do_sample=True,
                pad_token_id=self.local_tokenizer.eos_token_id,
            )
        return self.local_tokenizer.decode(
            out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True
        ).strip()

    def _call_openai(self, prompt: str) -> str:
        from openai import OpenAI
        if not self.api_key:
            raise ValueError("Set OPENAI_API_KEY environment variable")
        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return response.choices[0].message.content or ""

    def _call_anthropic(self, prompt: str) -> str:
        import anthropic
        if not self.api_key:
            raise ValueError("Set ANTHROPIC_API_KEY environment variable")
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _call_gemini(self, prompt: str) -> str:
        import google.generativeai as genai
        if not self.api_key:
            raise ValueError("Set GEMINI_API_KEY environment variable")
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                max_output_tokens=800,
            ),
        )
        return response.text

    def _parse_response(self, response: str) -> StyleScore:
        # Find the outermost JSON object (handles nested braces)
        s = response.find("{")
        if s >= 0:
            depth, e = 0, -1
            for i, ch in enumerate(response[s:], s):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        e = i + 1
                        break
            if e > s:
                try:
                    data = json.loads(response[s:e])
                    if "style_similarity" in data:
                        score = StyleScore(
                            style_similarity=float(data.get("style_similarity", 50)),
                            tone_match=float(data.get("tone_match", 50)),
                            vocabulary_specificity=float(data.get("vocabulary_specificity", 50)),
                            authenticity=float(data.get("authenticity", 50)),
                        )
                        score.reasons = {
                            "style_similarity": data.get("style_similarity_reason", ""),
                            "tone_match": data.get("tone_match_reason", ""),
                            "vocabulary_specificity": data.get("vocabulary_specificity_reason", ""),
                            "authenticity": data.get("authenticity_reason", ""),
                            "overall_verdict": data.get("overall_verdict", ""),
                        }
                        return score
                except (json.JSONDecodeError, ValueError, KeyError):
                    pass
        print(f"Warning: could not parse judge response: {response[:150]}")
        return StyleScore(50, 50, 50, 50)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate(author: str, comparisons: list[PromptComparison]) -> EvalReport:
    report = EvalReport(
        author=author,
        num_prompts=len(comparisons),
        comparisons=comparisons,
        created_at=datetime.now().isoformat(),
    )
    if not comparisons:
        return report

    am = AuthorMetrics(author=author, num_comparisons=len(comparisons))
    baseline_scores, candidate_scores, advantages = [], [], []

    genre_data: dict[str, list[PromptComparison]] = defaultdict(list)

    for comp in comparisons:
        baseline_scores.append(comp.baseline_output.score.average())
        candidate_scores.append(comp.candidate_output.score.average())
        advantages.append(comp.candidate_advantage)
        if comp.winner == "candidate":
            am.candidate_wins += 1
        elif comp.winner == "baseline":
            am.baseline_wins += 1
        else:
            am.ties += 1
        genre_data[comp.prompt.genre or "uncategorized"].append(comp)

    am.avg_baseline_score = sum(baseline_scores) / len(baseline_scores)
    am.avg_candidate_score = sum(candidate_scores) / len(candidate_scores)
    am.avg_candidate_advantage = sum(advantages) / len(advantages)
    am.candidate_win_rate = am.candidate_wins / len(comparisons)
    report.author_metrics = am

    for genre, comps in genre_data.items():
        gm = GenreMetrics(genre=genre, num_comparisons=len(comps))
        bs = [c.baseline_output.score.average() for c in comps]
        cs = [c.candidate_output.score.average() for c in comps]
        adv = [c.candidate_advantage for c in comps]
        gm.candidate_wins = sum(1 for c in comps if c.winner == "candidate")
        gm.baseline_wins = sum(1 for c in comps if c.winner == "baseline")
        gm.avg_baseline_score = sum(bs) / len(bs)
        gm.avg_candidate_score = sum(cs) / len(cs)
        gm.avg_candidate_advantage = sum(adv) / len(adv)
        report.genre_metrics[genre] = gm

    return report


# ---------------------------------------------------------------------------
# Main grader
# ---------------------------------------------------------------------------

def _compare_one(
    prompt: EvalPrompt,
    baseline: GeneratedOutput,
    candidate: GeneratedOutput,
    author: str,
    judge: LLMStyleJudge,
    author_samples: list[str] | None,
) -> PromptComparison:
    baseline.score = judge.evaluate_output(baseline, author, author_samples)
    candidate.score = judge.evaluate_output(candidate, author, author_samples)

    advantage = candidate.score.average() - baseline.score.average()
    if advantage > 2.0:
        winner = "candidate"
    elif advantage < -2.0:
        winner = "baseline"
    else:
        winner = "tie"

    return PromptComparison(
        prompt=prompt,
        baseline_output=baseline,
        candidate_output=candidate,
        candidate_advantage=advantage,
        winner=winner,
    )


def grade(
    author: str,
    prompts: list[dict[str, Any]],
    baselines: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    author_samples: list[str] | None = None,
    model: str = "gpt-4o-mini",
    judge_model=None,
    judge_tokenizer=None,
) -> EvalReport:
    """Evaluate candidate outputs against baselines.

    Args:
        author: Name of the author style being evaluated (e.g. "Shakespeare").
        prompts: List of dicts with keys: "text", and optionally "genre", "difficulty".
        baselines: List of dicts with key "text" (and optionally "prompt_id", "model_name").
        candidates: List of dicts with key "text" (and optionally "prompt_id", "model_name").
        author_samples: Optional list of authentic writing samples for reference.
        model: LLM judge model name for API-based judging (ignored if judge_model is set).
        judge_model: Optional loaded HuggingFace model to use as judge (no API key needed).
        judge_tokenizer: Tokenizer for judge_model (required when judge_model is set).

    Returns:
        EvalReport with win rates, per-genre breakdowns, and per-prompt comparisons.
    """
    if not (len(prompts) == len(baselines) == len(candidates)):
        raise ValueError(
            f"Length mismatch: {len(prompts)} prompts, "
            f"{len(baselines)} baselines, {len(candidates)} candidates"
        )

    if judge_model is not None:
        judge = LLMStyleJudge(local_model=judge_model, local_tokenizer=judge_tokenizer)
    else:
        judge = LLMStyleJudge(model=model)

    eval_prompts = [
        EvalPrompt(
            prompt_id=p.get("prompt_id", p.get("id", f"prompt_{i}")),
            text=p["text"],
            genre=p.get("genre", ""),
            difficulty=p.get("difficulty", "medium"),
        )
        for i, p in enumerate(prompts)
    ]
    eval_baselines = [
        GeneratedOutput(
            text=b["text"],
            source="baseline",
            prompt_id=b.get("prompt_id", f"prompt_{i}"),
            model_name=b.get("model_name", "unknown"),
        )
        for i, b in enumerate(baselines)
    ]
    eval_candidates = [
        GeneratedOutput(
            text=c["text"],
            source="candidate",
            prompt_id=c.get("prompt_id", f"prompt_{i}"),
            model_name=c.get("model_name", "unknown"),
        )
        for i, c in enumerate(candidates)
    ]

    print(f"\nEvaluating {len(eval_prompts)} prompts for author: {author}")
    print("-" * 60)

    comparisons = []
    for i, (prompt, baseline, candidate) in enumerate(
        zip(eval_prompts, eval_baselines, eval_candidates)
    ):
        comp = _compare_one(prompt, baseline, candidate, author, judge, author_samples)
        comparisons.append(comp)
        print(
            f"  [{i+1}/{len(eval_prompts)}] {prompt.prompt_id}: "
            f"{comp.winner} (advantage: {comp.candidate_advantage:+.1f})"
        )

    return _aggregate(author, comparisons)


def grade_from_files(
    author: str,
    prompts_file: str | Path,
    baseline_file: str | Path,
    candidate_file: str | Path,
    author_samples_file: str | Path | None = None,
    model: str = "gpt-4o-mini",
) -> EvalReport:
    """Load inputs from JSON files and run evaluation.

    JSON formats:
        prompts: [{"text": "...", "genre": "dramatic"}, ...]
        baselines: [{"text": "..."}, ...]
        candidates: [{"text": "..."}, ...]
        author_samples (optional): ["sample text 1", "sample text 2", ...]
    """
    prompts = json.loads(Path(prompts_file).read_text())
    baselines = json.loads(Path(baseline_file).read_text())
    candidates = json.loads(Path(candidate_file).read_text())

    author_samples = None
    if author_samples_file:
        data = json.loads(Path(author_samples_file).read_text())
        author_samples = data if isinstance(data, list) else [data]

    return grade(author, prompts, baselines, candidates, author_samples, model)


def _bar(score: float, width: int = 10) -> str:
    filled = int(round(score / 10 * width))
    filled = max(0, min(width, filled))
    return "[" + "█" * filled + "░" * (width - filled) + f"] {score:.1f}/10"


def print_report(report: EvalReport) -> None:
    """Print a detailed human-readable evaluation report."""
    W = 72

    def rule(char="="):
        print(char * W)

    rule()
    print(f"  STYLE EVALUATION REPORT — {report.author.upper()}")
    print(f"  {report.created_at[:19]}")
    rule()

    # ── Per-prompt detail ────────────────────────────────────────────────────
    for i, comp in enumerate(report.comparisons, 1):
        winner_label = {"candidate": "ADAPTER WINS", "baseline": "BASELINE WINS", "tie": "TIE"}.get(comp.winner, "?")
        adv_sign = f"{comp.candidate_advantage:+.1f}"
        print(f"\n{'─' * W}")
        print(f"  Prompt {i}/{report.num_prompts}  [{comp.prompt.genre.upper()}]  →  {winner_label}  ({adv_sign} pts)")
        print(f"{'─' * W}")
        print(f"  Prompt: {comp.prompt.text}")

        for label, output, tag in [
            ("BASELINE (no adapter)", comp.baseline_output, "B"),
            ("CANDIDATE (adapter)  ", comp.candidate_output, "A"),
        ]:
            print(f"\n  ── {label} ──")
            text = output.text.strip().replace("\n", " ")
            print(f"  Text : {text[:220]}{'…' if len(text) > 220 else ''}")
            if output.score:
                s = output.score
                reasons = getattr(s, "reasons", {})
                print(f"  Style similarity  : {_bar(s.style_similarity)}"
                      + (f"  → {reasons.get('style_similarity','')}" if reasons.get("style_similarity") else ""))
                print(f"  Tone match        : {_bar(s.tone_match)}"
                      + (f"  → {reasons.get('tone_match','')}" if reasons.get("tone_match") else ""))
                print(f"  Vocabulary        : {_bar(s.vocabulary_specificity)}"
                      + (f"  → {reasons.get('vocabulary_specificity','')}" if reasons.get("vocabulary_specificity") else ""))
                print(f"  Authenticity      : {_bar(s.authenticity)}"
                      + (f"  → {reasons.get('authenticity','')}" if reasons.get("authenticity") else ""))
                print(f"  Average           : {_bar(s.average())}")
                if reasons.get("overall_verdict"):
                    print(f"  Verdict : {reasons['overall_verdict']}")

    # ── Overall summary ──────────────────────────────────────────────────────
    if report.author_metrics:
        m = report.author_metrics
        rule()
        print(f"  OVERALL SUMMARY  ({m.num_comparisons} prompts)")
        rule()
        print(f"  Adapter wins  : {m.candidate_wins} / {m.num_comparisons}  ({m.candidate_win_rate*100:.0f}%)")
        print(f"  Baseline wins : {m.baseline_wins} / {m.num_comparisons}")
        print(f"  Ties          : {m.ties} / {m.num_comparisons}")
        print()
        print(f"  Avg baseline score  : {_bar(m.avg_baseline_score)}")
        print(f"  Avg adapter score   : {_bar(m.avg_candidate_score)}")
        print(f"  Avg advantage       : {m.avg_candidate_advantage:+.2f} pts (out of 10)")

        if m.avg_candidate_advantage > 5:
            interp = "The adapter consistently shifts output toward the target style."
        elif m.avg_candidate_advantage > 0:
            interp = "The adapter shows a modest style improvement over the base model."
        elif m.avg_candidate_advantage > -5:
            interp = "The adapter and base model perform similarly overall."
        else:
            interp = "The base model outperforms the adapter on this prompt set."
        print(f"\n  Interpretation: {interp}")

    # ── Per-genre breakdown ──────────────────────────────────────────────────
    if report.genre_metrics:
        print()
        rule("─")
        print("  PER-GENRE BREAKDOWN")
        rule("─")
        for genre in sorted(report.genre_metrics):
            gm = report.genre_metrics[genre]
            win_rate = gm.candidate_wins / gm.num_comparisons if gm.num_comparisons else 0
            delta = gm.avg_candidate_advantage
            trend = "↑ adapter better" if delta > 2 else ("↓ baseline better" if delta < -2 else "≈ even")
            print(f"  {genre:<18} {gm.num_comparisons} prompt(s)  "
                  f"baseline {gm.avg_baseline_score:.1f}/10  adapter {gm.avg_candidate_score:.1f}/10  "
                  f"({delta:+.2f} pts)  {trend}")
    rule()
