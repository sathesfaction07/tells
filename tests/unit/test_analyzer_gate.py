"""The gate that decides whether the LLM is called at all.

`analyzer.py` reads `if self.reasoner and level == "MEDIUM":`. That single line is the whole
of the "reason only about the uncertain cases" design, and it was untested -- the item asking
somebody to *confirm* it had been open since the project was built, and reading the line is a
weaker confirmation than pinning it.

Why it matters in both directions:

  fires too often   every HIGH and LOW case pays for an LLM call that cannot change the
                    verdict, because a confident score is not what the reasoner is for
  fires too rarely  the MEDIUM band is exactly the set of cases a human would otherwise
                    have to adjudicate, so skipping it removes the feature

The reasoner is a stub here. These tests are about WHEN it is consulted and what its verdict
is allowed to do to the level -- not about the quality of its reasoning, which no test can
assert.
"""

from __future__ import annotations

import asyncio

import pytest

from evasion_detect.core.analyzer import EvasionAnalyzer
from evasion_detect.core.scoring import THRESHOLDS, Signal, classify_confidence


class RecordingReasoner:
    """Stands in for the Bedrock-backed reasoner and records whether it was consulted."""

    def __init__(self, verdict: str | None = None):
        self.verdict = verdict
        self.calls: list[tuple[str, float]] = []

    def reason(self, product_id: str, signals: list[Signal], confidence: float) -> dict | None:
        self.calls.append((product_id, confidence))
        if self.verdict is None:
            return None
        return {
            "verdict": self.verdict,
            "reasoning": "stub",
            "alternative_explanation": "stub",
            "recommended_action": "stub",
        }


class StubSource:
    """A single source returning one signal at a chosen score."""

    name = "annotations"

    def __init__(self, raw_score: float):
        self.raw_score = raw_score

    async def gather(self, product_id: str, cutoff) -> Signal:
        return Signal(
            source="annotations",
            raw_score=self.raw_score,
            count=1,
            summary="stub",
        )


def analyse(raw_score: float, reasoner=None) -> dict:
    analyzer = EvasionAnalyzer(llm_reasoning=False)
    analyzer.sources = [StubSource(raw_score)]
    analyzer.reasoner = reasoner
    return asyncio.run(analyzer.analyze("P-1"))


def score_landing_in(level: str) -> float:
    """A raw score whose single-source confidence classifies as `level`."""
    for candidate in [float(n) for n in range(0, 101)]:
        if classify_confidence(candidate) == level:
            return candidate
    raise AssertionError(f"no score classifies as {level}")


class TestTheReasonerIsConsultedOnlyForMedium:
    def test_a_medium_case_consults_it(self):
        reasoner = RecordingReasoner()
        result = analyse(score_landing_in("MEDIUM"), reasoner)
        assert result["level"] == "MEDIUM"
        assert len(reasoner.calls) == 1, "MEDIUM is the band the reasoner exists for"

    @pytest.mark.parametrize("level", ["HIGH", "LOW"])
    def test_a_confident_case_does_not(self, level):
        reasoner = RecordingReasoner()
        result = analyse(score_landing_in(level), reasoner)
        # Assert the level was actually REACHED, so this cannot pass because the analyser
        # produced something else entirely and skipped the reasoner for the wrong reason.
        assert result["level"] == level
        assert reasoner.calls == [], f"{level} must not pay for an LLM call"

    def test_no_reasoner_means_no_call_and_no_crash(self):
        result = analyse(score_landing_in("MEDIUM"), reasoner=None)
        assert result["level"] == "MEDIUM"
        assert result["llm_reasoning"] is None


class TestWhatTheVerdictIsAllowedToDo:
    """It may move a MEDIUM case to either end, and may not touch anything else."""

    def test_evasive_promotes_medium_to_high(self):
        result = analyse(score_landing_in("MEDIUM"), RecordingReasoner("EVASIVE"))
        assert result["level"] == "HIGH"

    def test_legitimate_demotes_medium_to_low(self):
        result = analyse(score_landing_in("MEDIUM"), RecordingReasoner("LEGITIMATE"))
        assert result["level"] == "LOW"

    def test_an_unrecognised_verdict_leaves_the_level_alone(self):
        result = analyse(score_landing_in("MEDIUM"), RecordingReasoner("UNSURE"))
        assert result["level"] == "MEDIUM", "only the two known verdicts may move it"

    def test_a_reasoner_returning_nothing_leaves_the_level_alone(self):
        result = analyse(score_landing_in("MEDIUM"), RecordingReasoner(None))
        assert result["level"] == "MEDIUM"
        assert result["llm_reasoning"] is None

    def test_the_confidence_number_is_never_rewritten(self):
        """The verdict changes the LEVEL only.

        So a report can show a HIGH case sitting at a mid-range score, which looks
        inconsistent and is honest: the number is what the signals said, and the level is what
        the reasoner concluded. Collapsing them would hide which of the two produced the
        verdict.
        """
        raw = score_landing_in("MEDIUM")
        plain = analyse(raw)
        promoted = analyse(raw, RecordingReasoner("EVASIVE"))
        assert promoted["confidence"] == plain["confidence"]
        assert promoted["level"] == "HIGH" and plain["level"] == "MEDIUM"


class TestTheBandBoundaries:
    def test_the_thresholds_are_inclusive_at_the_bottom(self):
        assert classify_confidence(THRESHOLDS["high"]) == "HIGH"
        assert classify_confidence(THRESHOLDS["medium"]) == "MEDIUM"
        assert classify_confidence(THRESHOLDS["medium"] - 0.1) == "LOW"

    def test_a_score_exactly_on_the_high_threshold_skips_the_reasoner(self):
        """The boundary decides whether an LLM is called, so it is pinned rather than assumed."""
        reasoner = RecordingReasoner()
        analyse(THRESHOLDS["high"], reasoner)
        assert reasoner.calls == []
