# Decision-model comparison

Scored by `laya.evals` (`0.3.27`), the same harness Laya's own benchmarks use, with one adapter making OpenThai-SystemOne speak its runner contract. Metrics, metric math and calibration numbers therefore come from one implementation, not two.

## Run identity

| key | value |
|---|---|
| schema | laya-evals-report/1 |
| dataset_path | decision_models\data\focused_items.jsonl |
| dataset_sha256 | 8646f3551389c7d768eca620a12502e9e141edd20ac729a83b295f24014abbf0 |
| n_items | 68 |
| models | ['laya-ml'] |
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
| laya-ml | 90 | 90 | 0.633 | 0.688 | 0.652 | 0.789 | 0.190 | 0.144 | 0.772 | 0.776 | 0.630 |

## By language

The headline table. `chance` is the mean 1/options over the group, so a reading near chance is a model that is guessing at this width.

| model | lang | n | n scored | acc | choice | noul | score_MAE | ECE | AURC | sel@80 | mean max-p | mean entropy | chance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| laya-ml | en | 43 | 43 | 0.674 | 0.696 | 0.727 | 0.771 | 0.190 | 0.115 | 0.821 | 0.785 | 0.656 | 0.312 |
| laya-ml | th | 47 | 47 | 0.596 | 0.680 | 0.583 | 0.805 | 0.269 | 0.184 | 0.767 | 0.767 | 0.606 | 0.313 |

## By language and question family

| model | lang | family | n | acc | choice | noul | score_MAE | mean opts |
|---|---|---|---|---|---|---|---|---|
| laya-ml | en | cardinality18 | 3 | 0.333 | 0.333 | - | - | 18 |
| laya-ml | en | cardinality4 | 6 | 0.500 | 0.333 | 0.667 | - | 3 |
| laya-ml | en | multi | 12 | 0.750 | 0.500 | 1 | 0.564 | 3 |
| laya-ml | en | noul | 4 | 0.500 | - | 0.500 | - | 2 |
| laya-ml | en | routing | 8 | 1 | 1 | - | - | 4 |
| laya-ml | en | score | 5 | 0.400 | - | - | 0.936 | 3.800 |
| laya-ml | en | triage | 5 | 0.800 | 0.800 | - | - | 4 |
| laya-ml | th | cardinality18 | 3 | 0.667 | 0.667 | - | - | 18 |
| laya-ml | th | cardinality4 | 6 | 0.333 | 0.333 | 0.333 | - | 3 |
| laya-ml | th | multi | 12 | 0.667 | 0.500 | 1 | 0.675 | 3 |
| laya-ml | th | noul | 4 | 0.500 | - | 0.500 | - | 2 |
| laya-ml | th | routing | 8 | 0.875 | 0.875 | - | - | 4 |
| laya-ml | th | score | 5 | 0.400 | - | - | 0.912 | 3.800 |
| laya-ml | th | thai-only | 4 | 0.500 | 1 | 0.000 | 0.797 | 3.250 |
| laya-ml | th | triage | 5 | 0.600 | 0.600 | - | - | 4 |

## By option count

Laya splits its option budget (`head_max_len`) across the options, so accuracy is expected to fall as the option count rises. OpenThai-SystemOne supports up to 255 options and auto-enables order-invariant averaging above 10.

| model | options | n | acc | choice | chance | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| laya-ml | 2-2 | 23 | 0.652 | - | 0.500 | 22.462 | 30.476 |
| laya-ml | 3-5 | 61 | 0.639 | 0.714 | 0.267 | 22.676 | 35.722 |
| laya-ml | 6-20 | 6 | 0.500 | 0.500 | 0.056 | 23.300 | 24.353 |

## Latency

Measured on this machine, per backend call, for one question set over one state. Published figures for either model come from other hardware and are not reproduced here.

| model | lang | n | p50 ms | p95 ms |
|---|---|---|---|---|
| laya-ml | en | 43 | 22.988 | 35.722 |
| laya-ml | th | 47 | 22.584 | 26.220 |
| laya-ml | all | 90 | 22.772 | 35.722 |

## Confidence is two different numbers

Both models expose a field named `confidence`, and in both it is `1 - H(p)/log(k)` (entropy) -- the `native entropy` column below checks that claim rather than asserting it, and should equal `mean entropy` exactly.

Laya *additionally* exposes `answer_confidence`, the only field its `min_confidence` gate and its calibration figures are defined against. It is `max(p)` after temperature scaling, **not** the raw argmax probability: the `native max-p` column sits about 0.15 below the computed one because it carries Laya's temperature correction, and one shipped question shape was rejected as invalid at load time and fell back to an uncalibrated value. The comparison therefore computes raw `max(p)` here, identically for both models, so the ECE/AURC columns are the same measurement of each; Laya's own scaled number is reported for reference and is not what anything is gated on.

OpenThai-SystemOne exposes no max-probability field at all -- it reports only the entropy quantity, plus an `abstain` slot Laya's choice answer does not have.

| model | n | mean max-p | mean entropy | native entropy | native max-p | max-p minus entropy |
|---|---|---|---|---|---|---|
| laya-ml | 90 | 0.776 | 0.630 | 0.630 | 0.724 | 0.146 |

### Routing decisions that hinge on which field is read

Route_gate gates at `DELEGATION_FLOOR = 0.8`. Reading `max(p)` where it exists and `1 - H/log k` where it does not changes the routing action on **12 of 90** comparable cases (13.3%).

| qid | model | lang | max-p | entropy | correct |
|---|---|---|---|---|---|
| route | laya-ml | en | 0.885 | 0.675 | yes |
| route | laya-ml | th | 0.895 | 0.751 | no |
| department | laya-ml | en | 0.825 | 0.577 | yes |
| department | laya-ml | th | 0.891 | 0.701 | yes |
| urgency | laya-ml | en | 0.838 | 0.566 | - |
| urgency | laya-ml | th | 0.806 | 0.505 | - |
| department | laya-ml | en | 0.918 | 0.735 | yes |
| department | laya-ml | en | 0.837 | 0.561 | no |
| urgency | laya-ml | en | 0.917 | 0.733 | - |
| department | laya-ml | th | 0.876 | 0.637 | no |
| urgency | laya-ml | th | 0.907 | 0.708 | - |
| department | laya-ml | th | 0.845 | 0.575 | yes |

## Where the models disagree

The highest-value items for a human to look at, and the natural place to consider routing to an escalation path.

None: every backend agreed on correctness for every item.

## Recommendation

Measured winner per language: en -> `laya-ml`, th -> `laya-ml`.

One model wins in every language measured, so the routing policy can use `laya-ml` as a single default and keep the others as fallbacks rather than branching on language.

| language | best | acc | runner-up | acc | margin |
|---|---|---|---|---|---|
| en | laya-ml | 0.674 | - | - | - |
| th | laya-ml | 0.596 | - | - | - |

## Limitations

- Sample size is 90 scored rows; a difference of a few points is not distinguishable from noise at this size, and per-cell slices are smaller still.
- ECE here spans choice and noul only (a `score` answer has no boolean verdict). Neither model's shipped numbers are used: Laya's own card says its base checkpoint ships over-confident and needs temperature fitting, and at load time this run reported invalid shipped temperatures for at least one question shape. The ECE figures are therefore pre-fitting, on purpose.
- Latency is one measurement of one process on one machine, and includes the Runner dispatch path; treat it as a magnitude, not a benchmark.
- Expectations were inherited from the source material for the routing and triage families rather than re-authored; where a label is arguable, the disagreement table is the place that shows it.
- Which checkpoint actually answered (requested -> answered): laya-ml -> laya-multilingual.
