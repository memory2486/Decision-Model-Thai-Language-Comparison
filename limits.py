"""The question constraints both models can survive, intersected.

Asking one model a question the other cannot render produces a comparison of
two different tasks. These are the tighter of the two engines' own limits, so
every item in the benchmark is answerable by both, and a violation is an error
in the dataset rather than a silently degraded score.

Sources (verified against the installed packages, not the docs):

* ``laya.serve``  -- ``MAX_CHOICE_OPTIONS=100``, ``MAX_SCORE_LEVELS=32``,
  ``MAX_TOTAL_OPTIONS=512``, ``MAX_QUESTIONS=64``, ``MAX_STATE_CHARS=50000``.
* OpenThai-SystemOne -- ``choices <= 255``, ``2 <= score levels <= 10``,
  ``max_total_tokens=65536``, ``max_state_tokens=32768``.

The service-level caps are deliberately *not* the model-level ones: a question
that ``laya-serve`` would reject is a question the served comparison cannot ask.
``MAX_TOTAL_OPTIONS`` is Laya's, because it is the only one of the two that
bounds a whole request rather than a single question.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

MAX_CHOICE_OPTIONS = 100
MIN_SCORE_LEVELS = 2
MAX_SCORE_LEVELS = 10
MAX_TOTAL_OPTIONS = 512
MAX_QUESTIONS = 64
MAX_STATE_CHARS = 50000

QTYPES = ("choice", "score", "noul")


class ConstraintError(ValueError):
    """A question violates the shared contract; the message names the question id."""


def _criteria_count(question: Mapping[str, Any]) -> int:
    criteria = question.get("criteria")
    if isinstance(criteria, Mapping):
        return len(criteria)
    if isinstance(criteria, (list, tuple)):
        return len(criteria)
    return 0


def validate_question(qid: str, question: Mapping[str, Any]) -> Dict[str, Any]:
    """Check one question against the shared limits and return it unchanged.

    Returns the same mapping so callers can validate inline:
    ``validate_question(qid, question)`` -> ``question``.
    """
    if not isinstance(question, Mapping):
        raise ConstraintError("question %r must be an object, got %s" % (qid, type(question).__name__))
    qtype = question.get("type")
    if qtype not in QTYPES:
        raise ConstraintError("question %r has type %r; expected one of %s" % (qid, qtype, ", ".join(QTYPES)))
    if not question.get("instructions"):
        raise ConstraintError("question %r has no instructions" % qid)

    n = _criteria_count(question)
    if qtype == "choice":
        if n == 0:
            raise ConstraintError("choice question %r has no criteria" % qid)
        if n > MAX_CHOICE_OPTIONS:
            raise ConstraintError(
                "choice question %r has %d options, over the shared cap of %d"
                % (qid, n, MAX_CHOICE_OPTIONS)
            )
    elif qtype == "score":
        if not (MIN_SCORE_LEVELS <= n <= MAX_SCORE_LEVELS):
            raise ConstraintError(
                "score question %r has %d levels; the shared range is %d to %d"
                % (qid, n, MIN_SCORE_LEVELS, MAX_SCORE_LEVELS)
            )
    # `noul` takes no criteria by contract, so nothing to bound.
    return dict(question)


def validate_questions(questions: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate a whole question set against the shared contract."""
    if not isinstance(questions, Mapping) or not questions:
        raise ConstraintError("questions must be a non-empty object")
    if len(questions) > MAX_QUESTIONS:
        raise ConstraintError("question set has %d questions, over the cap of %d" % (len(questions), MAX_QUESTIONS))
    total = 0
    out: Dict[str, Any] = {}
    for qid, question in questions.items():
        out[qid] = validate_question(str(qid), question)
        total += _criteria_count(question)
    if total > MAX_TOTAL_OPTIONS:
        raise ConstraintError(
            "question set declares %d options in total, over the cap of %d" % (total, MAX_TOTAL_OPTIONS)
        )
    return out


def validate_state(state: Any) -> Any:
    """Bound the state, which reaches both engines as text."""
    text = state if isinstance(state, str) else __import__("json").dumps(state, ensure_ascii=False)
    if len(text) > MAX_STATE_CHARS:
        raise ConstraintError("state is %d characters, over the cap of %d" % (len(text), MAX_STATE_CHARS))
    return state
