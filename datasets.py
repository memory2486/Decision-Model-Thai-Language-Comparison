"""Public benchmark replication, to validate the rig against published numbers.

The focused set shows *where* the two models differ on your tasks. This module
answers a different question -- can the harness reproduce a number someone else
published? -- because a rig that cannot reproduce a known result cannot be
trusted on an unknown one.

MASSIVE (``AmazonScience/massive``) is the centrepiece: 51 languages including
``th-TH`` and ``en-US``, one million utterances, 60 intents, and -- the reason
it is here -- **parallel** across locales, so the English and Thai rows carry the
same intent label. That makes it the controlled bilingual comparison the
hand-written set can only approximate, and its 60-way choice is the high
cardinality case Laya's option budget is documented to struggle with.

Reference points to check a run against, from each project's own materials (not
measured here): OpenThai-SystemOne reports 90.0% on MASSIVE-th with ECE 0.043;
Laya reports 0.783 on MASSIVE intent for English and 0.657 for
``laya-multilingual``.

The row builders are pure functions over already-loaded records, so the
transformation is unit-tested without a download; only :func:`load_*` needs the
``datasets`` package.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from . import bench
from .limits import MAX_CHOICE_OPTIONS, MAX_SCORE_LEVELS

MASSIVE = "AmazonScience/massive"
XNLI = "facebook/xnli"

MASSIVE_LOCALES = {"en": "en-US", "th": "th-TH"}


class DatasetUnavailable(RuntimeError):
    """The `datasets` package or the upstream dataset is not available."""


def label_text(name: str) -> str:
    """`alarm_set` -> `alarm set`, so a criteria description reads as English."""
    return name.replace("_", " ").replace("-", " ").strip()


def intent_question(feature_names: Sequence[str]) -> Dict[str, Any]:
    """The 60-way intent question, or fewer if the feature has fewer labels."""
    names = [str(n) for n in feature_names]
    if len(names) > MAX_CHOICE_OPTIONS:
        raise ValueError(
            "MASSIVE declares %d intents, over the shared cap of %d; the comparison "
            "cannot ask a question the smaller engine would reject"
            % (len(names), MAX_CHOICE_OPTIONS)
        )
    return {
        "intent": {
            "type": "choice",
            "instructions": "Which intent is the user expressing?",
            "criteria": {name: label_text(name) for name in names},
        }
    }


def rows_from_massive_records(
    feature_names: Sequence[str],
    records: Iterable[Mapping[str, Any]],
    locale: str,
    language: str,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """MASSIVE records -> harness rows, one per utterance.

    ``expected`` is the intent label, which MASSIVE guarantees is the same
    intent in every locale for the same utterance -- so an English row and its
    Thai counterpart are the same task with the same gold label.
    """
    questions = intent_question(feature_names)
    names = [str(n) for n in feature_names]
    rows: List[Dict[str, Any]] = []
    for index, record in enumerate(records):
        if limit is not None and len(rows) >= limit:
            break
        label = record.get("intent")
        if isinstance(label, int) and 0 <= label < len(names):
            label = names[label]
        if label not in questions["intent"]["criteria"]:
            continue
        utterance = record.get("utt")
        if not isinstance(utterance, str) or not utterance.strip():
            continue
        rows.append({
            "id": "massive-%s-%04d" % (locale, index),
            "state": utterance,
            "questions": questions,
            "expected": {"intent": label},
            "language": language,
            "family": "massive-intent",
            "tags": ["massive-%s-%04d" % (locale, index), "massive-intent", language],
        })
    return rows


XNLI_LABELS = {"entailment": "entailment", "neutral": "neutral", "contradiction": "contradiction"}

XNLI_QUESTIONS = {
    "relation": {
        "type": "choice",
        "instructions": "What is the relation between the premise and the hypothesis?",
        "criteria": dict(XNLI_LABELS),
    }
}


def rows_from_xnli_records(
    records: Iterable[Mapping[str, Any]],
    language: str,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """XNLI records -> three-way NLI rows (entailment / neutral / contradiction)."""
    rows: List[Dict[str, Any]] = []
    for index, record in enumerate(records):
        if limit is not None and len(rows) >= limit:
            break
        label = record.get("label")
        if isinstance(label, int):
            ordered = ["entailment", "neutral", "contradiction"]
            if not 0 <= label < len(ordered):
                continue
            label = ordered[label]
        if label not in XNLI_LABELS:
            continue
        premise, hypothesis = record.get("premise"), record.get("hypothesis")
        if not isinstance(premise, str) or not isinstance(hypothesis, str):
            continue
        item_id = "xnli-%s-%04d" % (language, index)
        rows.append({
            "id": item_id,
            "state": {"premise": premise, "hypothesis": hypothesis},
            "questions": XNLI_QUESTIONS,
            "expected": {"relation": label},
            "language": language,
            "family": "xnli",
            "tags": [item_id, "xnli", language],
        })
    return rows


def _require_datasets():
    try:
        import datasets  # noqa: F401
    except ImportError as exc:
        raise DatasetUnavailable(
            "the `datasets` package is not installed; the public-benchmark phase needs it "
            "(`pip install datasets`). Nothing else in this package does."
        ) from exc
    return datasets


def load_massive(language: str = "en", split: str = "test", limit: Optional[int] = 120,
                 **kwargs: Any) -> List[Dict[str, Any]]:
    """Download one MASSIVE locale and build its rows."""
    if language not in MASSIVE_LOCALES:
        raise ValueError("no MASSIVE locale for %r; expected one of %s"
                         % (language, ", ".join(sorted(MASSIVE_LOCALES))))
    datasets = _require_datasets()
    locale = MASSIVE_LOCALES[language]
    dataset = datasets.load_dataset(MASSIVE, locale, split=split, **kwargs)
    names = dataset.features["intent"].names if hasattr(dataset.features["intent"], "names") else []
    return rows_from_massive_records(names, dataset, locale=locale, language=language, limit=limit)


def load_xnli(language: str = "en", split: str = "test", limit: Optional[int] = 120,
              **kwargs: Any) -> List[Dict[str, Any]]:
    """Download one XNLI locale and build its rows."""
    datasets = _require_datasets()
    dataset = datasets.load_dataset(XNLI, language, split=split, **kwargs)
    return rows_from_xnli_records(dataset, language=language, limit=limit)


def write_rows(rows: Sequence[Mapping[str, Any]], path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")
    return path


def build(
    out_path: Optional[str] = None,
    limit: int = 120,
    languages: Sequence[str] = ("en", "th"),
    include_xnli: bool = True,
) -> List[Dict[str, Any]]:
    """Build the public dataset file: MASSIVE per language, plus XNLI for contrast."""
    rows: List[Dict[str, Any]] = []
    for language in languages:
        rows.extend(load_massive(language, limit=limit))
    if include_xnli:
        for language, code in (("en", "en"), ("th", "th")):
            rows.extend(load_xnli(code, limit=limit))
    path = out_path or os.path.join(bench.DATA, "public_items.jsonl")
    write_rows(rows, path)
    return rows


def main() -> None:
    rows = build()
    families: Dict[str, int] = {}
    languages: Dict[str, int] = {}
    for row in rows:
        families[row["family"]] = families.get(row["family"], 0) + 1
        languages[row["language"]] = languages.get(row["language"], 0) + 1
    print("wrote %d rows" % len(rows))
    print("by family:", dict(sorted(families.items())))
    print("by language:", languages)


if __name__ == "__main__":
    main()
