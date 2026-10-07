"""Command line for the decision-model harness.

    python -m decision_models.cli build        # regenerate the focused item file
    python -m decision_models.cli bench        # score every backend, write report.md
    python -m decision_models.cli bench --limit 4          # smoke run
    python -m decision_models.cli report       # re-render from stored results
    python -m decision_models.cli baseline     # freeze the current run
    python -m decision_models.cli gate         # fail if a re-run regressed
    python -m decision_models.cli serve        # language-aware dispatcher
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Sequence

from . import bench, report as report_mod
from .runners import DEFAULT_MODEL

HERE = os.path.dirname(os.path.abspath(__file__))

FOCUSED_RESULT = os.path.join(bench.RESULTS, "focused.json")
PUBLIC_RESULT = os.path.join(bench.RESULTS, "public.json")
FOCUSED_MD = os.path.join(HERE, "report.md")
PUBLIC_MD = os.path.join(HERE, "report_public.md")
FOCUSED_BASELINE = os.path.join(bench.BASELINES, "focused.json")


def _models(value: str) -> List[str]:
    return [m.strip() for m in value.split(",") if m.strip()]


def cmd_build(args: argparse.Namespace) -> int:
    from .tools.build_focused import build
    import json as _json

    rows = build()
    out = args.out or bench.FOCUSED_ITEMS
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(_json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")
    print("wrote %d rows to %s" % (len(rows), out))
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    models = _models(args.models) if args.models else list(bench.DEFAULT_MODELS)
    print("scoring %d backends: %s" % (len(models), ", ".join(models)))
    if args.split and len(models) > 1:
        return _bench_split(args, models)
    result = bench.run_focused(models=models, limit=args.limit, on_error=args.on_error)
    return _finish(result, args)


def _bench_split(args: argparse.Namespace, models: List[str]) -> int:
    """Score one backend per subprocess, then merge.

    Four checkpoints do not fit an 8 GB card simultaneously, and Laya keeps
    module-level caches that do not release on ``unload()``, so swapping
    backends inside one process ends it without a traceback. One process per
    backend is also checkpointed: a backend that fails leaves the others'
    results on disk.
    """
    import subprocess

    partials: List[str] = []
    for model in models:
        out = os.path.join(bench.RESULTS, "partial_%s.json" % model.replace("/", "_"))
        cmd = [sys.executable, "-m", "decision_models.cli", "bench",
               "--models", model, "--no-split", "--out", out,
               "--report-out", os.path.join(bench.RESULTS, "partial_%s.md" % model)]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        cmd += ["--on-error", args.on_error]
        print("  -> %s" % model, flush=True)
        completed = subprocess.run(cmd, cwd=os.path.dirname(HERE))
        if completed.returncode != 0:
            print("backend %s failed with exit %d; continuing with the rest"
                  % (model, completed.returncode), file=sys.stderr)
            if not os.path.exists(out):
                continue
        partials.append(out)
    if not partials:
        print("every backend failed", file=sys.stderr)
        return 1
    merged = report_mod.merge_reports([bench.load_report(p) for p in partials], title_models=models)
    merged["config"]["schema"] = "decision-models-focus/1"
    path = args.out or FOCUSED_RESULT
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(merged, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")
    print("merged %d report(s) into %s" % (len(partials), path))
    return _finish(None, args, merged=merged, path=path)


def _finish(result, args: argparse.Namespace, merged=None, path: Optional[str] = None) -> int:
    if merged is None:
        path = bench.save_report(result, args.out or FOCUSED_RESULT)
        merged = result.to_json()
        errors = bench.errored_count(result)
    else:
        errors = len(merged.get("config", {}).get("errored") or [])
    print("wrote %s" % path)
    cases = merged.get("cases") or []
    print("rows: %d | errored: %d" % (len(cases), errors))
    for model in sorted({str(c.get("model")) for c in cases}):
        metrics = report_mod.aggregate([c for c in cases if str(c.get("model")) == model])
        print("  %-12s n=%-4s acc=%-7s choice=%-7s noul=%-7s score_mae=%-6s ece=%-6s p50ms=%s" % (
            model, metrics.get("n"), _round(metrics.get("task_accuracy")),
            _round(metrics.get("choice_accuracy")), _round(metrics.get("noul_accuracy")),
            _round(metrics.get("score_mae")), _round(metrics.get("ece")),
            _round(metrics.get("latency_p50_ms"))))
    report_path = report_mod.write_markdown(merged, args.report_out or FOCUSED_MD)
    print("wrote %s" % report_path)
    if errors:
        print("ERROR: %d rows errored; see config.errored in %s" % (errors, path), file=sys.stderr)
        return 1
    return 0


def _round(value: Any) -> str:
    return "-" if value is None else ("%.3f" % value)


def cmd_report(args: argparse.Namespace) -> int:
    source = args.input or FOCUSED_RESULT
    data = bench.load_report(source)
    out = report_mod.write_markdown(data, args.out or FOCUSED_MD, title=args.title)
    print("wrote %s" % out)
    return 0


def cmd_baseline(args: argparse.Namespace) -> int:
    source = args.input or FOCUSED_RESULT
    data = bench.load_report(source)
    os.makedirs(os.path.dirname(FOCUSED_BASELINE), exist_ok=True)
    with open(FOCUSED_BASELINE, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")
    print("baseline written to %s (%d metrics)" % (FOCUSED_BASELINE, len(data.get("overall") or {})))
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    """Fail when a re-run drifted from the frozen baseline beyond tolerance."""
    from laya.evals import EvalReport

    from .confidence import DELEGATION_FLOOR

    baseline = bench.load_report(args.baseline or FOCUSED_BASELINE)
    current = bench.load_report(args.input or FOCUSED_RESULT)
    report = EvalReport(**{k: current.get(k, {} if k != "cases" else [])
                           for k in ("config", "overall", "slices", "cases")})
    report.overall = current.get("overall") or {}

    ok, reasons = report.comparable_to(baseline)
    if not ok:
        print("REFUSED: this run is not the same measurement as the baseline:", file=sys.stderr)
        for reason in reasons:
            print("  - %s" % reason, file=sys.stderr)
        return 2

    # Accuracy and calibration have tolerances (they are measurements); latency
    # does not, because it is timing noise rather than quality.
    tolerances = dict(args.tolerance)
    tolerances.setdefault("ece", 0.05)
    tolerances.setdefault("aurc", 0.05)
    tolerances.setdefault("task_accuracy", 0.05)
    tolerances.setdefault("choice_accuracy", 0.05)
    tolerances.setdefault("noul_accuracy", 0.05)
    tolerances.setdefault("score_mae", 0.10)
    tolerances.setdefault("gate_flip_rate@%g" % DELEGATION_FLOOR, 0.05)

    try:
        deltas = report_mod_assert(report, baseline, tolerances)
    except AssertionError as exc:
        print("REGRESSED: %s" % exc, file=sys.stderr)
        return 1
    print("gate passed (%d metrics compared)" % len(deltas))
    return 0


def report_mod_assert(report, baseline, tolerances):
    from laya.evals import assert_regression

    return assert_regression(report, baseline, tolerances)


def cmd_serve(args: argparse.Namespace) -> int:
    from .serve import create_app, parse_policy

    import uvicorn

    policy = parse_policy(args.policy)
    host = args.host
    port = args.port
    print("policy: %s" % policy)
    print("serving on http://%s:%d/v1/systemone" % (host, port))
    uvicorn.run(create_app(policy=policy), host=host, port=port)
    return 0


def cmd_expand(args: argparse.Namespace) -> int:
    models = _models(args.models) if args.models else list(bench.DEFAULT_MODELS)
    out = args.out or os.path.join(bench.RESULTS, "focused_expanded.jsonl")
    path = bench.expand_to_file(bench.FOCUSED_ITEMS, out, models=models)
    print("wrote %s" % path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="decision_models", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="regenerate the focused item file")
    p.add_argument("--out")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("bench", help="score every backend on the focused set")
    p.add_argument("--models", help="comma-separated backend keys")
    p.add_argument("--limit", type=int, help="cap the number of authored items")
    p.add_argument("--out")
    p.add_argument("--report-out")
    p.add_argument("--on-error", default="skip", choices=["skip", "fail"])
    p.add_argument("--split", dest="split", action="store_true", default=True,
                   help="one subprocess per backend, then merge (default; 4 checkpoints do not "
                        "fit one 8 GB card, and Laya's caches do not release on unload)")
    p.add_argument("--no-split", dest="split", action="store_false")
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("report", help="re-render markdown from stored results")
    p.add_argument("--input")
    p.add_argument("--out")
    p.add_argument("--title", default="Decision-model comparison")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("baseline", help="freeze the current results as the baseline")
    p.add_argument("--input")
    p.set_defaults(func=cmd_baseline)

    p = sub.add_parser("gate", help="fail if a re-run regressed against the baseline")
    p.add_argument("--input")
    p.add_argument("--baseline")
    p.add_argument("--tolerance", action="append", default=[], metavar="METRIC=VALUE")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("serve", help="run the language-aware dispatcher")
    p.add_argument("--host", default=os.environ.get("DECISION_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("DECISION_PORT", "8077")))
    p.add_argument("--policy", help="lang:th=openthai,default=laya-en")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("expand", help="write the expanded per-backend dataset")
    p.add_argument("--models")
    p.add_argument("--out")
    p.set_defaults(func=cmd_expand)
    return parser


def main(argv: Sequence[str] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "gate":
        args.tolerance = [_pair(t) for t in args.tolerance]
    return args.func(args)


def _pair(text: str):
    if "=" not in text:
        raise SystemExit("--tolerance expects METRIC=VALUE, got %r" % text)
    key, value = text.split("=", 1)
    return key.strip(), float(value)


if __name__ == "__main__":
    raise SystemExit(main())
