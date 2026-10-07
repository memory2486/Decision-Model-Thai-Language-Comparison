"""Both models must always be asked questions both models can answer."""

import pytest

from decision_models.limits import (
    MAX_CHOICE_OPTIONS,
    MAX_SCORE_LEVELS,
    MAX_STATE_CHARS,
    ConstraintError,
    validate_question,
    validate_questions,
    validate_state,
)


def choice(n):
    return {"type": "choice", "instructions": "pick", "criteria": {str(i): "opt" for i in range(n)}}


def score(n):
    return {"type": "score", "instructions": "rate", "criteria": [str(i) for i in range(n)]}


def test_a_normal_choice_passes():
    validate_question("q", choice(4))


def test_choice_at_the_shared_cap_passes():
    validate_question("q", choice(MAX_CHOICE_OPTIONS))


def test_choice_above_the_shared_cap_is_refused():
    """Laya's serve cap is 100, OpenThai's is 255; the tighter one wins."""
    with pytest.raises(ConstraintError) as exc:
        validate_question("q", choice(MAX_CHOICE_OPTIONS + 1))
    assert "shared cap" in str(exc.value)


def test_score_levels_must_be_within_the_open_ended_range():
    validate_question("q", score(2))
    validate_question("q", score(MAX_SCORE_LEVELS))
    with pytest.raises(ConstraintError):
        validate_question("q", score(1))
    with pytest.raises(ConstraintError):
        validate_question("q", score(MAX_SCORE_LEVELS + 1))


def test_noul_needs_no_criteria():
    validate_question("q", {"type": "noul", "instructions": "yes or no?"})


def test_unknown_question_type_is_refused():
    with pytest.raises(ConstraintError):
        validate_question("q", {"type": "rating", "instructions": "x"})


def test_missing_instructions_is_refused():
    with pytest.raises(ConstraintError):
        validate_question("q", {"type": "noul"})


def test_validate_questions_bounds_the_whole_set():
    """Each question is legal; 600 options in one request is not."""
    questions = {"q%d" % i: choice(MAX_CHOICE_OPTIONS) for i in range(6)}
    assert len(questions) < 64, "the set must stay under the question cap to reach the option check"
    with pytest.raises(ConstraintError) as exc:
        validate_questions(questions)
    assert "in total" in str(exc.value)


def test_empty_question_set_is_refused():
    with pytest.raises(ConstraintError):
        validate_questions({})


def test_state_length_is_bounded():
    validate_state("x" * 100)
    with pytest.raises(ConstraintError):
        validate_state("x" * (MAX_STATE_CHARS + 1))


def test_non_string_state_is_measured_as_serialized_text():
    with pytest.raises(ConstraintError):
        validate_state({"body": "x" * (MAX_STATE_CHARS + 1)})
