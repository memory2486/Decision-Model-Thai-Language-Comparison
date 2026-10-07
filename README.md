# decision_models

One harness for two decision models, because they are the same thing wearing
different names: a `state` plus typed `questions` (`choice` / `score` / `noul`)
answered with calibrated probabilities in one forward pass and zero output
tokens.

- **Laya** — `convaiinnovations/laya`, Apache 2.0. English root checkpoint
  (ModernBERT-large, 421M) plus `multilingual` (mmBERT-base, 322M).
- **OpenThai-SystemOne** — `iapp/OpenThai-SystemOne`, Apache 2.0, Thai + English,
  0.8B.

Both are served over the same `POST /v1/systemone` body shape, so this is not an
integration problem. It is a *selection* problem, and the point of this package
is to answer it with measurements instead of vendors' numbers.

## The four things this measures that reading the docs will not tell you

1. **`confidence` means two different things.** Both models expose a field with
   that name, and in both it is `1 - H(p)/log(k)`. Laya *additionally* exposes
   `answer_confidence` — `max(p)` after temperature scaling — which is what its
   own gate and calibration figures use; OpenThai exposes no max-probability
   field at all. For a 4-option answer at `{0.94, .02, .02, .02}` that is 0.94
   against 0.7887, and 0.7887 is below Route_gate's 0.8 floor. **Every answer
   here carries both, computed by the same code for both models**, so their ECE
   and AURC are the same measurement.

2. **Laya's English checkpoint cannot read Thai, and does not know it.** The
   `laya.load(...)` entry point used by the pre-existing experiments has no
   script detection. Measured on the focused set: **0.319 accuracy on Thai
   against a 0.313 chance baseline**, with mean `max(p)` still at 0.525. Laya's
   own card says it: "Because the model stays confident while being wrong,
   confidence gating cannot save you." `laya.Router` fixes it by dispatching
   non-Latin script to `multilingual`.

3. **OpenThai-SystemOne won both languages** on the focused set — English 0.814
   vs 0.767, Thai 0.723 vs 0.596 — so language is *not* the switch the plan
   assumed. What it loses is time: p50 573 ms against `laya-ml` at 107 ms.

4. **The harness is Laya's own.** `laya.evals` already computes `ece`, `brier`,
   `aurc`, `selective_accuracy@50/@80` and the per-type evaluators, and already
   slices by `language` and `model` via `Example.language` / `Example.model`.
   This package adds one adapter, not a second metric stack.

## Usage

```bash
# score every backend and write report.md  (one process per backend)
python -m decision_models.cli bench

# smoke run / single backend
python -m decision_models.cli bench --limit 4
python -m decision_models.cli bench --models openthai --no-split

# re-render, freeze, and gate a future run
python -m decision_models.cli report
python -m decision_models.cli baseline
python -m decision_models.cli gate          # 0 pass, 1 regressed, 2 not the same measurement

# language-aware dispatcher on :8077/v1/systemone
python -m decision_models.cli serve
```

Backend keys: `laya-auto` (the script-aware Router), `laya-en`, `laya-ml`,
`openthai`. `laya-en` is kept as an explicit key so the failure mode is
*measured* rather than accidentally hit.

## Layout

| path | what it is |
|---|---|
| `confidence.py` | the normalization; both confidence notions, and a gate that fails closed |
| `limits.py` | the question constraints the *tighter* engine allows, so both are always asked survivable questions |
| `runners/` | the registry, plus one adapter per family (`laya_backend.py`, `openthai_backend.py`) |
| `bench.py` | expands items across backends and scores them with `laya.evals` |
| `report.py` | the comparison document: cross-slices, threshold-flip count, recommendation |
| `serve.py` | `POST /v1/systemone` in front of both models |
| `datasets.py` | MASSIVE / XNLI row builders for the public-benchmark replication |
| `report.md` | **the finding** — the rendered focused-set comparison |
| `baselines/focused.json` | frozen run the `gate` command compares against |

## Two deliberate design choices

**Answers are normalized to `answer_confidence = raw max(p)` for both models.**
Laya's own `answer_confidence` is temperature-scaled (measured ~0.15 above raw),
so using it would mean comparing a calibrated number against an uncalibrated
one. Laya's own figure is kept in `native_answer_confidence` and reported for
reference. Nothing is gated on it.

**Nothing ever substitutes a default for a missing confidence.** The failure
this replaces was `.get("answer_confidence", .get("confidence", 0.9))`, where an
absent key became a delegation-grade 0.9 indistinguishable from a real one. A
missing confidence is `None`, and `gate(None)` is `"confusion"`.

## Running the tests

```bash
python -m pytest          # 100 tests, no model weights required
```

The unit tests use fake backends and synthetic records, so they run in about two
seconds without touching a checkpoint. The end-to-end claim they cover is that
`laya.evals.evaluate` scores this package's runner with no special casing.

## Phase 6: what was patched, and what was not

`tools/phase6_patch.py` fixes the three modules that were loading a checkpoint
directly, and is idempotent (re-running reports no edits rather than duplicating
a line):

| module | defect fixed |
|---|---|
| `Laya_Agent_Gating/laya_router.py` | English checkpoint for every request; fabricated `0.9` and defaulted `"general"` choice |
| `exp_tetris/laya_player.py` | same loader defect; fabricated `0.85` and defaulted `"opt_0"` choice |
| `dsh-subagent-dispatch/laya_server.py` | same loader defect in the **served** component, reachable over HTTP; also now reports `answered_by` / `routing_reason`, and emits `answer_confidence` alongside `confidence` so the bare name is not the only signal |

Verified live in each case: Thai reports `answered_by: multilingual` with reason
`non-Latin script (thai, ...); the English checkpoint cannot read it`, and
English stays on `english`.

**Not patched:** `OpenThai-SystemOne/server.py`. Its loader is already correct
(it uses OpenThai-SystemOne, which reads Thai), so there is no router fix to
make. It does still return `move_candidates[0]` with `confidence_prob: 0.5` when
inference throws — a fail-open default of the same family as the others — but it
is a demo error path feeding a JavaScript client that was not inspected here,
and changing its contract without checking that client would be guesswork. It is
recorded rather than silently left.

## Limitations

- **Public benchmarks were not run.** `datasets.py` builds the MASSIVE (parallel
  `en-US` / `th-TH`, 60 intents) and XNLI rows and is tested against synthetic
  records, but `pip install datasets` did not finish in the time available, so
  the Phase 3 replication numbers do not exist. The transformation is verified;
  the run is not.
- **The focused set is small.** 360 scored rows, and per-cell slices are smaller
  still. Treat a few points of difference as noise.
- **Latency is one process on one machine** (RTX 5050 Laptop, 8 GB) and includes
  the runner dispatch path. Magnitudes, not benchmarks.
- **ECE is pre-fitting.** Neither model's shipped numbers are used, and Laya
  reported invalid shipped temperatures for one question shape at load time.
- **Four backends do not fit one 8 GB card.** The runner can swap, but Laya's
  module-level caches do not release on `unload()` and the process dies without
  a traceback, so `bench` defaults to one subprocess per backend and merges.
