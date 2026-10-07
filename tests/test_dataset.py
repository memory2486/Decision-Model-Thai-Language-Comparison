"""The focused set is the experiment, so its invariants get asserted, not assumed."""

import os

import pytest
from laya.evals import Example, questions_fingerprint, Dataset

from decision_models import bench
from decision_models.limits import validate_questions, validate_state


@pytest.fixture(scope="module")
def items():
    return bench.load_items()


def test_the_item_file_exists_and_parses(items):
    assert len(items) >= 60, "the plan asks for roughly 60 parallel rows"


def test_every_row_is_answerable_by_both_models(items):
    for item in items:
        validate_questions(item["questions"])
        validate_state(item["state"])


def test_every_expected_key_names_a_real_question(items):
    for item in items:
        unknown = sorted(set(item["expected"]) - set(item["questions"]))
        assert not unknown, "%s expects unknown question(s) %s" % (item["id"], unknown)


def test_expected_types_match_question_types(items):
    for item in items:
        for qid, expected in item["expected"].items():
            qtype = item["questions"][qid]["type"]
            if qtype == "choice":
                assert isinstance(expected, str), item["id"]
            elif qtype == "noul":
                assert isinstance(expected, bool), item["id"]
            elif qtype == "score":
                assert isinstance(expected, (int, float)) and not isinstance(expected, bool), item["id"]


def test_score_expectations_stay_inside_the_declared_levels(items):
    for item in items:
        for qid, expected in item["expected"].items():
            question = item["questions"][qid]
            if question["type"] != "score":
                continue
            levels = question["criteria"]
            assert 0 <= float(expected) <= len(levels) - 1, "%s: %s" % (item["id"], expected)


def test_choice_expectations_are_real_options(items):
    for item in items:
        for qid, expected in item["expected"].items():
            question = item["questions"][qid]
            if question["type"] != "choice":
                continue
            assert expected in question["criteria"], "%s: %s" % (item["id"], expected)


def test_each_item_has_exactly_one_row_per_language(items):
    by_id = {}
    for item in items:
        by_id.setdefault(item["id"], []).append(item["language"])
    for item_id, languages in by_id.items():
        assert len(languages) == len(set(languages)), item_id
        assert set(languages) <= {"en", "th"}, item_id


def test_parallel_items_share_one_label_across_languages(items):
    """If the Thai row had a different label, the two rows would be different tasks."""
    by_id = {}
    for item in items:
        by_id.setdefault(item["id"], []).append(item)
    parallel = 0
    for item_id, rows in by_id.items():
        if len(rows) < 2:
            continue
        parallel += 1
        labels = {tuple(sorted(r["expected"].items())) for r in rows}
        assert len(labels) == 1, item_id
    assert parallel >= 25, "expected most items to be bilingual pairs, got %d" % parallel


def test_language_balance_is_close_to_symmetric(items):
    en = sum(1 for i in items if i["language"] == "en")
    th = sum(1 for i in items if i["language"] == "th")
    assert abs(en - th) <= 6, "en=%d th=%d" % (en, th)


def test_the_control_family_and_the_cardinality_family_are_present(items):
    families = {i["family"] for i in items}
    assert {"routing", "triage", "noul", "score", "cardinality18", "cardinality4"} <= families
    assert "thai-only" in families, "Thai-only registers are the point of the Thai side"


def test_the_eighteen_way_family_really_has_eighteen_options(items):
    cubes = [i for i in items if i["family"] == "cardinality18"]
    assert cubes
    for item in cubes:
        assert len(item["questions"]["next_move"]["criteria"]) == 18


def test_expansion_puts_each_backend_in_one_block():
    """Ordering by model is what makes `release_between_models` cost one load per backend."""
    examples = bench.expand(bench.load_items(), models=["a", "b", "c"])
    order = [e.model for e in examples]
    assert order == sorted(order), "expansion must group by backend"
    assert order.count("a") == len(order) // 3
    assert len({e.model for e in examples}) == 3


def test_expansion_sets_the_language_and_tags_the_harness_slices_by():
    examples = bench.expand(bench.load_items(), models=["a"])
    assert {e.language for e in examples} == {"en", "th"}
    for example in examples:
        assert len(example.tags) >= 3
        assert example.tags[-1] == example.language


def test_expanded_examples_satisfy_the_harness_parser():
    dataset = Dataset(bench.expand(bench.load_items(), models=["a"]))
    assert len(dataset) == len(bench.load_items())
    assert questions_fingerprint(dataset)


def test_limit_caps_authored_items_not_expanded_rows():
    limit = 5
    examples = bench.expand(bench.load_items(), models=["a", "b"], limit=limit)
    distinct = {e.tags[0] for e in examples}
    assert len(distinct) == limit


def test_the_committed_file_matches_what_the_builder_produces():
    """A dataset edited by hand without the builder drifts; this catches that."""
    from decision_models.tools.build_focused import build

    built = build()
    loaded = bench.load_items()
    assert len(built) == len(loaded)
    for produced, on_disk in zip(built, loaded):
        assert produced["id"] == on_disk["id"]
        assert produced["state"] == on_disk["state"]
        assert produced["expected"] == on_disk["expected"]
        assert produced["language"] == on_disk["language"]
