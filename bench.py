"""Run the labelled benchmark through ``laya.evals``.

Laya's harness is the scorer, not a hand-rolled metric stack: it already
computes ``ece``, ``brier``, ``aurc``, ``selective_accuracy@50/@80`` and the
per-question-type evaluators, and it slices by ``language``, ``model``, ``qid``
and ``tag``. Two harnesses would produce two numbers that cannot be compared,
which is the one thing this package exists to avoid.

The dataset is expanded to one row per (item, backend) and **ordered by model
block**. ``DecisionRunner(release_between_models=True)`` then unloads the
previous backend at each block boundary, so the run's peak VRAM is one model
rather than four.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence

import laya
from laya.evals import Dataset, EvalReport, Example, evaluate

from .runners import DEFAULT_MODEL, DecisionRunner
from .runners.openthai_backend import DEFAULT_MODEL_PATH

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RESULTS = os.path.join(HERE, "results")
BASELINES = os.path.join(HERE, "baselines")

FOCUSED_ITEMS = os.path.join(DATA, "focused_items.jsonl")

#: The comparison set. `laya-auto` is Laya used the way it is meant to be used;
#: `laya-en` is the same model driven the way the pre-existing experiments drove
#: it. Keeping both turns the Thai failure mode into a measurement.
DEFAULT_MODELS = ("laya-auto", "laya-en", "laya-ml", "openthai")


def load_items(path: str = FOCUSED_ITEMS) -> List[Dict[str, Any]]:
    """Read the authored item file, keeping the ``id``/``family`` the harness drops."""
    items: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                items.append(json.loads(line))
            except ValueError as exc:
                raise ValueError("%s:%d is not valid JSON: %s" % (path, lineno, exc)) from exc
    if not items:
        raise ValueError("%s contains no items" % path)
    return items


def expand(
    items: Sequence[Dict[str, Any]],
    models: Iterable[str] = DEFAULT_MODELS,
    limit: Optional[int] = None,
) -> List[Example]:
    """One ``Example`` per (item, backend), ordered by backend block.

    ``tags`` carries the item id and the family so the harness's own tag slicing
    can break results down by item family without a second aggregation pass.
    """
    chosen = list(items)
    if limit:
        # `limit` counts authored items, not expanded rows, so a quick run still
        # exercises every family in the same proportion.
        seen: List[str] = []
        for item in chosen:
            if item["id"] not in seen:
                seen.append(item["id"])
        keep = set(seen[:limit])
        chosen = [item for item in chosen if item["id"] in keep]

    examples: List[Example] = []
    for model in models:
        for item in chosen:
            examples.append(
                Example(
                    state=item["state"],
                    questions=item["questions"],
                    expected=item["expected"],
                    tags=tuple(item.get("tags") or (item["id"], item.get("family", "unknown"))),
                    language=item.get("language"),
                    model=model,
                )
            )
    return examples


def _sha256(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def run_config(dataset_path: str, models: Sequence[str]) -> Dict[str, Any]:
    """Everything a reader needs to know what produced these numbers."""
    import platform

    return {
        "schema": "decision-models-focus/1",
        "dataset_sha256": _sha256(dataset_path),
        "dataset_path": os.path.relpath(dataset_path, os.path.dirname(HERE)),
        "models": list(models),
        "laya_version": getattr(laya, "__version__", "unknown"),
        "openthai_model": DEFAULT_MODEL_PATH,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def run_focused(
    models: Sequence[str] = DEFAULT_MODELS,
    items_path: str = FOCUSED_ITEMS,
    limit: Optional[int] = None,
    on_error: str = "skip",
    runner: Optional[DecisionRunner] = None,
) -> EvalReport:
    """Score every backend on the focused bilingual set."""
    items = load_items(items_path)
    dataset = Dataset(expand(items, models, limit=limit))
    runner = runner or DecisionRunner.with_defaults(release_between_models=True)
    config = run_config(items_path, models)
    config["on_error"] = on_error
    config["n_items"] = len(dataset)
    report = evaluate(runner, dataset, batch_size=None, on_error=on_error, config=config)
    report.config = dict(report.config, routing=runner.routing_log)
    return report


def run_dataset(
    dataset_path: str,
    models: Sequence[str] = DEFAULT_MODELS,
    on_error: str = "skip",
    config_extra: Optional[Dict[str, Any]] = None,
    runner: Optional[DecisionRunner] = None,
) -> EvalReport:
    """Score every backend on a dataset file already in ``laya.evals`` JSONL form.

    Used by the public-benchmark replication, whose rows are built by
    :mod:`decision_models.datasets` rather than authored by hand.
    """
    dataset = Dataset.from_jsonl(dataset_path)
    runner = runner or DecisionRunner.with_defaults(release_between_models=True)
    config = run_config(dataset_path, models)
    config.update(config_extra or {})
    config["n_items"] = len(dataset)
    config["on_error"] = on_error
    report = evaluate(runner, dataset, batch_size=None, on_error=on_error, config=config)
    report.config = dict(report.config, routing=runner.routing_log)
    return report


def save_report(report: EvalReport, path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report.to_json(), handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")
    return path


def load_report(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def errored_count(report: EvalReport) -> int:
    return len(report.config.get("errored") or [])


def expand_to_file(items_path: str, out_path: str, models: Sequence[str] = DEFAULT_MODELS) -> str:
    """Write the expanded dataset, so a run can be inspected before it is scored."""
    examples = expand(load_items(items_path), models)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        for example in examples:
            handle.write(json.dumps({
                "state": example.state,
                "questions": example.questions,
                "expected": example.expected,
                "tags": list(example.tags),
                "language": example.language,
                "model": example.model,
            }, ensure_ascii=False) + "\n")
    return out_path
