#!/usr/bin/env python3
"""Tests for grader_colab.py — no real LLM calls."""
from __future__ import annotations

from grader_colab import (
    StyleScore,
    GeneratedOutput,
    EvalPrompt,
    PromptComparison,
    AuthorMetrics,
    GenreMetrics,
    EvalReport,
    _aggregate,
    print_report,
)


def test_data_structures() -> None:
    print("Testing data structures...")

    score = StyleScore(style_similarity=75.0, tone_match=80.0,
                       vocabulary_specificity=70.0, authenticity=85.0)
    assert score.average() == 77.5
    print("  ✓ StyleScore")

    output = GeneratedOutput(text="Sample", source="candidate", model_name="test", prompt_id="p1", score=score)
    assert output.score.average() == 77.5
    print("  ✓ GeneratedOutput")

    prompt = EvalPrompt(prompt_id="p1", text="Sample prompt", genre="test", difficulty="easy")
    assert prompt.prompt_id == "p1"
    print("  ✓ EvalPrompt")

    baseline = GeneratedOutput(text="Baseline", source="baseline", model_name="base", prompt_id="p1",
                               score=StyleScore(50, 50, 50, 50))
    comp = PromptComparison(prompt=prompt, baseline_output=baseline, candidate_output=output,
                            candidate_advantage=27.5, winner="candidate")
    assert comp.winner == "candidate"
    print("  ✓ PromptComparison")

    report = EvalReport(author="Test Author", num_prompts=1, comparisons=[comp])
    assert report.to_json().__contains__("Test Author")
    print("  ✓ EvalReport / JSON serialization")

    print("\n✅ All data structure tests passed!")


def test_aggregator() -> None:
    print("\nTesting aggregator...")

    prompt = EvalPrompt(prompt_id="p1", text="Test", genre="dramatic")
    baseline = GeneratedOutput(text="Baseline", source="baseline", model_name="base", prompt_id="p1",
                               score=StyleScore(45, 50, 40, 50))
    candidate = GeneratedOutput(text="Candidate", source="candidate", model_name="cand", prompt_id="p1",
                                score=StyleScore(75, 80, 70, 85))
    comp = PromptComparison(prompt=prompt, baseline_output=baseline, candidate_output=candidate,
                            candidate_advantage=27.5, winner="candidate")

    report = _aggregate("Test Author", [comp])
    assert report.num_prompts == 1
    assert report.author_metrics.candidate_wins == 1
    assert report.author_metrics.candidate_win_rate == 1.0
    assert report.author_metrics.avg_candidate_advantage > 20
    assert "dramatic" in report.genre_metrics
    print("  ✓ Author and genre metrics")

    print_report(report)
    print("\n✅ All aggregator tests passed!")


def main() -> int:
    print("=" * 70)
    print("grader_colab.py — Unit Tests")
    print("=" * 70)
    try:
        test_data_structures()
        test_aggregator()
        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED!")
        print("=" * 70)
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
