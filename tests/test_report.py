"""The report is the deliverable, so its arithmetic and its sections get tested."""

import pytest

from decision_models.report import (
    aggregate,
    bucket_of,
    cross,
    n_options_of,
    recommend,
    render,
    task_correct,
)


def case(model="laya-en", lang="en", qid="route", correct=True, answer_confidence=0.9,
         confidence=0.8, kind="choice", value=None, expected=None, latency=40.0,
         family="routing", item="i1", n_options=4):
    """A synthetic harness case record.

    ``correct`` drives the *answer*, not just a flag: a case marked incorrect
    has to actually say the wrong thing, or ``choice_accuracy`` would disagree
    with ``task_accuracy`` and the fixture would be testing nothing.
    """
    probabilities = {str(i): 0.01 for i in range(n_options)}
    probabilities[str(0)] = 0.97
    answer = {
        "type": kind,
        "answer_confidence": answer_confidence,
        "confidence": confidence,
        "native_confidence": confidence,
        "native_answer_confidence": answer_confidence if model != "openthai" else None,
        "_latency_ms": latency,
        "probabilities": probabilities if kind == "choice" else {"0": 0.9, "1": 0.1},
    }
    if kind == "choice":
        expected = "weather" if expected is None else expected
        answer["choice"] = value if value is not None else (expected if correct else "cost")
    elif kind == "noul":
        expected = True if expected is None else expected
        answer["noul"] = 0.9 if correct else 0.1
    else:
        expected = 1 if expected is None else expected
        answer["score"] = float(expected) if correct else float(expected) + 3.0
    return {
        "qid": qid, "model": model, "language": lang, "tags": [item, family, lang],
        "expected": expected, "answer": answer,
        # `laya.evals` puts `_answer_confidence(answer)` here, i.e. max-p under
        # the name `confidence`. Reproduced faithfully so the report's
        # answer-first lookup is exercised against the real hazard.
        "confidence": answer_confidence,
        "correct": correct if kind != "score" else None,
    }


def test_aggregate_counts_correct_and_total():
    metrics = aggregate([case(correct=True), case(correct=False)])
    assert metrics["n"] == 2
    assert metrics["n_scored"] == 2
    assert metrics["task_accuracy"] == pytest.approx(0.5)
    assert metrics["choice_accuracy"] == pytest.approx(0.5)


def test_aggregate_computes_ece_and_calibration_over_choice_and_noul_only():
    cases = [case(correct=True), case(correct=False, answer_confidence=0.2)]
    metrics = aggregate(cases)
    assert "ece" in metrics and "aurc" in metrics
    assert metrics["n_calibration"] == 2

    score_only = aggregate([case(kind="score")])
    assert "ece" not in score_only, "a score answer has no boolean verdict to calibrate against"


def test_aggregate_reports_both_confidence_means():
    metrics = aggregate([case(answer_confidence=0.9, confidence=0.7)])
    assert metrics["mean_answer_confidence"] == pytest.approx(0.9)
    assert metrics["mean_confidence"] == pytest.approx(0.7)


def test_aggregate_counts_gate_flips():
    """max-p 0.94 delegates, entropy 0.79 clarifies: one flip out of two."""
    cases = [
        case(answer_confidence=0.94, confidence=0.79),
        case(answer_confidence=0.95, confidence=0.94),
    ]
    metrics = aggregate(cases)
    assert metrics["gate_flip_rate_at_0.8"] == pytest.approx(0.5)


def test_aggregate_recovers_option_counts_for_the_cardinality_buckets():
    metrics = aggregate([case(n_options=18), case(n_options=4)])
    assert metrics["mean_options"] == pytest.approx(11.0)
    assert metrics["mean_chance"] == pytest.approx((1 / 18 + 1 / 4) / 2)


def test_latency_percentiles_come_from_the_answer_records():
    metrics = aggregate([case(latency=10.0), case(latency=20.0), case(latency=30.0)])
    assert metrics["latency_p50_ms"] == pytest.approx(20.0)
    assert metrics["latency_p95_ms"] == pytest.approx(30.0)


def test_score_rows_count_correct_within_tolerance():
    inside = case(kind="score")
    inside["answer"]["score"] = 1.4
    inside["expected"] = 1
    assert task_correct(inside) is True

    outside = case(kind="score")
    outside["answer"]["score"] = 2.6
    outside["expected"] = 1
    assert task_correct(outside) is False


def test_options_are_read_back_off_the_answer():
    assert n_options_of(case(n_options=18)) == 18
    assert n_options_of(case(kind="noul")) == 2


def test_buckets_split_the_cardinality_range():
    assert bucket_of(2) == "2-2"
    assert bucket_of(4) == "3-5"
    assert bucket_of(18) == "6-20"
    assert bucket_of(60) == "21+"


def test_cross_builds_the_model_language_grid_the_harness_cannot():
    cases = [case(model="a", lang="en"), case(model="a", lang="th"),
             case(model="b", lang="en", correct=False)]
    grid = cross(cases, lambda c: c["model"], lambda c: c["language"])
    assert grid[("a", "en")]["task_accuracy"] == pytest.approx(1.0)
    assert grid[("b", "en")]["task_accuracy"] == pytest.approx(0.0)


def test_recommend_picks_a_winner_per_language():
    cases = [
        case(model="laya-en", lang="en", correct=True),
        case(model="laya-en", lang="en", correct=True),
        case(model="openthai", lang="en", correct=False),
        case(model="openthai", lang="th", correct=True),
        case(model="openthai", lang="th", correct=True),
        case(model="laya-en", lang="th", correct=False),
    ]
    verdict = recommend(cases, ["laya-en", "openthai"], ["en", "th"])
    assert verdict["winners"] == {"en": "laya-en", "th": "openthai"}
    assert any("not the same in every language" in p for p in verdict["narrative"])
    assert {row[0] for row in verdict["table"]} == {"en", "th"}


def test_recommend_says_so_when_one_model_wins_everywhere():
    cases = [case(model="laya-en", lang="en", correct=True),
             case(model="openthai", lang="en", correct=False),
             case(model="laya-en", lang="th", correct=True),
             case(model="openthai", lang="th", correct=False)]
    verdict = recommend(cases, ["laya-en", "openthai"], ["en", "th"])
    assert set(verdict["winners"].values()) == {"laya-en"}
    assert any("single default" in p for p in verdict["narrative"])


def test_render_carries_every_promised_section():
    cases = [
        case(model="laya-en", lang="en", correct=True, answer_confidence=0.94, confidence=0.79),
        case(model="openthai", lang="th", correct=False, answer_confidence=0.94, confidence=0.79),
    ]
    text = render({"config": {"schema": "t", "laya_version": "0.3.27"}, "cases": cases,
                   "overall": aggregate(cases)}, title="T")
    for heading in ("# T", "## Run identity", "## Overall", "## By language",
                    "## By option count", "## Latency",
                    "## Confidence is two different numbers",
                    "## Where the models disagree", "## Recommendation", "## Limitations"):
        assert heading in text, heading
    assert "No rows errored" in text


def test_render_reports_errored_rows_loudly():
    text = render({"config": {"errored": [{"index": 1}]}, "cases": [], "overall": {}})
    assert "1 rows errored" in text
    assert "No rows errored" not in text


def test_render_states_when_the_models_agree_everywhere():
    cases = [case(model="a", correct=True), case(model="b", correct=True)]
    text = render({"config": {}, "cases": cases, "overall": aggregate(cases)})
    assert "every backend agreed on correctness" in text


def test_render_lists_disagreements_with_both_answers():
    cases = [case(model="laya-en", correct=True), case(model="openthai", correct=False)]
    text = render({"config": {}, "cases": cases, "overall": aggregate(cases)})
    assert "| item | lang | question |" in text
    assert "laya-en" in text and "openthai" in text


def test_disagreements_keep_the_two_languages_apart():
    """An item is a bilingual pair; keying on (item, qid) alone overwrote one row."""
    cases = [
        case(model="laya-en", lang="en", correct=True),
        case(model="openthai", lang="en", correct=False),
        case(model="laya-en", lang="th", correct=False),
        case(model="openthai", lang="th", correct=True),
    ]
    body = render({"config": {}, "cases": cases, "overall": aggregate(cases)})
    table = body.split("## Where the models disagree")[1].split("## Recommendation")[0]
    assert "| i1 | en | route |" in table
    assert "| i1 | th | route |" in table


def test_family_table_is_derived_from_the_dataset():
    """The HTML family table must be read off the JSONL, never typed by hand."""
    from decision_models.tools.build_report_html import family_rows, load

    rows = family_rows()
    assert [r[0] for r in rows] == [
        "routing", "triage", "multi", "noul", "score",
        "cardinality4", "cardinality18", "thai-only",
    ]
    assert sum(r[1] for r in rows) == 68      # authored rows
    assert sum(r[2] for r in rows) == 90      # questions, which is what gets scored

    by_name = {r[0]: r for r in rows}
    # (rows, questions, types, options) -- cardinality18 is the 18-option family.
    assert by_name["cardinality18"][1:] == [6, 6, "choice", "18"]
    assert by_name["noul"][1:] == [8, 8, "noul", "—"]
    # 68 rows x 4 backends is 272, not 360: the harness scores questions.
    assert len(load()["cases"]) == 90 * 4


def test_html_report_substitutes_every_placeholder():
    """An unsubstituted placeholder would ship to the reader as literal __FOO__ text."""
    import re

    from decision_models.tools.build_report_html import build_html, load

    html = build_html(load())
    assert re.search(r"__[A-Za-z][A-Za-z_]*__", html) is None
    # Self-contained means self-contained: nothing to fetch, nothing to execute.
    assert "<script" not in html
    assert "http://" not in html and "https://" not in html
    assert "cardinality18" in html and "Run it again, in this order" in html
