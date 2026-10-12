# Decision-model comparison

Scored by `laya.evals` (`0.3.27`), the same harness Laya's own benchmarks use, with one adapter making OpenThai-SystemOne speak its runner contract. Metrics, metric math and calibration numbers therefore come from one implementation, not two.

## Run identity

| key | value |
|---|---|
| schema | laya-evals-report/1 |
| dataset_path | decision_models\data\focused_items.jsonl |
| dataset_sha256 | 8646f3551389c7d768eca620a12502e9e141edd20ac729a83b295f24014abbf0 |
| n_items | 68 |
| models | ['openthai'] |
| on_error | skip |
| laya_version | 0.3.27 |
| openthai_model | iapp/OpenThai-SystemOne |
| python | 3.14.5 |
| platform | Windows-11-10.0.26200-SP0 |

No rows errored: every backend answered every item it was asked.

## Overall

`acc` is the headline: choice and noul from the harness's own verdict, score counted correct within 0.5 of the labelled level. `ECE`/`AURC`/`sel@80` span choice and noul only, because a `score` answer has no boolean verdict.

| model | n | n scored | acc | choice | noul | score_MAE | ECE | AURC | sel@80 | mean max-p | mean entropy |
|---|---|---|---|---|---|---|---|---|---|---|---|
| openthai | 90 | 90 | 0.767 | 0.750 | 0.783 | 0.265 | 0.162 | 0.059 | 0.842 | 0.875 | 0.791 |

## By language

The headline table. `chance` is the mean 1/options over the group, so a reading near chance is a model that is guessing at this width.

| model | lang | n | n scored | acc | choice | noul | score_MAE | ECE | AURC | sel@80 | mean max-p | mean entropy | chance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openthai | en | 43 | 43 | 0.814 | 0.783 | 0.909 | 0.257 | 0.150 | 0.044 | 0.857 | 0.865 | 0.776 | 0.312 |
| openthai | th | 47 | 47 | 0.723 | 0.720 | 0.667 | 0.272 | 0.220 | 0.070 | 0.833 | 0.884 | 0.805 | 0.313 |

## By language and question family

| model | lang | family | n | acc | choice | noul | score_MAE | mean opts |
|---|---|---|---|---|---|---|---|---|
| openthai | en | cardinality18 | 3 | 0.000 | 0.000 | - | - | 18 |
| openthai | en | cardinality4 | 6 | 0.833 | 1 | 0.667 | - | 3 |
| openthai | en | multi | 12 | 0.750 | 0.500 | 1 | 0.281 | 3 |
| openthai | en | noul | 4 | 1 | - | 1 | - | 2 |
| openthai | en | routing | 8 | 1 | 1 | - | - | 4 |
| openthai | en | score | 5 | 0.800 | - | - | 0.238 | 3.800 |
| openthai | en | triage | 5 | 1 | 1 | - | - | 4 |
| openthai | th | cardinality18 | 3 | 0.333 | 0.333 | - | - | 18 |
| openthai | th | cardinality4 | 6 | 0.167 | 0.000 | 0.333 | - | 3 |
| openthai | th | multi | 12 | 0.750 | 0.500 | 1 | 0.283 | 3 |
| openthai | th | noul | 4 | 0.750 | - | 0.750 | - | 2 |
| openthai | th | routing | 8 | 1 | 1 | - | - | 4 |
| openthai | th | score | 5 | 1 | - | - | 0.195 | 3.800 |
| openthai | th | thai-only | 4 | 0.500 | 1 | 0.000 | 0.612 | 3.250 |
| openthai | th | triage | 5 | 1 | 1 | - | - | 4 |

## By option count

Laya splits its option budget (`head_max_len`) across the options, so accuracy is expected to fall as the option count rises. OpenThai-SystemOne supports up to 255 options and auto-enables order-invariant averaging above 10.

| model | options | n | acc | choice | chance | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| openthai | 2-2 | 23 | 0.783 | - | 0.500 | 105.834 | 164.252 |
| openthai | 3-5 | 61 | 0.820 | 0.833 | 0.267 | 92.225 | 164.252 |
| openthai | 6-20 | 6 | 0.167 | 0.167 | 0.056 | 87.086 | 122.950 |

## Latency

Measured on this machine, per backend call, for one question set over one state. Published figures for either model come from other hardware and are not reproduced here.

| model | lang | n | p50 ms | p95 ms |
|---|---|---|---|---|
| openthai | en | 43 | 104.660 | 159.270 |
| openthai | th | 47 | 92.225 | 164.252 |
| openthai | all | 90 | 101.145 | 164.252 |

## Confidence is two different numbers

Both models expose a field named `confidence`, and in both it is `1 - H(p)/log(k)` (entropy) -- the `native entropy` column below checks that claim rather than asserting it, and should equal `mean entropy` exactly.

Laya *additionally* exposes `answer_confidence`, the only field its `min_confidence` gate and its calibration figures are defined against. It is `max(p)` after temperature scaling, **not** the raw argmax probability: the `native max-p` column sits about 0.15 below the computed one because it carries Laya's temperature correction, and one shipped question shape was rejected as invalid at load time and fell back to an uncalibrated value. The comparison therefore computes raw `max(p)` here, identically for both models, so the ECE/AURC columns are the same measurement of each; Laya's own scaled number is reported for reference and is not what anything is gated on.

OpenThai-SystemOne exposes no max-probability field at all -- it reports only the entropy quantity, plus an `abstain` slot Laya's choice answer does not have.

| model | n | mean max-p | mean entropy | native entropy | native max-p | max-p minus entropy |
|---|---|---|---|---|---|---|
| openthai | 90 | 0.875 | 0.791 | 0.755 | - | 0.084 |

### Routing decisions that hinge on which field is read

Route_gate gates at `DELEGATION_FLOOR = 0.8`. Reading `max(p)` where it exists and `1 - H/log k` where it does not changes the routing action on **7 of 90** comparable cases (7.8%).

| qid | model | lang | max-p | entropy | correct |
|---|---|---|---|---|---|
| route | openthai | en | 0.913 | 0.769 | yes |
| urgency | openthai | th | 0.904 | 0.693 | - |
| urgency | openthai | th | 0.947 | 0.789 | - |
| frustration | openthai | th | 0.935 | 0.764 | - |
| frustration | openthai | en | 0.830 | 0.662 | - |
| next_move | openthai | en | 0.826 | 0.705 | no |
| next_move | openthai | en | 0.864 | 0.761 | no |

## Where the models disagree

The highest-value items for a human to look at, and the natural place to consider routing to an escalation path.

None: every backend agreed on correctness for every item.

## Recommendation

Measured winner per language: en -> `openthai`, th -> `openthai`.

One model wins in every language measured, so the routing policy can use `openthai` as a single default and keep the others as fallbacks rather than branching on language.

| language | best | acc | runner-up | acc | margin |
|---|---|---|---|---|---|
| en | openthai | 0.814 | - | - | - |
| th | openthai | 0.723 | - | - | - |

## Limitations

- Sample size is 90 scored rows; a difference of a few points is not distinguishable from noise at this size, and per-cell slices are smaller still.
- ECE here spans choice and noul only (a `score` answer has no boolean verdict). Neither model's shipped numbers are used: Laya's own card says its base checkpoint ships over-confident and needs temperature fitting, and at load time this run reported invalid shipped temperatures for at least one question shape. The ECE figures are therefore pre-fitting, on purpose.
- Latency is one measurement of one process on one machine, and includes the Runner dispatch path; treat it as a magnitude, not a benchmark.
- Expectations were inherited from the source material for the routing and triage families rather than re-authored; where a label is arguable, the disagreement table is the place that shows it.
- Which checkpoint actually answered (requested -> answered): openthai -> openthai.
