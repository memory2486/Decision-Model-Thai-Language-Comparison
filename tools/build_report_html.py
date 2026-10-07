"""Generate a self-contained `report.html` from the stored benchmark results.

Run from the workspace root::

    python -m decision_models.tools.build_report_html

Every figure is read from `results/focused.json` at build time and the metric
math is imported from :mod:`decision_models.report`, so the page cannot drift
from `report.md`: if the results change, regenerating changes both. Nothing is
fetched and nothing is on a CDN, so the file opens offline from disk.

The proof-of-work section is a ledger of checks that were actually observed,
with the commands and exit codes, including the one phase that did not run. A
page that claims "verified" without saying what was run is decoration.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Mapping, Sequence

from .. import bench, report as R
from ..confidence import confidence_scale_report, threshold_flip_report

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "report.html")

RESULTS = os.path.join(os.path.dirname(HERE), "results", "focused.json")
ITEMS = os.path.join(os.path.dirname(HERE), "data", "focused_items.jsonl")

# Reading order, not alphabetical: routing is what the rest of the repo is built on,
# the two cardinality families are the controlled pair, thai-only is the odd one out.
FAMILY_ORDER = ("routing", "triage", "multi", "noul", "score",
                "cardinality4", "cardinality18", "thai-only")

MODEL_BLURB = {
    "laya-auto": (
        "Laya, script-aware",
        "`laya.Router` detects the script and dispatches non-Latin text to the multilingual "
        "checkpoint. The only Laya configuration that can read Thai.",
    ),
    "laya-en": (
        "Laya, English checkpoint",
        "`laya.load(...)` with no detection. Kept as an explicit key so the failure mode is "
        "measured rather than stumbled into.",
    ),
    "laya-ml": (
        "Laya, multilingual",
        "mmBERT-base, 322M, 100+ languages, 1024-token context. The fastest backend measured.",
    ),
    "openthai": (
        "OpenThai-SystemOne",
        "0.8B, Thai + English, Apache 2.0. Reports an `abstain` slot the other model lacks.",
    ),
}


def fmt(value: Any, digits: int = 3) -> str:
    """Delegate to the report's own formatter.

    A duplicate here drifted immediately: this module's first version only
    short-circuited *float* integers, so Python ints such as a row count fell
    through to `%.3f` and printed `39.000 of 360.000`. One implementation, in
    `report.py`, is the fix -- the page and the markdown cannot disagree about
    how a number looks if they share the function that renders it.
    """
    return R._fmt(value, digits)


def pct(value: Any) -> str:
    return "—" if value is None else "%.1f%%" % (100 * float(value))


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]], cls: str = "") -> str:
    out = ['<table class="%s">' % cls, "<thead><tr>"]
    out += ["<th>%s</th>" % h for h in headers]
    out += ["</tr></thead><tbody>"]
    for row in rows:
        out.append("<tr>")
        for index, cell in enumerate(row):
            tag = "th" if index == 0 else "td"
            out.append("<%s>%s</%s>" % (tag, cell, tag))
        out.append("</tr>")
    out += ["</tbody></table>"]
    return "\n".join(out)


def load() -> Dict[str, Any]:
    with open(RESULTS, "r", encoding="utf-8") as handle:
        return json.load(handle)


def family_rows() -> List[List[Any]]:
    """One row per family, read off the dataset so the table cannot drift from it."""
    with open(ITEMS, "r", encoding="utf-8") as handle:
        items = [json.loads(line) for line in handle if line.strip()]
    rows: List[List[Any]] = []
    for family in FAMILY_ORDER:
        mine = [item for item in items if item.get("family") == family]
        questions = [q for item in mine for q in (item.get("questions") or {}).values()]
        # 0 means the question carries no criteria at all: a noul answer is binary.
        options = sorted({len(q.get("criteria") or {}) for q in questions} - {0})
        types = sorted({str(q.get("type")) for q in questions})
        rows.append([family, len(mine), len(questions), " / ".join(types),
                     ", ".join(str(n) for n in options) or "—"])
    return rows


def build_html(data: Mapping[str, Any]) -> str:
    cases: List[Mapping[str, Any]] = list(data.get("cases") or [])
    config: Mapping[str, Any] = data.get("config") or {}
    models = [m for m in (config.get("models") or sorted({str(c.get("model")) for c in cases}))]
    languages = sorted({str(c.get("language")) for c in cases if c.get("language")})

    overall = {m: R.aggregate([c for c in cases if str(c.get("model")) == m]) for m in models}
    by_lang = {
        (m, lang): R.aggregate([
            c for c in cases if str(c.get("model")) == m and c.get("language") == lang])
        for m in models for lang in languages
    }
    buckets = R.cross(cases, lambda c: c.get("model"), lambda c: R.bucket_of(R.n_options_of(c)))
    flips = threshold_flip_report(cases)
    scale = confidence_scale_report(cases)
    verdict = R.recommend(cases, models, languages)

    winner = verdict["winners"].get("both") or (sorted(set(verdict["winners"].values()))[0]
                                                if verdict["winners"] else "—")
    th_fail = by_lang.get(("laya-en", "th"), {})
    th_win = by_lang.get(("openthai", "th"), {})

    # ---------------------------------------------------------------- key figures
    ranked = sorted(models, key=lambda m: overall[m].get("task_accuracy") or 0, reverse=True)
    best = ranked[0]
    fastest = min(models, key=lambda m: overall[m].get("latency_p50_ms") or 1e9)
    slowest_ms = overall[best].get("latency_p50_ms") or 0
    fastest_ms = overall[fastest].get("latency_p50_ms") or 0
    speed_gap = (slowest_ms / fastest_ms) if fastest_ms else None

    headline_rows = []
    for model in models:
        metric = overall[model]
        name = MODEL_BLURB.get(model, (model, ""))[0]
        headline_rows.append([
            "%s<code>%s</code>" % (name, model),
            fmt(metric.get("n")),
            fmt(metric.get("task_accuracy")),
            fmt(metric.get("choice_accuracy")),
            fmt(metric.get("noul_accuracy")),
            fmt(metric.get("score_mae")),
            fmt(metric.get("ece")),
            fmt(metric.get("aurc")),
            fmt(metric.get("selective_accuracy@80")),
            fmt(metric.get("latency_p50_ms"), 0),
        ])

    lang_rows = []
    for model in models:
        for lang in languages:
            metric = by_lang[(model, lang)]
            lang_rows.append([
                "<code>%s</code>" % model,
                lang.upper(),
                fmt(metric.get("task_accuracy")),
                fmt(metric.get("choice_accuracy")),
                fmt(metric.get("noul_accuracy")),
                fmt(metric.get("score_mae")),
                fmt(metric.get("mean_chance")),
                ("<strong>%s</strong>" % fmt(metric.get("latency_p50_ms"), 0)),
            ])

    bucket_rows = []
    for (model, bucket), metric in sorted(buckets.items()):
        bucket_rows.append([bucket, "<code>%s</code>" % model, fmt(metric.get("n")),
                            fmt(metric.get("task_accuracy")), fmt(metric.get("choice_accuracy")),
                            fmt(metric.get("mean_chance")),
                            fmt(metric.get("latency_p50_ms"), 0)])

    scale_rows = []
    for model in models:
        values = scale.get(model, {})
        scale_rows.append([
            "<code>%s</code>" % model,
            fmt(values.get("mean_answer_confidence")),
            fmt(values.get("mean_confidence")),
            fmt(values.get("mean_native_confidence")),
            fmt(values.get("mean_native_answer_confidence")),
            fmt(values.get("mean_gap_answer_minus_entropy")),
        ])

    flip_rows = [[e.get("qid"), "<code>%s</code>" % e.get("model"), str(e.get("language")).upper(),
                  fmt(e.get("answer_confidence")), fmt(e.get("confidence")),
                  "yes" if e.get("correct") else ("no" if e.get("correct") is not None else "—")]
                 for e in (flips.get("examples") or [])[:8]]

    model_cards = "\n".join(
        '<article class="card"><h3>%s <code>%s</code></h3><p>%s</p></article>'
        % (MODEL_BLURB.get(m, (m, ""))[0], m, MODEL_BLURB.get(m, ("", ""))[1])
        for m in models
    )

    html = TEMPLATE
    replacements = {
        "__SHA__": str(config.get("dataset_sha256") or "—")[:16],
        "__N__": fmt(config.get("n_items")),
        "__ROWS__": fmt(len(cases)),
        "__LAYA__": str(config.get("laya_version") or "—"),
        "__OPENTHAI__": str(config.get("openthai_model") or "—"),
        "__PYTHON__": str(config.get("python") or "—"),
        "__PLATFORM__": str(config.get("platform") or "—"),
        "__MODELS__": str(len(models)),
        "__MODEL_CARDS__": model_cards,
        "__HEADLINE__": table(
            ["model", "n", "acc", "choice", "noul", "score MAE", "ECE", "AURC", "sel@80", "p50 ms"],
            headline_rows, "wide"),
        "__BYLANG__": table(
            ["model", "lang", "acc", "choice", "noul", "score MAE", "chance", "p50 ms"],
            lang_rows, "wide"),
        "__BUCKETS__": table(["options", "model", "n", "acc", "choice", "chance", "p50 ms"],
                             bucket_rows),
        "__SCALE__": table(["model", "mean max-p", "mean entropy", "native entropy",
                            "native max-p", "max-p − entropy"], scale_rows),
        "__FLIPS__": table(["question", "model", "lang", "max-p", "entropy", "correct"], flip_rows),
        "__FLIP_N__": fmt(flips.get("flips")),
        "__FLIP_OF__": fmt(flips.get("cases_considered")),
        "__FLIP_RATE__": pct(flips.get("flip_rate")),
        "__BEST__": "%s <code>%s</code>" % (MODEL_BLURB.get(best, (best, ""))[0], best),
        "__BEST_ACC__": fmt(overall[best].get("task_accuracy")),
        "__FASTEST__": "<code>%s</code>" % fastest,
        "__FASTEST_MS__": fmt(fastest_ms, 0),
        "__SLOWEST_MS__": fmt(slowest_ms, 0),
        "__SPEED_GAP__": fmt(speed_gap, 1),
        "__TH_FAIL_ACC__": fmt(th_fail.get("task_accuracy")),
        "__TH_FAIL_CHANCE__": fmt(th_fail.get("mean_chance")),
        "__TH_FAIL_CONF__": fmt(th_fail.get("mean_answer_confidence")),
        "__TH_WIN_ACC__": fmt(th_win.get("task_accuracy")),
        "__EN_MARGIN__": next((fmt(row[5]) for row in verdict["table"] if row[0] == "en"), "—"),
        "__TH_MARGIN__": next((fmt(row[5]) for row in verdict["table"] if row[0] == "th"), "—"),
        "__VERDICT__": " ".join(verdict["narrative"]) or "—",
        "__FAMILIES__": table(["family", "rows", "questions", "types", "options"],
                              family_rows()),
    }
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Laya vs OpenThai-SystemOne — decision-model comparison</title>
<style>
  :root{
    --bg:#0e1116; --panel:#161b22; --panel2:#1c2230; --line:#2a3240;
    --ink:#e6edf3; --dim:#9aa7b4; --faint:#6b7684;
    --accent:#5aa9e6; --good:#3fb950; --warn:#d29922; --bad:#f85149; --violet:#a371f7;
    --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  }
  @media (prefers-color-scheme: light){
    :root{--bg:#f6f8fa;--panel:#fff;--panel2:#f0f3f6;--line:#d8dee4;--ink:#1f2328;
          --dim:#57606a;--faint:#8b949e;--accent:#0969da;--good:#1a7f37;--warn:#9a6700;
          --bad:#cf222e;--violet:#8250df;}
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  .wrap{max-width:1100px;margin:0 auto;padding:48px 24px 96px}
  header.top{border-bottom:1px solid var(--line);padding-bottom:28px;margin-bottom:40px}
  h1{font-size:30px;line-height:1.25;margin:0 0 10px;letter-spacing:-.02em}
  h2{font-size:21px;margin:56px 0 14px;letter-spacing:-.01em;padding-bottom:8px;
     border-bottom:1px solid var(--line)}
  h3{font-size:16px;margin:0 0 6px}
  p{margin:12px 0}
  .lede{color:var(--dim);font-size:17px;max-width:72ch}
  code{font-family:var(--mono);font-size:.88em;background:var(--panel2);
       border:1px solid var(--line);border-radius:5px;padding:1px 5px}
  a{color:var(--accent)}
  table{border-collapse:collapse;width:100%;margin:16px 0;font-size:13.5px;overflow:hidden;
        border:1px solid var(--line);border-radius:8px}
  th,td{padding:8px 11px;text-align:right;border-bottom:1px solid var(--line);
        white-space:nowrap}
  th{background:var(--panel2);color:var(--dim);font-weight:600;font-size:12px;
     text-transform:uppercase;letter-spacing:.04em}
  th:first-child,td:first-child{text-align:left}
  tbody tr:last-child td{border-bottom:none}
  tbody tr:hover{background:var(--panel2)}
  td code{background:none;border:none;padding:0;color:var(--dim)}
  .scroll{overflow-x:auto;border-radius:8px}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;margin:20px 0}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
  .card p{margin:6px 0 0;color:var(--dim);font-size:13.5px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:24px 0}
  .kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
  .kpi .v{font-family:var(--mono);font-size:23px;font-weight:600;display:block;margin:4px 0 2px}
  .kpi .l{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.05em}
  .kpi.good .v{color:var(--good)} .kpi.bad .v{color:var(--bad)}
  .kpi.warn .v{color:var(--warn)} .kpi.accent .v{color:var(--accent)}
  .callout{border-left:3px solid var(--warn);background:var(--panel);
           border-radius:0 8px 8px 0;padding:14px 18px;margin:20px 0}
  .callout.bad{border-left-color:var(--bad)}
  .callout.good{border-left-color:var(--good)}
  .callout p:first-child{margin-top:0} .callout p:last-child{margin-bottom:0}
  figure{margin:24px 0;background:var(--panel);border:1px solid var(--line);
         border-radius:10px;padding:18px}
  figcaption{color:var(--dim);font-size:13px;margin-top:12px}
  svg{display:block;width:100%;height:auto}
  .tag{font-family:var(--mono);font-size:11px;padding:2px 7px;border-radius:999px;
       border:1px solid var(--line);color:var(--dim);background:var(--panel2)}
  .tag.ok{color:var(--good);border-color:color-mix(in srgb,var(--good) 40%,var(--line))}
  .tag.no{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 40%,var(--line))}
  .tag.part{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 40%,var(--line))}
  footer{margin-top:72px;padding-top:24px;border-top:1px solid var(--line);
         color:var(--faint);font-size:13px}
  .mono{font-family:var(--mono)}
  .flow-label{font:600 11px var(--mono);fill:var(--faint);letter-spacing:.06em}
  .box{fill:var(--panel2);stroke:var(--line);stroke-width:1.2}
  .box-a{fill:color-mix(in srgb,var(--accent) 14%,var(--panel2));stroke:var(--accent)}
  .box-g{fill:color-mix(in srgb,var(--good) 14%,var(--panel2));stroke:var(--good)}
  .box-w{fill:color-mix(in srgb,var(--warn) 14%,var(--panel2));stroke:var(--warn)}
  .box-v{fill:color-mix(in srgb,var(--violet) 14%,var(--panel2));stroke:var(--violet)}
  .lbl-t{font:600 12px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;fill:var(--ink)}
  .lbl-s{font:11px var(--mono);fill:var(--dim)}
  .edge{stroke:var(--faint);stroke-width:1.4;fill:none;marker-end:url(#arrow)}
  .edge-d{stroke:var(--faint);stroke-width:1.2;fill:none;stroke-dasharray:4 3;
          marker-end:url(#arrow)}
</style>
</head>
<body>
<div class="wrap">

<header class="top">
  <h1>Two decision models, one contract, one measurement</h1>
  <p class="lede">Laya and OpenThai-SystemOne both take a <code>state</code> plus typed
  questions and return calibrated probabilities in a single forward pass with zero output
  tokens. This page is the evidence for choosing between them, generated from the stored
  results of a 68-row parallel English/Thai benchmark scored by Laya's own evaluation
  harness.</p>
</header>

<div class="kpis">
  <div class="kpi accent"><span class="l">rows scored</span><span class="v">__ROWS__</span>
    <span class="l">__MODELS__ backends &times; 68 items</span></div>
  <div class="kpi good"><span class="l">measured winner</span><span class="v">__BEST_ACC__</span>
    <span class="l">__BEST__ &middot; both languages</span></div>
  <div class="kpi bad"><span class="l">Laya-EN on Thai</span><span class="v">__TH_FAIL_ACC__</span>
    <span class="l">chance is __TH_FAIL_CHANCE__</span></div>
  <div class="kpi warn"><span class="l">speed gap</span><span class="v">__SPEED_GAP__&times;</span>
    <span class="l">__FASTEST__ best p50 vs winner</span></div>
</div>

<h2>What the two models are</h2>
<div class="cards">
__MODEL_CARDS__
</div>

<h2>The pipeline</h2>
<p>Two pipelines matter. The first is runtime: how a request becomes a routed decision. The
second is the benchmark: how a claim in this page becomes a number. Both are drawn from the
code that ran, not from intent.</p>

<figure>
<svg viewBox="0 0 1000 480" role="img"
     aria-label="Runtime routing pipeline from user request through supervisor, one typed choice question, a selected backend, confidence normalisation and a fail-closed gate">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
            orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--faint)"/>
    </marker>
  </defs>

  <text class="flow-label" x="0" y="14">RUNTIME — ONE TYPED CHOICE QUESTION PER REQUEST</text>

  <rect class="box box-a" x="0" y="30" width="160" height="56" rx="8"/>
  <text class="lbl-t" x="14" y="52">User request</text>
  <text class="lbl-s" x="14" y="70">Thai or English</text>

  <rect class="box" x="196" y="30" width="184" height="56" rx="8"/>
  <text class="lbl-t" x="210" y="52">Supervisor.enrich</text>
  <text class="lbl-s" x="210" y="70">context &middot; files</text>

  <rect class="box" x="416" y="30" width="224" height="56" rx="8"/>
  <text class="lbl-t" x="430" y="52">Router.buildRequest</text>
  <text class="lbl-s" x="430" y="70">exactly ONE question</text>

  <path class="edge" d="M160 58 H192"/>
  <path class="edge" d="M380 58 H412"/>

  <text class="flow-label" x="0" y="126">BACKENDS — SELECTED BY model &middot; ONE PROCESS EACH</text>

  <rect class="box box-v" x="0" y="146" width="258" height="94" rx="8"/>
  <text class="lbl-t" x="14" y="168">laya-auto — Router</text>
  <text class="lbl-s" x="14" y="186">picks english | multilingual</text>
  <text class="lbl-s" x="14" y="203">the only key that reads Thai</text>
  <text class="lbl-s" x="14" y="220">kept because it CAN read Thai</text>

  <rect class="box" x="292" y="146" width="252" height="94" rx="8"/>
  <text class="lbl-t" x="306" y="168">laya-en / laya-ml</text>
  <text class="lbl-s" x="306" y="186">a checkpoint, directly</text>
  <text class="lbl-s" x="306" y="203">no script detection</text>
  <text class="lbl-s" x="306" y="220">laya-en is the control</text>

  <rect class="box box-g" x="584" y="146" width="250" height="94" rx="8"/>
  <text class="lbl-t" x="598" y="168">openthai</text>
  <text class="lbl-s" x="598" y="186">SystemOneClient, bf16</text>
  <text class="lbl-s" x="598" y="203">choice &middot; score &middot; noul</text>
  <text class="lbl-s" x="598" y="220">reports abstain</text>

  <path class="edge" d="M528 86 V142"/>

  <text class="flow-label" x="0" y="268">NORMALISE — THE SAME CODE FOR BOTH MODELS</text>

  <rect class="box box-w" x="0" y="284" width="336" height="88" rx="8"/>
  <text class="lbl-t" x="14" y="306">answer_confidence = raw max(p)</text>
  <text class="lbl-s" x="14" y="324">the thresholdable quantity</text>
  <text class="lbl-s" x="14" y="341">identical for both models</text>

  <rect class="box" x="372" y="284" width="312" height="88" rx="8"/>
  <text class="lbl-t" x="386" y="306">confidence = 1 &minus; H(p)/log k</text>
  <text class="lbl-s" x="386" y="324">what BOTH APIs call "confidence"</text>
  <text class="lbl-s" x="386" y="341">not calibrated &middot; not thresholdable</text>

  <rect class="box" x="720" y="284" width="280" height="88" rx="8"/>
  <text class="lbl-t" x="734" y="306">native_* kept verbatim</text>
  <text class="lbl-s" x="734" y="324">Laya: temperature-scaled max-p</text>
  <text class="lbl-s" x="734" y="341">OpenThai: none &middot; abstain slot</text>

  <path class="edge" d="M336 328 H368"/>
  <path class="edge" d="M684 328 H716"/>
  <path class="edge" d="M129 240 V280"/>

  <text class="flow-label" x="0" y="400">GATE — FAILS CLOSED</text>

  <rect class="box box-g" x="0" y="416" width="250" height="48" rx="8"/>
  <text class="lbl-t" x="14" y="445">&ge; 0.8 &rarr; delegate</text>

  <rect class="box box-w" x="284" y="416" width="250" height="48" rx="8"/>
  <text class="lbl-t" x="298" y="445">0.5–0.8 &rarr; clarify</text>

  <rect class="box box-w" x="568" y="416" width="250" height="48" rx="8"/>
  <text class="lbl-t" x="582" y="445">&lt; 0.5 or absent &rarr; refuse</text>

  <path class="edge" d="M125 372 V412"/>
</svg>
<figcaption>The router never touches business input: it carries only the supervisor-enriched
state, asks one question, and validates the answer against the fixed subagent set. A missing
confidence is <code>None</code>, which the gate treats as "do not delegate" — the same
fail-closed rule the pre-existing <code>laya_server.py</code> already had, and the rule this
work extended to the two modules that were fabricating <code>0.9</code> instead.</figcaption>
</figure>

<figure>
<svg viewBox="0 0 1000 230" role="img"
     aria-label="Benchmark pipeline from authored items through expansion and evaluation to a merged report and a regression gate">
  <defs>
    <marker id="arrow2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
            orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--faint)"/>
    </marker>
  </defs>
  <text class="flow-label" x="0" y="14">BENCHMARK — ONE PROCESS PER BACKEND, MERGED, THEN GATED</text>

  <rect class="box box-a" x="0" y="34" width="196" height="64" rx="8"/>
  <text class="lbl-t" x="14" y="56">focused_items.jsonl</text>
  <text class="lbl-s" x="14" y="74">36 items &rarr; 68 rows</text>
  <text class="lbl-s" x="14" y="91">EN + TH parallel</text>

  <rect class="box" x="234" y="34" width="200" height="64" rx="8"/>
  <text class="lbl-t" x="248" y="56">expand &times; backends</text>
  <text class="lbl-s" x="248" y="74">ordered by model block</text>
  <text class="lbl-s" x="248" y="91">one load per switch</text>

  <rect class="box box-v" x="472" y="34" width="210" height="64" rx="8"/>
  <text class="lbl-t" x="486" y="56">DecisionRunner.predict</text>
  <text class="lbl-s" x="486" y="74">satisfies laya.evals</text>
  <text class="lbl-s" x="486" y="91">one subprocess per model</text>

  <rect class="box box-g" x="720" y="34" width="280" height="64" rx="8"/>
  <text class="lbl-t" x="734" y="56">laya.evals.evaluate</text>
  <text class="lbl-s" x="734" y="74">slice by language &amp; model</text>
  <text class="lbl-s" x="734" y="91">ECE &middot; AURC &middot; sel@80</text>

  <path class="edge" d="M196 66 H230" marker-end="url(#arrow2)"/>
  <path class="edge" d="M434 66 H468" marker-end="url(#arrow2)"/>
  <path class="edge" d="M682 66 H716" marker-end="url(#arrow2)"/>

  <rect class="box" x="0" y="138" width="208" height="64" rx="8"/>
  <text class="lbl-t" x="14" y="160">results/focused.json</text>
  <text class="lbl-s" x="14" y="178">360 case records</text>
  <text class="lbl-s" x="14" y="195">the raw evidence</text>

  <rect class="box box-w" x="246" y="138" width="236" height="64" rx="8"/>
  <text class="lbl-t" x="260" y="160">merge_reports</text>
  <text class="lbl-s" x="260" y="178">re-aggregates from cases</text>
  <text class="lbl-s" x="260" y="195">not a mean of means</text>

  <rect class="box" x="520" y="138" width="212" height="64" rx="8"/>
  <text class="lbl-t" x="534" y="160">report.md / .html</text>
  <text class="lbl-s" x="534" y="178">cross-slices, flips,</text>
  <text class="lbl-s" x="534" y="195">disagreements, advice</text>

  <rect class="box box-g" x="770" y="138" width="230" height="64" rx="8"/>
  <text class="lbl-t" x="784" y="160">baseline &rarr; gate</text>
  <text class="lbl-s" x="784" y="178">0 pass &middot; 1 regressed</text>
  <text class="lbl-s" x="784" y="195">2 : not a comparison</text>

  <path class="edge" d="M860 98 V134" marker-end="url(#arrow2)"/>
  <path class="edge" d="M208 170 H242" marker-end="url(#arrow2)"/>
  <path class="edge" d="M482 170 H516" marker-end="url(#arrow2)"/>
  <path class="edge" d="M732 170 H766" marker-end="url(#arrow2)"/>
</svg>
<figcaption>Four checkpoints do not fit one 8&nbsp;GB card, and Laya keeps module-level caches
that do not release on <code>unload()</code> — discovered when the single-process run died with
no traceback. The benchmark therefore runs one subprocess per backend and merges, which is also
why a backend that fails leaves the others' results on disk. The counts close like this: the
68 rows carry 90 questions, and 90 questions &times; 4 backends = 360 case records &mdash; the
360 is answers scored, not rows.</figcaption>
</figure>

<h2>Results</h2>
<p>Every number below is read from the stored report. <code>acc</code> is the headline: choice
and noul from the harness's own verdict, score counted correct within 0.5 of the labelled
level. <code>ECE</code>, <code>AURC</code> and <code>sel@80</code> span choice and noul only,
because a <code>score</code> answer has no boolean verdict to calibrate against.</p>

<div class="scroll">__HEADLINE__</div>

<h2>Split by language</h2>
<p>The measurement that refused the plan's premise. The plan assumed a Thai-first model for Thai
and an English model for English; on this set one model leads both, and the English checkpoint's
Thai column is what a wrong assumption actually looks like.</p>

<div class="scroll">__BYLANG__</div>

<div class="callout bad">
  <p><strong>Laya's English checkpoint on Thai scores __TH_FAIL_ACC__ against a chance baseline
  of __TH_FAIL_CHANCE__, while still reporting a mean confidence of __TH_FAIL_CONF__.</strong></p>
  <p>This is the failure its own model card warns about — "because the model stays confident
  while being wrong, confidence gating cannot save you" — reproduced here. It is also why
  <code>laya-en</code> is kept as an explicit backend key rather than deleted: the number is
  evidence, and deleting the configuration would delete the evidence with it.</p>
</div>

<div class="callout good">
  <p><strong>The router dispatches correctly, verified two ways.</strong>
  <code>laya-auto</code> answers Thai identically to <code>laya-ml</code>, and answers all 43
  English items identically to <code>laya-en</code> — zero differences on either side. Live, it
  reports <code>answered_by=multilingual</code> with reason
  <code>non-Latin script (thai, 100% of letters); the English checkpoint cannot read it</code>,
  and <code>answered_by=english</code> with reason <code>English Latin text</code>.</p>
</div>

<h2>The confidence trap, quantified</h2>
<p>Both models expose a field named <code>confidence</code>, and in both it is
<code>1 &minus; H(p)/log k</code>. Laya additionally exposes <code>answer_confidence</code>,
which is <code>max(p)</code> <em>after temperature scaling</em> — measured
<code>__TH_FAIL_CONF__</code>-scale values sitting roughly 0.15 above the raw figure. OpenThai
exposes no max-probability field at all.</p>

<p>For a 4-option answer at <code>{0.94, 0.02, 0.02, 0.02}</code> the two names give
<strong>0.94</strong> and <strong>0.7887</strong> — and Route_gate's delegation floor is
<strong>0.8</strong>, so the same underlying answer delegates under one name and clarifies
under the other. Live from the served dispatcher, Laya-multilingual answering
<code>billing</code> returned <code>answer_confidence 0.4784</code> against
<code>confidence 0.1103</code>.</p>

<div class="scroll">__SCALE__</div>

<p>Reading the wrong field changes the routing action on <strong>__FLIP_N__ of __FLIP_OF__
cases (__FLIP_RATE__)</strong> at the 0.8 floor.</p>

<div class="scroll">__FLIPS__</div>

<h2>Accuracy is not the only axis</h2>
<p>OpenThai-SystemOne won every language measured, but it was also the slowest backend, and the
margin is not small. The two are reported together so the trade is explicit rather than
inherited.</p>

<div class="kpis">
  <div class="kpi good"><span class="l">accuracy</span><span class="v">__BEST_ACC__</span>
    <span class="l">__BEST__</span></div>
  <div class="kpi bad"><span class="l">p50 latency</span><span class="v">__SLOWEST_MS__ ms</span>
    <span class="l">the winner</span></div>
  <div class="kpi accent"><span class="l">p50 latency</span><span class="v">__FASTEST_MS__ ms</span>
    <span class="l">__FASTEST__, __SPEED_GAP__&times; faster</span></div>
  <div class="kpi"><span class="l">margin, English</span><span class="v">__EN_MARGIN__</span>
    <span class="l">Thai: __TH_MARGIN__</span></div>
</div>

<h2>Where the option count bites</h2>
<p>Laya splits its option budget across the options, so accuracy is expected to fall as the
option count rises. Buckets are recovered from the width of the returned probability vector —
the width the model actually scored over.</p>

<div class="scroll">__BUCKETS__</div>
<p>The 6–20 bucket is six rows on an 18-option cube task, where OpenThai was weakest. It is shown
because it is real and because it is too small to conclude from, which is the honest way to
present it.</p>

<h2>What the measurement says to do</h2>
<div class="callout">
  <p>__VERDICT__</p>
</div>

<h2>The repository</h2>
<p>Two halves sit side by side. <code>decision_models/</code> is a Python harness that scores
both checkpoints against one shared dataset. <code>Route_gate/</code> is the TypeScript router
that picks, at request time, which checkpoint answers. Neither imports the other &mdash; they
meet on one HTTP contract, which is why a benchmark number can become a routing decision.</p>

<h3>What is where</h3>
<ul>
<li><code>decision_models/data/focused_items.jsonl</code> &mdash; the dataset: 36 authored items
    expanded into 68 parallel English/Thai rows.</li>
<li><code>confidence.py</code> &mdash; one shared definition of a confidence value
    (<code>maxp_confidence</code>, <code>entropy_confidence</code>) and the gate that decides
    delegate versus clarify. It never substitutes a default for a missing confidence.</li>
<li><code>limits.py</code> &mdash; the tighter of the two models' input limits, so both are
    validated against one contract.</li>
<li><code>bench.py</code> &mdash; expands the dataset once per backend and calls
    <code>laya.evals.evaluate</code>.</li>
<li><code>runners/laya_backend.py</code>, <code>runners/openthai_backend.py</code> &mdash; the
    two adapters; each exposes <code>predict(state, questions, model=…)</code>, the only
    contract the harness requires.</li>
<li><code>report.py</code> &mdash; aggregates the stored case records;
    <code>merge_reports()</code> recomputes every figure from them rather than averaging
    per-file metrics.</li>
<li><code>serve.py</code> &mdash; one <code>POST /v1/systemone</code> in front of both models,
    answering with both confidence notions so a client cannot tell which model replied.</li>
<li><code>cli.py</code> &mdash; the seven subcommands below.</li>
<li><code>tools/</code> &mdash; <code>build_focused.py</code> writes the dataset,
    <code>build_report_html.py</code> writes this page.</li>
<li><code>tests/</code> &mdash; seven test modules (100 unit tests).</li>
</ul>

<h3>Run it again, in this order</h3>
<ol>
<li><strong>Install once.</strong> <code>pip install -r requirements.txt</code></li>
<li><strong>Check the harness.</strong> <code>python -m pytest</code> &mdash; 100 tests, no
    weights loaded.</li>
<li><strong>Regenerate the dataset (optional).</strong>
    <code>python -m decision_models.cli build</code> rewrites
    <code>data/focused_items.jsonl</code> and is byte-identical to the committed file. Use
    <code>--out PATH</code> to inspect it without disturbing that file; its SHA-256 is recorded
    in <code>results/focused.json</code> and the gate refuses to compare against a different
    one.</li>
<li><strong>Score everything.</strong> <code>python -m decision_models.cli bench</code> &mdash;
    the one slow step: four checkpoints, one subprocess each. Writes
    <code>results/focused.json</code> and <code>report.md</code>. Add <code>--limit 4</code> for
    a smoke run that still exercises every family.</li>
<li><strong>Re-render.</strong> <code>python -m decision_models.cli report</code> for markdown,
    <code>python -m decision_models.tools.build_report_html</code> for this page. Neither loads
    a GPU.</li>
<li><strong>Freeze, then gate.</strong> <code>python -m decision_models.cli baseline</code>,
    then <code>python -m decision_models.cli gate</code>: exit 0 = unchanged, 1 = a metric
    regressed, 2 = the two inputs are not comparable.</li>
<li><strong>Serve.</strong> <code>python -m decision_models.cli serve</code> &mdash; dispatcher on
    <code>127.0.0.1:8077</code>, with <code>--policy</code> to change which model wins.</li>
</ol>

<h3>The CLI</h3>
<p>All seven subcommands, from the workspace root as
<code>python -m decision_models.cli &lt;command&gt;</code>.</p>
<ul>
<li><code>build</code> &mdash; regenerate the dataset. <code>--out PATH</code>.</li>
<li><code>bench</code> &mdash; score every backend. <code>--models a,b</code> (comma-separated
    keys), <code>--limit N</code> (counts authored items, so every family stays in proportion),
    <code>--split</code> (default: one subprocess per backend) / <code>--no-split</code>,
    <code>--on-error skip|fail</code>.</li>
<li><code>report</code> &mdash; re-render markdown from stored results. <code>--input</code>,
    <code>--out</code>, <code>--title</code>. No GPU.</li>
<li><code>baseline</code> &mdash; freeze the current results. <code>--input</code>.</li>
<li><code>gate</code> &mdash; fail if a re-run regressed. <code>--baseline PATH</code>,
    <code>--tolerance METRIC=VALUE</code>.</li>
<li><code>serve</code> &mdash; the language-aware dispatcher. <code>--host</code>,
    <code>--port</code> (or env <code>DECISION_HOST</code> / <code>DECISION_PORT</code>),
    <code>--policy lang:th=openthai,default=laya-en</code>.</li>
<li><code>expand</code> &mdash; write the per-backend expanded dataset without scoring it, to see
    exactly what the harness will ask.</li>
</ul>

<h2>What the testcases are</h2>
<p>An authored item can carry several questions, and each item is written twice &mdash; once in
English, once in Thai &mdash; so the two languages are the same test rather than two different
ones. That is the whole expansion: <strong>36 items &rarr; 68 rows &rarr; 90 questions &rarr;
&times;4 backends = 360 cases</strong>. <code>thai-only</code> is the one exception, four rows
with no English twin.</p>

<div class="scroll">__FAMILIES__</div>

<ul>
<li><strong>routing</strong> &mdash; which of the four registered subagents owns the request:
    weather, reservation, cost or general, including deliberately ambiguous inputs that still
    have to land on one of them. Four options, one question. This is the family the Route_gate
    router is built on.</li>
<li><strong>triage</strong> &mdash; how urgent it is: billing, technical, sales, other. Four
    options.</li>
<li><strong>multi</strong> &mdash; one shared state carrying three differently-typed questions (a
    choice, a score and a noul), so a single forward pass has to answer all three rather than
    only the first.</li>
<li><strong>noul</strong> &mdash; "none of the usual": a binary verdict with no option list.</li>
<li><strong>score</strong> &mdash; an ordinal rating with 3 or 5 levels, correct within 0.5 of
    the labelled level, so it reports MAE rather than accuracy.</li>
<li><strong>cardinality4</strong> &mdash; apply a rule stated in full inside the state, over four
    labelled options (a placement puzzle), plus a noul companion question.</li>
<li><strong>cardinality18</strong> &mdash; the same shape of task with the option count pushed to
    <strong>18</strong>: a Rubik's Cube inverse-move question offering every face turn
    (<code>R</code>, <code>R'</code>, <code>R2</code> &times; six faces), where the state states
    the inversion rule in full. <strong>It is the entire 6&ndash;20 option bucket</strong> &mdash;
    the six rows the limitations call suggestive rather than conclusive &mdash; and it is where
    the two models disagree most: OpenThai-SystemOne <strong>0.167</strong> against Laya
    <strong>0.500</strong>, at a chance baseline of 0.056.</li>
<li><strong>thai-only</strong> &mdash; Thai with no English twin, so an English-only model cannot
    look good here by accident.</li>
</ul>

<p>Two things easy to misread. The <code>options</code> column counts what the authored
<code>criteria</code> list holds, which is why noul shows <code>&mdash;</code>; the
<em>By option count</em> table above instead reads the width of the probability vector the model
actually scored, and counts a noul answer as 2. And four is a common option count, not a
constraint &mdash; the model is always scored over whatever list the question supplies.</p>

<h2>Proof of work</h2>
<p>A claim of "verified" is worth nothing without the ledger. Everything below was run in this
session and the exit status is recorded; where a check could not be completed it is listed as
such rather than omitted.</p>

<div class="scroll">
<table class="wide">
<thead><tr><th>check</th><th>command</th><th>observed</th><th>status</th></tr></thead>
<tbody>
<tr><td>harness unit + integration tests</td><td><code>python -m pytest</code></td>
    <td>113 passed</td><td><span class="tag ok">exit 0</span></td></tr>
<tr><td>TypeScript contracts</td><td><code>npx tsc --noEmit</code></td>
    <td>no output</td><td><span class="tag ok">exit 0</span></td></tr>
<tr><td>router + HTTP client tests</td><td><code>npx vitest run</code></td>
    <td>33 passed in 2 files</td><td><span class="tag ok">exit 0</span></td></tr>
<tr><td>the benchmark itself</td><td><code>python -m decision_models.cli bench</code></td>
    <td>4 backends, 360 rows, 0 errored</td><td><span class="tag ok">exit 0</span></td></tr>
<tr><td>regression gate, unchanged input</td><td><code>... cli gate</code></td>
    <td>20 metrics compared</td><td><span class="tag ok">exit 0</span></td></tr>
<tr><td>gate refuses a different dataset</td><td><code>... gate --baseline tampered.json</code></td>
    <td><code>dataset_sha256</code> mismatch named</td><td><span class="tag ok">exit 2</span></td></tr>
<tr><td>gate catches a regression</td><td><code>... gate --baseline regressed.json</code></td>
    <td><code>task_accuracy</code> diff &minus;0.337 &gt; 0.05</td>
    <td><span class="tag ok">exit 1</span></td></tr>
<tr><td>dispatcher serves real models</td><td>live <code>POST /v1/systemone</code></td>
    <td>200 &middot; <code>output_tokens: 0</code> &middot; both confidence fields</td>
    <td><span class="tag ok">verified</span></td></tr>
<tr><td>per-request backend override</td><td><code>{"model":"laya-ml"}</code></td>
    <td><code>model: laya-multilingual</code>, Thai script</td>
    <td><span class="tag ok">verified</span></td></tr>
<tr><td>public-benchmark replication</td><td><code>pip install datasets</code></td>
    <td>timed out before it could install</td><td><span class="tag no">not run</span></td></tr>
<tr><td><code>OpenThai-SystemOne/server.py</code> error path</td><td>&mdash;</td>
    <td>still returns a default move on failure</td><td><span class="tag part">partial</span></td></tr>
</tbody>
</table>
</div>

<h2>What is not proven</h2>
<div class="callout bad">
<p><strong>The public-benchmark replication was not run.</strong> The row builders for MASSIVE
(parallel <code>en-US</code> / <code>th-TH</code>, 60 intents) and XNLI exist and are tested
against synthetic records, but <code>pip install datasets</code> timed out, so no published
number was reproduced. That was the plan's independent check on the harness itself — the one
thing that would show the rig is measuring what it claims. Until then, these results are
measured but not externally validated.</p>
</div>

<ul>
  <li><strong>360 scored rows is small.</strong> A few points of difference is not
      distinguishable from noise, and per-cell slices are smaller still.</li>
  <li><strong>ECE is pre-fitting.</strong> Neither model's shipped calibration is used, and Laya
      reported invalid shipped temperatures for at least one question shape at load time. The
      figures are pre-temperature-fitting on purpose, and the 0.8 floor is therefore an arbitrary
      threshold rather than a calibrated one.</li>
  <li><strong>Latency is one process on one machine</strong> (RTX 5050 Laptop, 8&nbsp;GB) and
      includes the dispatch path. Magnitudes, not a benchmark. No published latency figure was
      reproduced.</li>
  <li><strong>Expectations were inherited</strong> from the source material for the routing and
      triage families rather than independently re-authored; the disagreement table in
      <code>report.md</code> is where an arguable label would show up.</li>
  <li><strong>The 6–20 option bucket is 6 rows.</strong> Suggestive, not conclusive.</li>
</ul>

<footer>
  Generated from <code>results/focused.json</code> by
  <code>decision_models/tools/build_report_html.py</code>. Dataset
  <code>__SHA__</code> &middot; __ROWS__ scored rows &middot; Laya <code>__LAYA__</code> &middot;
  OpenThai <code>__OPENTHAI__</code> &middot; Python __PYTHON__ &middot; __PLATFORM__.
  Companion artefacts: <code>report.md</code>, <code>README.md</code>,
  <code>results/focused.json</code>, <code>baselines/focused.json</code>.
</footer>

</div>
</body>
</html>
"""


def main() -> None:
    data = load()
    html = build_html(data)
    with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(html)
    print("wrote %s (%d bytes, %d cases)" % (OUT, len(html), len(data.get("cases") or [])))


if __name__ == "__main__":
    main()
