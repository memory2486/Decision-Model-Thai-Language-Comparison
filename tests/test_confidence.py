"""The normalization must be exact, because every comparison rests on it."""

import math

import pytest

from decision_models.confidence import (
    CONFIDENCE_FLOOR,
    DELEGATION_FLOOR,
    confidence_scale_report,
    entropy_confidence,
    gate,
    maxp_confidence,
    normalize_choice,
    normalize_noul,
    normalize_score,
    threshold_flip_report,
)


def test_maxp_is_the_largest_probability():
    assert maxp_confidence({"a": 0.7, "b": 0.3}) == pytest.approx(0.7)
    assert maxp_confidence([0.1, 0.9]) == pytest.approx(0.9)
    assert maxp_confidence(None) is None
    assert maxp_confidence({}) is None


def test_entropy_confidence_matches_one_minus_normalized_entropy():
    p = [0.94, 0.02, 0.02, 0.02]
    h = -sum(x * math.log(x) for x in p)
    expected = 1.0 - h / math.log(4)
    assert entropy_confidence(p) == pytest.approx(expected)
    assert entropy_confidence(p) == pytest.approx(0.7887286654011272)


def test_a_uniform_distribution_is_zero_confidence():
    assert entropy_confidence([0.25, 0.25, 0.25, 0.25]) == pytest.approx(0.0)


def test_a_certain_answer_is_one_confidence():
    assert entropy_confidence([1.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_entropy_is_not_the_same_scale_as_maxp():
    """The whole reason this module exists."""
    probabilities = [0.94, 0.02, 0.02, 0.02]
    assert maxp_confidence(probabilities) == pytest.approx(0.94)
    assert entropy_confidence(probabilities) < DELEGATION_FLOOR


def test_gate_fails_closed_when_confidence_is_absent():
    assert gate(None) == "confusion"


def test_gate_bands_match_the_typescript_floor():
    assert gate(0.49) == "confusion"
    assert gate(CONFIDENCE_FLOOR) == "confusion"
    assert gate(0.79) == "confusion"
    assert gate(DELEGATION_FLOOR) == "delegated"
    assert gate(0.94) == "delegated"


def test_normalize_choice_keeps_every_confidence_notion():
    answer = normalize_choice("billing", {"billing": 0.9, "other": 0.1},
                              native_confidence=0.5, abstain=0.01,
                              native_answer_confidence=0.9)
    assert answer["type"] == "choice"
    assert answer["choice"] == "billing"
    assert answer["answer_confidence"] == pytest.approx(0.9)
    assert answer["confidence"] == pytest.approx(entropy_confidence({"billing": 0.9, "other": 0.1}))
    assert answer["native_confidence"] == pytest.approx(0.5)
    assert answer["native_answer_confidence"] == pytest.approx(0.9)
    assert answer["abstain"] == pytest.approx(0.01)


def test_normalize_choice_reports_missing_native_fields_as_none():
    """OpenThai has no max-p field; None must survive rather than become 0.0."""
    answer = normalize_choice("a", {"a": 0.8, "b": 0.2}, native_confidence=0.3)
    assert answer["native_answer_confidence"] is None
    assert answer["native_confidence"] == pytest.approx(0.3)


def test_normalize_score_carries_the_legend():
    answer = normalize_score(1.4, {"0": 0.1, "1": 0.8, "2": 0.1},
                             legend={"0": "calm", "1": "annoyed", "2": "angry"})
    assert answer["type"] == "score"
    assert answer["score"] == pytest.approx(1.4)
    assert answer["legend"]["2"] == "angry"
    assert answer["answer_confidence"] == pytest.approx(0.8)


def test_normalize_noul_uses_max_of_p_and_one_minus_p():
    assert normalize_noul(0.99)["answer_confidence"] == pytest.approx(0.99)
    assert normalize_noul(0.01)["answer_confidence"] == pytest.approx(0.99)
    assert normalize_noul(0.5)["answer_confidence"] == pytest.approx(0.5)


def test_threshold_flip_report_counts_a_documented_flip():
    cases = [
        {"qid": "q", "model": "openthai", "language": "en",
         "answer_confidence": 0.94, "confidence": 0.7887, "correct": True},
        {"qid": "q", "model": "openthai", "language": "en",
         "answer_confidence": 0.95, "confidence": 0.94, "correct": True},
    ]
    result = threshold_flip_report(cases)
    assert result["cases_considered"] == 2
    assert result["flips"] == 1
    assert result["flip_rate"] == pytest.approx(0.5)
    assert result["examples"][0]["answer_confidence"] == pytest.approx(0.94)


def test_threshold_flip_report_ignores_cases_without_both_numbers():
    result = threshold_flip_report([{"qid": "q", "answer_confidence": 0.9}])
    assert result["cases_considered"] == 0
    assert result["flip_rate"] is None


def test_confidence_scale_report_separates_the_two_means():
    cases = [
        {"model": "laya-en", "answer_confidence": 0.9, "confidence": 0.8,
         "native_confidence": 0.8, "native_answer_confidence": 0.9},
        {"model": "laya-en", "answer_confidence": 0.7, "confidence": 0.6,
         "native_confidence": 0.6, "native_answer_confidence": 0.7},
    ]
    out = confidence_scale_report(cases)
    assert out["laya-en"]["mean_answer_confidence"] == pytest.approx(0.8)
    assert out["laya-en"]["mean_confidence"] == pytest.approx(0.7)
    assert out["laya-en"]["mean_gap_answer_minus_entropy"] == pytest.approx(0.1)
