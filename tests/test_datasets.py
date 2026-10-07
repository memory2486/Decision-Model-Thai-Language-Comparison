"""The public-benchmark transformations are tested without downloading anything.

The download needs the `datasets` package, which is deliberately not a
dependency of the rest of the harness. These tests drive the pure row builders
with synthetic records, so the part that can silently corrupt a replication --
the mapping from a dataset label to a question option and an expected value --
is verified regardless.
"""

import pytest

from decision_models import datasets
from decision_models.limits import validate_questions


INTENTS = ["alarm_set", "alarm_query", "music_like", "weather_query"]


def massive_records():
    return [
        {"intent": 0, "utt": "set an alarm for 7am"},
        {"intent": 3, "utt": "will it rain tomorrow"},
        {"intent": "music_like", "utt": "play something upbeat"},
    ]


def test_intent_question_names_every_label():
    question = datasets.intent_question(INTENTS)
    assert set(question["intent"]["criteria"]) == set(INTENTS)
    validate_questions(question)


def test_intent_question_is_refused_when_the_label_space_is_too_wide():
    with pytest.raises(ValueError, match="shared cap"):
        datasets.intent_question(["intent_%03d" % i for i in range(101)])


def test_massive_rows_resolve_both_integer_and_string_labels():
    rows = datasets.rows_from_massive_records(INTENTS, massive_records(), "en-US", "en")
    assert [row["expected"]["intent"] for row in rows] == \
        ["alarm_set", "weather_query", "music_like"]


def test_massive_rows_carry_a_valid_question_and_language():
    rows = datasets.rows_from_massive_records(INTENTS, massive_records(), "th-TH", "th")
    for row in rows:
        validate_questions(row["questions"])
        assert row["language"] == "th"
        assert row["expected"]["intent"] in row["questions"]["intent"]["criteria"]
        assert row["family"] == "massive-intent"
        assert row["tags"][-1] == "th"


def test_massive_rows_skip_a_label_outside_the_declared_space():
    """A label the question does not offer would be unanswerable, so it is dropped."""
    records = [{"intent": 99, "utt": "out of range"}, {"intent": 1, "utt": "fine"}]
    rows = datasets.rows_from_massive_records(INTENTS, records, "en-US", "en")
    assert len(rows) == 1
    assert rows[0]["state"] == "fine"


def test_massive_rows_skip_an_empty_utterance():
    rows = datasets.rows_from_massive_records(
        INTENTS, [{"intent": 0, "utt": "   "}, {"intent": 0, "utt": "ok"}], "en-US", "en")
    assert len(rows) == 1


def test_massive_limit_is_respected():
    rows = datasets.rows_from_massive_records(INTENTS, massive_records(), "en-US", "en", limit=2)
    assert len(rows) == 2


def test_the_same_intent_survives_both_locales():
    """This is why MASSIVE is the controlled comparison: the label is language-invariant."""
    english = datasets.rows_from_massive_records(INTENTS, massive_records(), "en-US", "en")
    thai = datasets.rows_from_massive_records(INTENTS, massive_records(), "th-TH", "th")
    assert [r["expected"]["intent"] for r in english] == [r["expected"]["intent"] for r in thai]


def test_xnli_rows_build_a_three_way_question():
    records = [
        {"premise": "A man is playing guitar.", "hypothesis": "A man is playing music.", "label": 0},
        {"premise": "A man is playing guitar.", "hypothesis": "A man is sleeping.", "label": 2},
        {"premise": "A man is playing guitar.", "hypothesis": "A man is outside.", "label": 1},
    ]
    rows = datasets.rows_from_xnli_records(records, "th")
    assert [row["expected"]["relation"] for row in rows] == ["entailment", "contradiction", "neutral"]
    for row in rows:
        validate_questions(row["questions"])
        assert row["language"] == "th"
        assert isinstance(row["state"], dict)
        assert "premise" in row["state"] and "hypothesis" in row["state"]


def test_xnli_accepts_a_named_label():
    rows = datasets.rows_from_xnli_records(
        [{"premise": "p", "hypothesis": "h", "label": "neutral"}], "en")
    assert rows[0]["expected"]["relation"] == "neutral"


def test_xnli_skips_incomplete_records():
    rows = datasets.rows_from_xnli_records(
        [{"premise": "p", "label": 0}, {"premise": "p", "hypothesis": "h", "label": 0}], "en")
    assert len(rows) == 1


def test_rows_feed_the_expansion_the_harness_consumes():
    """The public rows must be usable by the same expansion as the focused set."""
    from decision_models import bench

    rows = datasets.rows_from_massive_records(INTENTS, massive_records(), "en-US", "en")
    examples = bench.expand(rows, models=["openthai"])
    assert len(examples) == len(rows)
    assert {e.model for e in examples} == {"openthai"}
    assert examples[0].questions["intent"]["type"] == "choice"


def test_a_missing_datasets_install_is_reported_clearly(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "datasets":
            raise ImportError("no datasets")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(datasets.DatasetUnavailable, match="pip install datasets"):
        datasets.load_massive("en")


def test_an_unknown_locale_is_refused_before_any_download():
    with pytest.raises(ValueError, match="no MASSIVE locale"):
        datasets.load_massive("de")
