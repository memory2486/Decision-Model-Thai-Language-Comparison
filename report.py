"""Turn a stored ``laya.evals`` report into the comparison document.

The metric *math* is not reimplemented here: ``ece``, ``brier``, ``aurc``,
``selective_accuracy`` and the per-type evaluators are imported from
``laya.evals``, so every number below is the same function the harness ran, only
re-cut along dimensions the harness does not pre-slice (model x language, option
count, item family). What this module adds is the cross-cutting that the report
is *for*: where the two models disagree, how much the two confidence scales
diverge, and which model wins in which language.
"""

from __future__ import annotations

import os
import statistics
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from laya.evals import (
    SELECTIVE_COVERAGES,
    ChoiceAccuracy,
    NoulAccuracy,
    ScoreMAE,
    aurc,
    brier,
    ece,
    selective_accuracy,
)


from .confidence import (
    ANSWER_FIELDS,
    confidence_of,
    confidence_scale_report,
    gate,
    threshold_flip_report,
)

#: Default tolerance for treating a `score` answer as correct when computing a
#: single headline accuracy. `ScoreMAE` is reported alongside it, so the
#: tolerance is never the only view of score quality.
SCORE_TOLERANCE = 0.5

#: Option-count buckets for the cardinality analysis.
BUCKETS = ((2, 2), (3, 5), (6, 20), (21, 10 ** 9))


def bucket_of(n_options: Optional[int]) -> str:
    if not n_options:
        return "unknown"
    for low, high in BUCKETS:
        if low <= n_options <= high:
            return "%d-%d" % (low, high) if high < 10 ** 9 else "%d+" % low
    return "unknown"


def n_options_of(case: Mapping[str, Any]) -> Optional[int]:
    """How many options the question offered, read back off the answer.

    The harness's case records carry the answer but not the question, so the
    option count is recovered from the probability vector -- which is also the
    honest source, since it is the width the model actually scored over.
    """
    answer = case.get("answer") or {}
    if answer.get("type") == "noul":
        return 2
    probabilities = answer.get("probabilities")
    if isinstance(probabilities, Mapping):
        return len(probabilities)
    if isinstance(probabilities, (list, tuple)):
        return len(probabilities)
    return None


def _percentiles(values: Sequence[float]) -> tuple:
    ordered = sorted(values)
    n = len(ordered)
    rank = (95 * n + 99) // 100
    return float(statistics.median(ordered)), float(ordered[rank - 1])


def task_correct(case: Mapping[str, Any], tolerance: float = SCORE_TOLERANCE) -> Optional[bool]:
    """One comparable correctness verdict for every question type.

    ``choice`` and ``noul`` come from the harness's own ``correct``. ``score``
    has no boolean verdict in the harness -- ``_correct`` returns ``None`` -- so
    it is called correct when it lands within ``tolerance`` of the labelled
    level. Making this explicit is the point: a headline accuracy that silently
    dropped every score row would flatter whichever model is worse at scoring.
    """
    if case.get("correct") is not None:
        return bool(case["correct"])
    answer = case.get("answer") or {}
    if answer.get("type") == "score":
        expected = case.get("expected")
        actual = answer.get("score")
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            return abs(float(actual) - float(expected)) <= tolerance
    return None


def aggregate(cases: Sequence[Mapping[str, Any]], tolerance: float = SCORE_TOLERANCE) -> Dict[str, float]:
    """Every metric this report shows, for one set of cases."""
    out: Dict[str, Any] = {"n": len(cases)}
    typed = {ChoiceAccuracy().name: [], NoulAccuracy().name: [], ScoreMAE().name: []}
    for case in cases:
        answer, expected = case.get("answer") or {}, case.get("expected")
        for evaluator in (ChoiceAccuracy(), NoulAccuracy(), ScoreMAE()):
            value = evaluator.score(answer, expected)
            if value is not None:
                typed[evaluator.name].append(value)
    for name, values in typed.items():
        if values:
            out[name] = float(statistics.fmean(values))

    verdicts = [task_correct(case, tolerance) for case in cases]
    verdicts = [v for v in verdicts if v is not None]
    if verdicts:
        out["task_accuracy"] = sum(1 for v in verdicts if v) / len(verdicts)
        out["n_scored"] = len(verdicts)

    # ECE / Brier / AURC need a boolean correctness and a confidence, so they
    # span choice and noul only -- `laya.evals._correct` is None for score.
    pairs = [(confidence_of(case, "answer_confidence"), case.get("correct")) for case in cases]
    pairs = [(c, bool(k)) for c, k in pairs if c is not None and k is not None]
    if pairs:
        confs = [p[0] for p in pairs]
        corrs = [p[1] for p in pairs]
        for name, value in (
            ("ece", ece(confs, corrs)),
            ("brier", brier(confs, corrs)),
            ("aurc", aurc(confs, corrs)),
            *[("selective_accuracy@%d" % round(cov * 100), selective_accuracy(confs, corrs, cov))
              for cov in SELECTIVE_COVERAGES],
        ):
            if value is not None and value == value:
                out[name] = float(value)
        out["n_calibration"] = len(pairs)
        out["accuracy_when_delegated"] = sum(1 for c in corrs if c) / len(corrs)

    for field in ANSWER_FIELDS:
        values = [v for v in (confidence_of(c, field) for c in cases) if v is not None]
        if values:
            out["mean_" + field] = float(statistics.fmean(values))

    # Share of cases whose routing decision depends on which confidence field
    # is read. This is the count that turns the scale mismatch into a risk.
    flippable = [(confidence_of(c, "answer_confidence"), confidence_of(c, "confidence")) for c in cases]
    flippable = [(a, b) for a, b in flippable if a is not None and b is not None]
    if flippable:
        flips = sum(1 for a, b in flippable if gate(a) != gate(b))
        out["gate_flip_rate_at_%g" % 0.8] = flips / len(flippable)

    options = [n_options_of(c) for c in cases]
    options = [n for n in options if n]
    if options:
        out["mean_options"] = float(statistics.fmean(options))
        out["mean_chance"] = float(statistics.fmean([1.0 / n for n in options]))

    latencies = [float((c.get("answer") or {}).get("_latency_ms")) for c in cases
                 if isinstance((c.get("answer") or {}).get("_latency_ms"), (int, float))]
    if latencies:
        out["latency_p50_ms"], out["latency_p95_ms"] = _percentiles(latencies)
    return out


def group(cases: Iterable[Mapping[str, Any]], key_fn) -> Dict[str, List[Mapping[str, Any]]]:
    out: Dict[str, List[Mapping[str, Any]]] = {}
    for case in cases:
        out.setdefault(str(key_fn(case)), []).append(case)
    return out


def cross(cases: Sequence[Mapping[str, Any]], *key_fns) -> Dict[tuple, Dict[str, float]]:
    """Aggregate over a tuple key, which the harness's one-dimension slices cannot express."""
    out: Dict[tuple, Dict[str, float]] = {}
    for case in cases:
        out.setdefault(tuple(fn(case) for fn in key_fns), []).append(case)  # type: ignore[arg-type]
    return {key: aggregate(value) for key, value in out.items()}  # type: ignore[arg-type]


# --------------------------------------------------------------------- rendering

def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        if value != value:
            return "-"
        # Counts read as counts: `n=90`, not `n=90.000`.
        if float(value).is_integer() and abs(value) >= 1:
            return str(int(value))
        return ("%%.%df" % digits) % value
    return str(value)


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(cell) for cell in row) + " |")
    return lines


METRIC_COLUMNS = (
    ("task_accuracy", "acc"),
    ("choice_accuracy", "choice"),
    ("noul_accuracy", "noul"),
    ("score_mae", "score_MAE"),
    ("ece", "ECE"),
    ("aurc", "AURC"),
    ("selective_accuracy@80", "sel@80"),
    ("mean_answer_confidence", "mean max-p"),
    ("mean_confidence", "mean entropy"),
)


def _metric_row(label: str, metrics: Mapping[str, Any]) -> List[Any]:
    return [label, metrics.get("n"), metrics.get("n_scored")] + [metrics.get(name) for name, _ in METRIC_COLUMNS]


def render(report: Mapping[str, Any], title: str = "Decision-model comparison") -> str:
    """Render the full markdown report from a stored evaluation JSON."""
    cases: List[Mapping[str, Any]] = list(report.get("cases") or [])
    config: Mapping[str, Any] = report.get("config") or {}
    models = sorted({str(c.get("model")) for c in cases})
    languages = sorted({str(c.get("language")) for c in cases if c.get("language")})
    errored = config.get("errored") or []

    lines: List[str] = ["# %s" % title, ""]
    lines.append("Scored by `laya.evals` (`%s`), the same harness Laya's own "
                 "benchmarks use, with one adapter making OpenThai-SystemOne speak its "
                 "runner contract. Metrics, metric math and calibration numbers therefore "
                 "come from one implementation, not two." % config.get("laya_version", "unknown"))
    lines.append("")

    lines += ["## Run identity", ""]
    lines += _table(["key", "value"], [[k, config.get(k)] for k in (
        "schema", "dataset_path", "dataset_sha256", "n_items", "models", "on_error",
        "laya_version", "openthai_model", "python", "platform",
    ) if config.get(k) is not None])
    lines.append("")
    if errored:
        lines += ["**%d rows errored** during the run; each is listed in "
                  "`config.errored` and the results must be read with that in mind." % len(errored), ""]
    else:
        lines.append("No rows errored: every backend answered every item it was asked.")
        lines.append("")

    lines += ["## Overall", ""]
    lines.append("`acc` is the headline: choice and noul from the harness's own verdict, "
                 "score counted correct within %.1f of the labelled level. `ECE`/`AURC`/`sel@80` "
                 "span choice and noul only, because a `score` answer has no boolean verdict."
                 % SCORE_TOLERANCE)
    lines.append("")
    lines += _table(["model", "n", "n scored"] + [label for _, label in METRIC_COLUMNS],
                    [_metric_row(model, aggregate([c for c in cases if str(c.get("model")) == model]))
                     for model in models])
    lines.append("")

    lines += ["## By language", ""]
    lines.append("The headline table. `chance` is the mean 1/options over the group, so a "
                 "reading near chance is a model that is guessing at this width.")
    lines.append("")
    rows = []
    for model in models:
        for lang in languages:
            subset = [c for c in cases if str(c.get("model")) == model and c.get("language") == lang]
            if not subset:
                continue
            metrics = aggregate(subset)
            rows.append([model, lang] + _metric_row("", metrics)[1:] + [metrics.get("mean_chance")])
    lines += _table(["model", "lang", "n", "n scored"] + [label for _, label in METRIC_COLUMNS] + ["chance"], rows)
    lines.append("")

    lines += ["## By language and question family", ""]
    family_rows = []
    for (model, lang, family), metrics in sorted(cross(
        cases,
        lambda c: c.get("model"),
        lambda c: c.get("language") or "-",
        lambda c: (c.get("tags") or ["-"])[1] if len(c.get("tags") or []) > 1 else "-",
    ).items()):
        family_rows.append([model, lang, family, metrics.get("n"), metrics.get("task_accuracy"),
                            metrics.get("choice_accuracy"), metrics.get("noul_accuracy"),
                            metrics.get("score_mae"), metrics.get("mean_options")])
    lines += _table(["model", "lang", "family", "n", "acc", "choice", "noul", "score_MAE", "mean opts"],
                    family_rows)
    lines.append("")

    lines += ["## By option count", ""]
    lines.append("Laya splits its option budget (`head_max_len`) across the options, so accuracy "
                 "is expected to fall as the option count rises. OpenThai-SystemOne supports up to "
                 "255 options and auto-enables order-invariant averaging above 10.")
    lines.append("")
    bucket_rows = []
    for (model, bucket), metrics in sorted(cross(
        cases, lambda c: c.get("model"), lambda c: bucket_of(n_options_of(c))
    ).items()):
        bucket_rows.append([model, bucket, metrics.get("n"), metrics.get("task_accuracy"),
                            metrics.get("choice_accuracy"), metrics.get("mean_chance"),
                            metrics.get("latency_p50_ms"), metrics.get("latency_p95_ms")])
    lines += _table(["model", "options", "n", "acc", "choice", "chance", "p50 ms", "p95 ms"], bucket_rows)
    lines.append("")

    lines += ["## Latency", ""]
    lines.append("Measured on this machine, per backend call, for one question set over one state. "
                 "Published figures for either model come from other hardware and are not "
                 "reproduced here.")
    lines.append("")
    latency_rows = []
    for model in models:
        subset = [c for c in cases if str(c.get("model")) == model]
        for lang in languages + [None]:
            group_cases = [c for c in subset if (lang is None or c.get("language") == lang)]
            if not group_cases:
                continue
            metrics = aggregate(group_cases)
            latency_rows.append([model, lang or "all", metrics.get("n"),
                                 metrics.get("latency_p50_ms"), metrics.get("latency_p95_ms")])
    lines += _table(["model", "lang", "n", "p50 ms", "p95 ms"], latency_rows)
    lines.append("")

    lines += ["## Confidence is two different numbers", ""]
    lines.append("Both models expose a field named `confidence`, and in both it is "
                 "`1 - H(p)/log(k)` (entropy) -- the `native entropy` column below checks that "
                 "claim rather than asserting it, and should equal `mean entropy` exactly.")
    lines.append("")
    lines.append("Laya *additionally* exposes `answer_confidence`, the only field its "
                 "`min_confidence` gate and its calibration figures are defined against. It is "
                 "`max(p)` after temperature scaling, **not** the raw argmax probability: the "
                 "`native max-p` column sits about 0.15 below the computed one because it "
                 "carries Laya's temperature correction, and one shipped question shape was "
                 "rejected as invalid at load time and fell back to an uncalibrated value. "
                 "The comparison therefore computes raw `max(p)` here, identically for both "
                 "models, so the ECE/AURC columns are the same measurement of each; Laya's own "
                 "scaled number is reported for reference and is not what anything is gated on.")
    lines.append("")
    lines.append("OpenThai-SystemOne exposes no max-probability field at all -- it reports only "
                 "the entropy quantity, plus an `abstain` slot Laya's choice answer does not "
                 "have.")
    lines.append("")
    scale = confidence_scale_report(cases)
    lines += _table(["model", "n", "mean max-p", "mean entropy", "native entropy",
                     "native max-p", "max-p minus entropy"],
                    [[model, values["n"], values["mean_answer_confidence"],
                      values["mean_confidence"], values["mean_native_confidence"],
                      values["mean_native_answer_confidence"], values["mean_gap_answer_minus_entropy"]]
                     for model, values in sorted(scale.items())])
    lines.append("")

    flips = threshold_flip_report(cases)
    lines += ["### Routing decisions that hinge on which field is read", ""]
    lines.append("Route_gate gates at `DELEGATION_FLOOR = 0.8`. Reading `max(p)` where it exists "
                 "and `1 - H/log k` where it does not changes the routing action on "
                 "**%s of %s** comparable cases (%.1f%%)."
                 % (flips["flips"], flips["cases_considered"],
                    100 * (flips["flip_rate"] or 0)))
    lines.append("")
    if flips["examples"]:
        lines += _table(["qid", "model", "lang", "max-p", "entropy", "correct"],
                        [[e["qid"], e["model"], e["language"], e["answer_confidence"],
                          e["confidence"], e["correct"]] for e in flips["examples"]])
        lines.append("")

    lines += ["## Where the models disagree", ""]
    lines.append("The highest-value items for a human to look at, and the natural place to "
                 "consider routing to an escalation path.")
    lines.append("")
    # Keyed by language as well as item: an item is a bilingual pair, so keying
    # on (item, qid) alone lets the Thai row overwrite the English one and
    # prints one language's answer under the other's expected value.
    by_item: Dict[tuple, Dict[str, Mapping[str, Any]]] = {}
    for case in cases:
        tags = case.get("tags") or []
        item_id = tags[0] if tags else str(case.get("qid"))
        key = (item_id, case.get("qid"), case.get("language"))
        by_item.setdefault(key, {})[str(case.get("model"))] = case
    disagreement_rows = []
    for (item_id, qid, language), per_model in sorted(by_item.items(), key=lambda kv: tuple(str(p) for p in kv[0])):
        verdicts = {m: task_correct(c) for m, c in per_model.items()}
        distinct = {v for v in verdicts.values() if v is not None}
        if len(distinct) > 1:
            row: List[Any] = [item_id, language, qid]
            for model in models:
                case = per_model.get(model)
                answer = (case or {}).get("answer") or {}
                row.append(answer.get("choice") if answer.get("choice") is not None
                           else answer.get("score") if answer.get("score") is not None
                           else answer.get("noul"))
            row.append(next(iter(per_model.values())).get("expected"))
            disagreement_rows.append(row)
    if disagreement_rows:
        lines += _table(["item", "lang", "question"] + models + ["expected"], disagreement_rows)
    else:
        lines.append("None: every backend agreed on correctness for every item.")
    lines.append("")

    lines += ["## Recommendation", ""]
    verdict = recommend(cases, models, languages)
    for paragraph in verdict["narrative"]:
        lines.append(paragraph)
        lines.append("")
    if verdict["table"]:
        lines += _table(["language", "best", "acc", "runner-up", "acc", "margin"], verdict["table"])
        lines.append("")

    lines += ["## Limitations", ""]
    for note in limitations(cases, config):
        lines.append("- " + note)
    lines.append("")
    return "\n".join(lines)


def recommend(cases: Sequence[Mapping[str, Any]], models: Sequence[str],
              languages: Sequence[str]) -> Dict[str, Any]:
    """Pick a default per language from the measured accuracy, with the margin stated."""
    table = []
    narrative: List[str] = []
    winners: Dict[str, str] = {}
    for lang in languages:
        scored = []
        for model in models:
            subset = [c for c in cases if str(c.get("model")) == model and c.get("language") == lang]
            metrics = aggregate(subset)
            if metrics.get("task_accuracy") is not None:
                scored.append((model, metrics["task_accuracy"], metrics.get("n_scored") or 0))
        scored.sort(key=lambda item: item[1], reverse=True)
        if not scored:
            continue
        best, best_acc, best_n = scored[0]
        winners[lang] = best
        if len(scored) > 1:
            second, second_acc, _ = scored[1]
            table.append([lang, best, best_acc, second, second_acc, best_acc - second_acc])
        else:
            table.append([lang, best, best_acc, None, None, None])

    if winners:
        pairs = ", ".join("%s -> `%s`" % (lang, model) for lang, model in sorted(winners.items()))
        narrative.append("Measured winner per language: %s." % pairs)
    if len(set(winners.values())) > 1:
        narrative.append("The winner is not the same in every language, so a single default "
                         "would knowingly lose accuracy in at least one of them; the routing "
                         "policy should choose by language.")
    elif winners:
        only = next(iter(set(winners.values())))
        narrative.append("One model wins in every language measured, so the routing policy can "
                         "use `%s` as a single default and keep the others as fallbacks rather "
                         "than branching on language." % only)

        # Accuracy is not the only axis, and the losing model can still win on time.
        latency = []
        for model in sorted({str(c.get("model")) for c in cases}):
            metrics = aggregate([c for c in cases if str(c.get("model")) == model])
            p50 = metrics.get("latency_p50_ms")
            if p50 is not None:
                latency.append((model, p50, metrics.get("task_accuracy")))
        if latency:
            fastest = min(latency, key=lambda item: item[1])
            chosen = next((item for item in latency if item[0] == only), None)
            if chosen and fastest[0] != only and fastest[1] > 0:
                narrative.append("That default is not the fastest: `%s` answers in %.0f ms p50 "
                                 "against `%s` at %.0f ms (%.1fx), for %.3f vs %.3f accuracy. "
                                 "A latency-bound caller should trade the accuracy deliberately "
                                 "rather than inherit this default."
                                 % (fastest[0], fastest[1], only, chosen[1],
                                    chosen[1] / fastest[1], fastest[2] or 0.0, chosen[2] or 0.0))
    return {"table": table, "narrative": narrative, "winners": winners}


def limitations(cases: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> List[str]:
    notes: List[str] = []
    n = len(cases)
    notes.append("Sample size is %d scored rows; a difference of a few points is not "
                 "distinguishable from noise at this size, and per-cell slices are smaller still." % n)
    notes.append("ECE here spans choice and noul only (a `score` answer has no boolean verdict). "
                 "Neither model's shipped numbers are used: Laya's own card says its base "
                 "checkpoint ships over-confident and needs temperature fitting, and at load time "
                 "this run reported invalid shipped temperatures for at least one question shape. "
                 "The ECE figures are therefore pre-fitting, on purpose.")
    notes.append("Latency is one measurement of one process on one machine, and includes the "
                 "Runner dispatch path; treat it as a magnitude, not a benchmark.")
    notes.append("Expectations were inherited from the source material for the routing and triage "
                 "families rather than re-authored; where a label is arguable, the disagreement "
                 "table is the place that shows it.")
    kept = config.get("routing") or []
    if kept:
        distinct = sorted({(r.get("requested"), r.get("answered_by")) for r in kept})
        notes.append("Which checkpoint actually answered (requested -> answered): %s."
                     % "; ".join("%s -> %s" % pair for pair in distinct))
    return notes


def merge_reports(reports: Sequence[Mapping[str, Any]], extra_config: Optional[Mapping[str, Any]] = None,
                  title_models: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Combine per-backend reports into one, recomputing every aggregate from the cases.

    Needed because four checkpoints do not fit one 8 GB card at once: the run is
    executed as one process per backend and merged here. Recomputing from
    ``cases`` rather than averaging the per-file metrics is what keeps the merge
    honest -- a mean of means is not the mean, and the option-count and
    model x language cuts are not present in either input file.
    """
    cases: List[Mapping[str, Any]] = []
    config: Dict[str, Any] = {}
    errored: List[Any] = []
    sources: List[str] = []
    for report in reports:
        cases.extend(report.get("cases") or [])
        errored.extend((report.get("config") or {}).get("errored") or [])
        sources.append((report.get("config") or {}).get("dataset_path"))
        for key, value in (report.get("config") or {}).items():
            if key in ("errored", "routing", "n_items"):
                continue
            if key == "models":
                config.setdefault("models", [])
                for model in (value or []):
                    if model not in config["models"]:
                        config["models"].append(model)
                continue
            config.setdefault(key, value)
    if title_models is not None:
        config["models"] = list(title_models)
    config["n_items"] = len(cases)
    config["merged_from"] = sources
    if errored:
        config["errored"] = errored
    config.update(extra_config or {})

    merged = {"config": config, "cases": cases}
    merged["overall"] = aggregate(cases)
    slices: Dict[str, Dict[str, Dict[str, float]]] = {}
    for dimension, key_fn in (
        ("model", lambda c: c.get("model")),
        ("language", lambda c: c.get("language")),
        ("qid", lambda c: c.get("qid")),
    ):
        grouped = group(cases, key_fn)
        if grouped:
            slices[dimension] = {key: aggregate(value) for key, value in grouped.items()}
    tag_groups: Dict[str, List[Mapping[str, Any]]] = {}
    for case in cases:
        for tag in (case.get("tags") or []):
            tag_groups.setdefault(str(tag), []).append(case)
    if tag_groups:
        slices["tag"] = {key: aggregate(value) for key, value in tag_groups.items()}
    merged["slices"] = slices
    return merged


def write_markdown(report: Mapping[str, Any], path: str, title: str = "Decision-model comparison") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = render(report, title=title)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path
