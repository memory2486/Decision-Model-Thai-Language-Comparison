"""Normalizing confidence, so a threshold means the same thing on both models.

This is the module the whole comparison rests on. The two engines do **not**
agree on what ``confidence`` is:

* Laya exposes two numbers. ``answer_confidence`` is ``max(p)`` -- "the
  quantity temperature scaling fits, and the quantity every calibration figure
  in this repository is computed on" (``laya/confidence.py``). Its ``confidence``
  is ``1 - H(p)/log(k)``, documented there as "not calibrated ... not what the
  reported ECE measures".
* OpenThai-SystemOne exposes **only** the second kind: its ``confidence`` is
  "1 ลบด้วยเอนทโรปีที่ทำให้เป็นมาตรฐาน" (1 - normalized entropy), plus an
  ``abstain`` slot Laya's choice answer does not have.

So OpenThai's headline ``confidence`` is formula-identical to the quantity Laya
labels uncalibrated and refuses to threshold on. Measured on a 4-option answer
at ``{0.94, 0.02, 0.02, 0.02}``: ``answer_confidence`` 0.94, entropy
``confidence`` 0.7887 -- and Route_gate's ``DELEGATION_FLOOR`` is 0.8, so the
same answer delegates under one name and clarifies under the other.

Every answer this package emits therefore carries ``answer_confidence``
(``max(p)``, computed here for both models alike) as *the* thresholdable field,
and ``confidence`` (entropy) alongside it. ``native_confidence`` preserves what
the model itself reported, which is what makes the scale mismatch measurable
rather than merely asserted -- see :func:`confidence_scale_report`.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

#: Mirrors `Route_gate/src/supervisor.ts`: below FLOOR never delegate, below
#: DELEGATION_FLOOR clarify, at or above DELEGATION_FLOOR delegate.
CONFIDENCE_FLOOR = 0.5
DELEGATION_FLOOR = 0.8

#: The confidence keys every canonical answer carries, in report order.
ANSWER_FIELDS = ("answer_confidence", "confidence", "native_confidence", "native_answer_confidence")


def maxp_confidence(probabilities: Any) -> Optional[float]:
    """``max(p)``: the calibrated, thresholdable confidence. Laya's ``answer_confidence``."""
    values = _probs(probabilities)
    return max(values) if values else None


def entropy_confidence(probabilities: Any) -> Optional[float]:
    """``1 - H(p)/log(k)``: how concentrated the distribution is. Not calibrated."""
    values = _probs(probabilities)
    if not values:
        return None
    k = len(values)
    if k <= 1:
        return 1.0
    total = sum(values)
    if total <= 0:
        return None
    p = [v / total for v in values]
    h = -sum(x * math.log(x) for x in p if x > 0)
    return max(0.0, min(1.0, 1.0 - h / math.log(k)))


def _probs(probabilities: Any) -> list:
    if isinstance(probabilities, Mapping):
        out = []
        for v in probabilities.values():
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                return []
        return out
    if isinstance(probabilities, (list, tuple)):
        try:
            return [float(v) for v in probabilities]
        except (TypeError, ValueError):
            return []
    return []


def _as_float(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _finish(
    answer: Dict[str, Any],
    probabilities: Any,
    native_confidence: Any,
    native_answer_confidence: Any = None,
) -> Dict[str, Any]:
    """Attach every confidence notion, so downstream code never has to guess.

    Four fields, and the distinction between them is the whole finding:

    ``answer_confidence``
        Raw ``max(p)``, computed here for every backend alike. This is the field
        a threshold belongs on, and computing it identically for both models is
        what makes their ECE and AURC the same measurement. Laya's own
        ``answer_confidence`` is *not* this number: it is ``max(p)`` after
        temperature scaling (measured ~0.15 higher on this benchmark), which is
        why it is recorded separately rather than used here.
    ``confidence``
        ``1 - H(p)/log(k)``, computed here for every backend alike. What the
        *name* ``confidence`` means in **both** models' native APIs -- Laya's
        ``confidence`` and OpenThai's ``confidence`` are the same quantity.
    ``native_confidence``
        What the model itself reported under ``confidence``, kept verbatim so
        the claim above is checkable rather than asserted.
    ``native_answer_confidence``
        Laya additionally reports a max-probability field under this name;
        OpenThai reports none at all. ``None`` here is meaningful.
    """
    answer["answer_confidence"] = maxp_confidence(probabilities)
    answer["confidence"] = entropy_confidence(probabilities)
    answer["native_confidence"] = _as_float(native_confidence)
    answer["native_answer_confidence"] = _as_float(native_answer_confidence)
    return answer


def normalize_choice(
    choice: Any,
    probabilities: Any,
    native_confidence: Any = None,
    abstain: Any = None,
    native_answer_confidence: Any = None,
) -> Dict[str, Any]:
    """One canonical ``choice`` answer."""
    answer: Dict[str, Any] = {
        "type": "choice",
        "choice": choice,
        "probabilities": dict(probabilities) if isinstance(probabilities, Mapping) else probabilities,
    }
    if abstain is not None:
        try:
            answer["abstain"] = float(abstain)
        except (TypeError, ValueError):
            pass
    return _finish(answer, probabilities, native_confidence,
                   native_answer_confidence=native_answer_confidence)


def normalize_score(
    score: Any,
    probabilities: Any = None,
    legend: Any = None,
    native_confidence: Any = None,
    native_answer_confidence: Any = None,
) -> Dict[str, Any]:
    """One canonical ``score`` answer."""
    answer: Dict[str, Any] = {"type": "score", "score": score}
    if probabilities is not None:
        answer["probabilities"] = dict(probabilities) if isinstance(probabilities, Mapping) else probabilities
    if legend is not None:
        answer["legend"] = legend
    return _finish(answer, probabilities, native_confidence,
                   native_answer_confidence=native_answer_confidence)


def normalize_noul(p: Any, native_confidence: Any = None) -> Dict[str, Any]:
    """One canonical ``noul`` answer.

    ``noul`` is a bare probability, so there is no distribution to take an
    entropy over. The thresholdable confidence is ``max(p, 1-p)`` -- the same
    fallback ``laya.evals._answer_confidence`` uses for this question type, so
    the harness and this module agree on the number.
    """
    value = float(p)
    answer: Dict[str, Any] = {"type": "noul", "noul": value}
    answer["answer_confidence"] = max(value, 1.0 - value)
    answer["confidence"] = answer["answer_confidence"]
    answer["native_confidence"] = _as_float(native_confidence)
    answer["native_answer_confidence"] = None
    return answer


def gate(
    answer_confidence: Optional[float],
    floor: float = CONFIDENCE_FLOOR,
    delegation_floor: float = DELEGATION_FLOOR,
) -> str:
    """Map a calibrated confidence onto a routing action.

    Missing confidence is *not* delegation. A model that returned nothing
    usable, or a backend that reported no confidence, must fail closed -- the
    failure this replaces was ``.get("answer_confidence", ...,
    .get("confidence", 0.9))``, where an absent key silently became a
    delegation-grade 0.9.
    """
    if answer_confidence is None:
        return "confusion"
    if answer_confidence < floor:
        return "confusion"
    if answer_confidence < delegation_floor:
        return "confusion"
    return "delegated"


def confidence_of(row: Mapping[str, Any], field: str) -> Optional[float]:
    """Read one confidence field, preferring the canonical answer dict.

    ``laya.evals`` copies a single ``confidence`` onto its case record -- and
    that value is ``_answer_confidence(answer)``, i.e. *max-p*, despite the
    name. Reading the case level for a field called ``confidence`` would
    therefore compare max-p against max-p and find no mismatch at all, so the
    canonical answer (which holds all four fields distinctly) is consulted
    first and the case level only as a fallback for a stripped-down record.
    """
    answer = row.get("answer")
    if isinstance(answer, Mapping):
        value = answer.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    value = row.get(field)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def threshold_flip_report(
    rows: Iterable[Mapping[str, Any]],
    floor: float = DELEGATION_FLOOR,
) -> Dict[str, Any]:
    """How often the *name* of confidence changes the routing decision.

    ``rows`` are case records carrying ``answer_confidence`` and ``confidence``.
    A flip is a case where reading Laya's field delegates and reading
    OpenThai's field clarifies (or the reverse). This turns the scale mismatch
    into a count, which is the number a promotion decision needs.
    """
    flips = []
    considered = 0
    for row in rows:
        a = confidence_of(row, "answer_confidence")
        b = confidence_of(row, "confidence")
        if a is None or b is None:
            continue
        considered += 1
        if gate(a, delegation_floor=floor) != gate(b, delegation_floor=floor):
            flips.append(
                {
                    "qid": row.get("qid"),
                    "model": row.get("model"),
                    "language": row.get("language"),
                    "answer_confidence": a,
                    "confidence": b,
                    "correct": row.get("correct"),
                }
            )
    return {
        "floor": floor,
        "cases_considered": considered,
        "flips": len(flips),
        "flip_rate": (len(flips) / considered) if considered else None,
        "examples": flips[:20],
    }


def confidence_scale_report(cases: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Per-model mean of each confidence notion, to show the scales differ.

    The gap between the two means is the size of the correction a naive port
    would silently skip.
    """
    by_model: Dict[str, Dict[str, list]] = {}
    for case in cases:
        model = str(case.get("model") or "unknown")
        entry = by_model.setdefault(model, {"answer_confidence": [], "confidence": [],
                                           "native_confidence": [], "native_answer_confidence": []})
        for key in entry:
            value = confidence_of(case, key)
            if value is not None:
                entry[key].append(value)
    out: Dict[str, Any] = {}
    for model, series in by_model.items():
        means = {key: (sum(vals) / len(vals)) if vals else None for key, vals in series.items()}
        gap = None
        if means["answer_confidence"] is not None and means["confidence"] is not None:
            gap = means["answer_confidence"] - means["confidence"]
        out[model] = {
            "n": max((len(v) for v in series.values()), default=0),
            "mean_answer_confidence": means["answer_confidence"],
            "mean_confidence": means["confidence"],
            "mean_native_confidence": means["native_confidence"],
            "mean_native_answer_confidence": means["native_answer_confidence"],
            "mean_gap_answer_minus_entropy": gap,
        }
    return out
