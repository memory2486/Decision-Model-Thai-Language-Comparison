# Decision-model comparison

Scored by `laya.evals` (`0.3.27`), the same harness Laya's own benchmarks use, with one adapter making OpenThai-SystemOne speak its runner contract. Metrics, metric math and calibration numbers therefore come from one implementation, not two.

## Run identity

| key | value |
|---|---|
| schema | decision-models-focus/1 |
| dataset_path | decision_models\data\focused_items.jsonl |
| dataset_sha256 | 8646f3551389c7d768eca620a12502e9e141edd20ac729a83b295f24014abbf0 |
| n_items | 360 |
| models | ['laya-auto', 'laya-en', 'laya-ml', 'openthai'] |
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
| laya-auto | 90 | 90 | 0.678 | 0.708 | 0.696 | 0.575 | 0.193 | 0.197 | 0.772 | 0.769 | 0.610 |
| laya-en | 90 | 90 | 0.533 | 0.521 | 0.609 | 0.698 | 0.169 | 0.299 | 0.632 | 0.643 | 0.451 |
| laya-ml | 90 | 90 | 0.633 | 0.688 | 0.652 | 0.789 | 0.204 | 0.142 | 0.772 | 0.776 | 0.630 |
| openthai | 90 | 90 | 0.767 | 0.750 | 0.783 | 0.265 | 0.162 | 0.060 | 0.842 | 0.874 | 0.791 |

## By language

The headline table. `chance` is the mean 1/options over the group, so a reading near chance is a model that is guessing at this width.

| model | lang | n | n scored | acc | choice | noul | score_MAE | ECE | AURC | sel@80 | mean max-p | mean entropy | chance |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| laya-auto | en | 43 | 43 | 0.767 | 0.739 | 0.818 | 0.320 | 0.223 | 0.173 | 0.821 | 0.772 | 0.615 | 0.312 |
| laya-auto | th | 47 | 47 | 0.596 | 0.680 | 0.583 | 0.805 | 0.294 | 0.180 | 0.733 | 0.767 | 0.606 | 0.313 |
| laya-en | en | 43 | 43 | 0.767 | 0.739 | 0.818 | 0.320 | 0.223 | 0.173 | 0.821 | 0.772 | 0.615 | 0.312 |
| laya-en | th | 47 | 47 | 0.319 | 0.320 | 0.417 | 1.037 | 0.241 | 0.550 | 0.367 | 0.525 | 0.302 | 0.313 |
| laya-ml | en | 43 | 43 | 0.674 | 0.696 | 0.727 | 0.770 | 0.191 | 0.113 | 0.821 | 0.786 | 0.657 | 0.312 |
| laya-ml | th | 47 | 47 | 0.596 | 0.680 | 0.583 | 0.805 | 0.294 | 0.180 | 0.733 | 0.767 | 0.606 | 0.313 |
| openthai | en | 43 | 43 | 0.814 | 0.783 | 0.909 | 0.258 | 0.150 | 0.044 | 0.857 | 0.864 | 0.775 | 0.312 |
| openthai | th | 47 | 47 | 0.723 | 0.720 | 0.667 | 0.271 | 0.219 | 0.072 | 0.833 | 0.884 | 0.805 | 0.313 |

## By language and question family

| model | lang | family | n | acc | choice | noul | score_MAE | mean opts |
|---|---|---|---|---|---|---|---|---|
| laya-auto | en | cardinality18 | 3 | 0.333 | 0.333 | - | - | 18 |
| laya-auto | en | cardinality4 | 6 | 0.333 | 0.333 | 0.333 | - | 3 |
| laya-auto | en | multi | 12 | 0.917 | 0.750 | 1 | 0.277 | 3 |
| laya-auto | en | noul | 4 | 1 | - | 1 | - | 2 |
| laya-auto | en | routing | 8 | 1 | 1 | - | - | 4 |
| laya-auto | en | score | 5 | 0.600 | - | - | 0.355 | 3.800 |
| laya-auto | en | triage | 5 | 0.800 | 0.800 | - | - | 4 |
| laya-auto | th | cardinality18 | 3 | 0.667 | 0.667 | - | - | 18 |
| laya-auto | th | cardinality4 | 6 | 0.333 | 0.333 | 0.333 | - | 3 |
| laya-auto | th | multi | 12 | 0.667 | 0.500 | 1 | 0.674 | 3 |
| laya-auto | th | noul | 4 | 0.500 | - | 0.500 | - | 2 |
| laya-auto | th | routing | 8 | 0.875 | 0.875 | - | - | 4 |
| laya-auto | th | score | 5 | 0.400 | - | - | 0.912 | 3.800 |
| laya-auto | th | thai-only | 4 | 0.500 | 1 | 0.000 | 0.796 | 3.250 |
| laya-auto | th | triage | 5 | 0.600 | 0.600 | - | - | 4 |
| laya-en | en | cardinality18 | 3 | 0.333 | 0.333 | - | - | 18 |
| laya-en | en | cardinality4 | 6 | 0.333 | 0.333 | 0.333 | - | 3 |
| laya-en | en | multi | 12 | 0.917 | 0.750 | 1 | 0.277 | 3 |
| laya-en | en | noul | 4 | 1 | - | 1 | - | 2 |
| laya-en | en | routing | 8 | 1 | 1 | - | - | 4 |
| laya-en | en | score | 5 | 0.600 | - | - | 0.355 | 3.800 |
| laya-en | en | triage | 5 | 0.800 | 0.800 | - | - | 4 |
| laya-en | th | cardinality18 | 3 | 0.333 | 0.333 | - | - | 18 |
| laya-en | th | cardinality4 | 6 | 0.333 | 0.333 | 0.333 | - | 3 |
| laya-en | th | multi | 12 | 0.250 | 0.250 | 0.250 | 0.820 | 3 |
| laya-en | th | noul | 4 | 0.500 | - | 0.500 | - | 2 |
| laya-en | th | routing | 8 | 0.250 | 0.250 | - | - | 4 |
| laya-en | th | score | 5 | 0.200 | - | - | 1.134 | 3.800 |
| laya-en | th | thai-only | 4 | 0.500 | 0.500 | 1 | 1.423 | 3.250 |
| laya-en | th | triage | 5 | 0.400 | 0.400 | - | - | 4 |
| laya-ml | en | cardinality18 | 3 | 0.333 | 0.333 | - | - | 18 |
| laya-ml | en | cardinality4 | 6 | 0.500 | 0.333 | 0.667 | - | 3 |
| laya-ml | en | multi | 12 | 0.750 | 0.500 | 1 | 0.564 | 3 |
| laya-ml | en | noul | 4 | 0.500 | - | 0.500 | - | 2 |
| laya-ml | en | routing | 8 | 1 | 1 | - | - | 4 |
| laya-ml | en | score | 5 | 0.400 | - | - | 0.936 | 3.800 |
| laya-ml | en | triage | 5 | 0.800 | 0.800 | - | - | 4 |
| laya-ml | th | cardinality18 | 3 | 0.667 | 0.667 | - | - | 18 |
| laya-ml | th | cardinality4 | 6 | 0.333 | 0.333 | 0.333 | - | 3 |
| laya-ml | th | multi | 12 | 0.667 | 0.500 | 1 | 0.674 | 3 |
| laya-ml | th | noul | 4 | 0.500 | - | 0.500 | - | 2 |
| laya-ml | th | routing | 8 | 0.875 | 0.875 | - | - | 4 |
| laya-ml | th | score | 5 | 0.400 | - | - | 0.912 | 3.800 |
| laya-ml | th | thai-only | 4 | 0.500 | 1 | 0.000 | 0.796 | 3.250 |
| laya-ml | th | triage | 5 | 0.600 | 0.600 | - | - | 4 |
| openthai | en | cardinality18 | 3 | 0.000 | 0.000 | - | - | 18 |
| openthai | en | cardinality4 | 6 | 0.833 | 1 | 0.667 | - | 3 |
| openthai | en | multi | 12 | 0.750 | 0.500 | 1 | 0.280 | 3 |
| openthai | en | noul | 4 | 1 | - | 1 | - | 2 |
| openthai | en | routing | 8 | 1 | 1 | - | - | 4 |
| openthai | en | score | 5 | 0.800 | - | - | 0.241 | 3.800 |
| openthai | en | triage | 5 | 1 | 1 | - | - | 4 |
| openthai | th | cardinality18 | 3 | 0.333 | 0.333 | - | - | 18 |
| openthai | th | cardinality4 | 6 | 0.167 | 0.000 | 0.333 | - | 3 |
| openthai | th | multi | 12 | 0.750 | 0.500 | 1 | 0.283 | 3 |
| openthai | th | noul | 4 | 0.750 | - | 0.750 | - | 2 |
| openthai | th | routing | 8 | 1 | 1 | - | - | 4 |
| openthai | th | score | 5 | 1 | - | - | 0.194 | 3.800 |
| openthai | th | thai-only | 4 | 0.500 | 1 | 0.000 | 0.609 | 3.250 |
| openthai | th | triage | 5 | 1 | 1 | - | - | 4 |

## By option count

Laya splits its option budget (`head_max_len`) across the options, so accuracy is expected to fall as the option count rises. OpenThai-SystemOne supports up to 255 options and auto-enables order-invariant averaging above 10.

| model | options | n | acc | choice | chance | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| laya-auto | 2-2 | 23 | 0.696 | - | 0.500 | 215.266 | 564.542 |
| laya-auto | 3-5 | 61 | 0.689 | 0.738 | 0.267 | 203.657 | 564.542 |
| laya-auto | 6-20 | 6 | 0.500 | 0.500 | 0.056 | 343.548 | 508.624 |
| laya-en | 2-2 | 23 | 0.609 | - | 0.500 | 560.478 | 1407.890 |
| laya-en | 3-5 | 61 | 0.525 | 0.548 | 0.267 | 332.574 | 1401.325 |
| laya-en | 6-20 | 6 | 0.333 | 0.333 | 0.056 | 833.410 | 1089.947 |
| laya-ml | 2-2 | 23 | 0.652 | - | 0.500 | 178.327 | 246.411 |
| laya-ml | 3-5 | 61 | 0.639 | 0.714 | 0.267 | 93.080 | 240.087 |
| laya-ml | 6-20 | 6 | 0.500 | 0.500 | 0.056 | 210.918 | 240.688 |
| openthai | 2-2 | 23 | 0.783 | - | 0.500 | 717.837 | 958.744 |
| openthai | 3-5 | 61 | 0.820 | 0.833 | 0.267 | 493.547 | 883.732 |
| openthai | 6-20 | 6 | 0.167 | 0.167 | 0.056 | 1238.041 | 1438.730 |

## Latency

Measured on this machine, per backend call, for one question set over one state. Published figures for either model come from other hardware and are not reproduced here.

| model | lang | n | p50 ms | p95 ms |
|---|---|---|---|---|
| laya-auto | en | 43 | 470.903 | 569.420 |
| laya-auto | th | 47 | 119.322 | 240.401 |
| laya-auto | all | 90 | 215.266 | 564.542 |
| laya-en | en | 43 | 495.505 | 627.198 |
| laya-en | th | 47 | 359.758 | 1407.890 |
| laya-en | all | 90 | 379.318 | 1407.890 |
| laya-ml | en | 43 | 166.418 | 224.846 |
| laya-ml | th | 47 | 100.883 | 246.411 |
| laya-ml | all | 90 | 106.766 | 246.411 |
| openthai | en | 43 | 649.617 | 1092.323 |
| openthai | th | 47 | 527.289 | 1242.833 |
| openthai | all | 90 | 572.830 | 1233.250 |

## Confidence is two different numbers

Both models expose a field named `confidence`, and in both it is `1 - H(p)/log(k)` (entropy) -- the `native entropy` column below checks that claim rather than asserting it, and should equal `mean entropy` exactly.

Laya *additionally* exposes `answer_confidence`, the only field its `min_confidence` gate and its calibration figures are defined against. It is `max(p)` after temperature scaling, **not** the raw argmax probability: the `native max-p` column sits about 0.15 below the computed one because it carries Laya's temperature correction, and one shipped question shape was rejected as invalid at load time and fell back to an uncalibrated value. The comparison therefore computes raw `max(p)` here, identically for both models, so the ECE/AURC columns are the same measurement of each; Laya's own scaled number is reported for reference and is not what anything is gated on.

OpenThai-SystemOne exposes no max-probability field at all -- it reports only the entropy quantity, plus an `abstain` slot Laya's choice answer does not have.

| model | n | mean max-p | mean entropy | native entropy | native max-p | max-p minus entropy |
|---|---|---|---|---|---|---|
| laya-auto | 90 | 0.769 | 0.610 | 0.610 | 0.716 | 0.159 |
| laya-en | 90 | 0.643 | 0.451 | 0.451 | 0.579 | 0.192 |
| laya-ml | 90 | 0.776 | 0.630 | 0.630 | 0.724 | 0.146 |
| openthai | 90 | 0.874 | 0.791 | 0.755 | - | 0.084 |

### Routing decisions that hinge on which field is read

Route_gate gates at `DELEGATION_FLOOR = 0.8`. Reading `max(p)` where it exists and `1 - H/log k` where it does not changes the routing action on **39 of 360** comparable cases (10.8%).

| qid | model | lang | max-p | entropy | correct |
|---|---|---|---|---|---|
| route | laya-auto | en | 0.928 | 0.761 | yes |
| route | laya-auto | th | 0.895 | 0.750 | no |
| department | laya-auto | en | 0.927 | 0.754 | yes |
| department | laya-auto | en | 0.879 | 0.645 | yes |
| department | laya-auto | en | 0.916 | 0.726 | yes |
| department | laya-auto | th | 0.893 | 0.705 | yes |
| urgency | laya-auto | th | 0.808 | 0.509 | - |
| department | laya-auto | en | 0.892 | 0.675 | yes |
| urgency | laya-auto | en | 0.950 | 0.793 | - |
| department | laya-auto | th | 0.873 | 0.630 | no |
| urgency | laya-auto | th | 0.908 | 0.710 | - |
| frustration | laya-auto | en | 0.914 | 0.714 | - |
| department | laya-auto | th | 0.839 | 0.563 | yes |
| route | laya-en | en | 0.928 | 0.761 | yes |
| department | laya-en | en | 0.927 | 0.754 | yes |
| department | laya-en | en | 0.879 | 0.645 | yes |
| department | laya-en | en | 0.916 | 0.726 | yes |
| department | laya-en | en | 0.892 | 0.675 | yes |
| urgency | laya-en | en | 0.950 | 0.793 | - |
| frustration | laya-en | en | 0.914 | 0.714 | - |

## Where the models disagree

The highest-value items for a human to look at, and the natural place to consider routing to an escalation path.

| item | lang | question | laya-auto | laya-en | laya-ml | openthai | expected |
|---|---|---|---|---|---|---|---|
| cube-inverse-02 | en | next_move | F | F | F' | F' | F |
| cube-inverse-02 | th | next_move | F | F | F | F' | F |
| cube-inverse-03 | en | next_move | L | L | L2 | R' | L2 |
| cube-inverse-03 | th | next_move | L2 | R2 | L2 | L2 | L2 |
| multi-billing-01 | th | department | sales | billing | sales | technical | billing |
| multi-billing-01 | th | refund_requested | 0.108 | 0.823 | 0.108 | 0.026 | no |
| multi-billing-01 | th | urgency | 1.906 | 1.011 | 1.906 | 1.980 | 2 |
| multi-billing-refund-01 | th | department | billing | sales | billing | billing | billing |
| multi-billing-refund-01 | th | urgency | 1.794 | 0.776 | 1.794 | 1.899 | 2 |
| multi-sales-01 | en | department | sales | sales | technical | other | sales |
| multi-sales-01 | th | refund_requested | 0.001 | 0.832 | 0.001 | 0.006 | no |
| multi-sales-01 | en | urgency | 0.338 | 0.338 | 1.594 | 0.025 | 0.000 |
| multi-sales-01 | th | urgency | 1.764 | 0.994 | 1.764 | 0.060 | 0.000 |
| multi-technical-01 | th | department | technical | billing | technical | technical | technical |
| multi-technical-01 | th | refund_requested | 0.000 | 0.893 | 0.000 | 0.006 | no |
| multi-technical-01 | en | urgency | 0.775 | 0.775 | 1.404 | 1.749 | 1 |
| multi-technical-01 | th | urgency | 1.630 | 1.071 | 1.630 | 1.950 | 1 |
| noul-churn-01 | en | churn_threat | 0.834 | 0.834 | 0.068 | 0.952 | yes |
| noul-churn-01 | th | churn_threat | 0.032 | 0.351 | 0.032 | 0.782 | yes |
| noul-churn-02 | th | churn_threat | 0.002 | 0.545 | 0.002 | 0.005 | no |
| noul-churn-03 | en | churn_threat | 0.803 | 0.803 | 0.006 | 0.955 | yes |
| noul-churn-03 | th | churn_threat | 0.033 | 0.848 | 0.033 | 0.379 | yes |
| placement-01 | en | placement | opt_0 | opt_0 | opt_2 | opt_2 | opt_2 |
| placement-01 | en | safe | 0.339 | 0.339 | 0.698 | 0.261 | yes |
| placement-02 | en | placement | opt_0 | opt_0 | opt_3 | opt_0 | opt_0 |
| placement-02 | th | placement | opt_0 | opt_0 | opt_0 | opt_3 | opt_0 |
| placement-03 | en | placement | opt_0 | opt_0 | opt_0 | opt_1 | opt_1 |
| placement-03 | en | safe | 0.692 | 0.692 | 0.632 | 0.241 | no |
| route-ambiguous-01 | th | route | cost | reservation | cost | reservation | reservation |
| route-cost-01 | th | route | cost | reservation | cost | cost | cost |
| route-cost-02 | th | route | cost | reservation | cost | cost | cost |
| route-general-01 | th | route | general | reservation | general | general | general |
| route-reservation-01 | th | route | reservation | general | reservation | reservation | reservation |
| route-weather-01 | th | route | weather | reservation | weather | weather | weather |
| route-weather-02 | th | route | weather | reservation | weather | weather | weather |
| score-frustration-01 | en | frustration | 1.908 | 1.908 | 1.214 | 1.983 | 2 |
| score-frustration-01 | th | frustration | 1.309 | 0.761 | 1.309 | 1.981 | 2 |
| score-frustration-02 | en | frustration | 0.482 | 0.482 | 1.091 | 0.434 | 0.000 |
| score-frustration-02 | th | frustration | 0.898 | 0.585 | 0.898 | 0.070 | 0.000 |
| score-frustration-03 | en | frustration | 1.522 | 1.522 | 1.198 | 1.597 | 1 |
| score-frustration-04 | en | frustration | 3.367 | 3.367 | 1.766 | 3.962 | 4 |
| score-frustration-04 | th | frustration | 1.266 | 1.443 | 1.266 | 3.914 | 4 |
| score-frustration-05 | th | frustration | 1.113 | 1.850 | 1.113 | 0.698 | 1 |
| thai-register-01 | th | churn_threat | 0.013 | 0.820 | 0.013 | 0.045 | yes |
| thai-register-02 | th | department | technical | billing | technical | technical | technical |
| triage-billing-01 | th | department | billing | sales | billing | billing | billing |
| triage-other-01 | en | department | billing | billing | billing | other | other |
| triage-other-01 | th | department | sales | billing | sales | other | other |
| triage-sales-01 | th | department | billing | technical | billing | sales | sales |

## Recommendation

Measured winner per language: en -> `openthai`, th -> `openthai`.

One model wins in every language measured, so the routing policy can use `openthai` as a single default and keep the others as fallbacks rather than branching on language.

That default is not the fastest: `laya-ml` answers in 107 ms p50 against `openthai` at 573 ms (5.4x), for 0.633 vs 0.767 accuracy. A latency-bound caller should trade the accuracy deliberately rather than inherit this default.

| language | best | acc | runner-up | acc | margin |
|---|---|---|---|---|---|
| en | openthai | 0.814 | laya-auto | 0.767 | 0.047 |
| th | openthai | 0.723 | laya-auto | 0.596 | 0.128 |

## Limitations

- Sample size is 360 scored rows; a difference of a few points is not distinguishable from noise at this size, and per-cell slices are smaller still.
- ECE here spans choice and noul only (a `score` answer has no boolean verdict). Neither model's shipped numbers are used: Laya's own card says its base checkpoint ships over-confident and needs temperature fitting, and at load time this run reported invalid shipped temperatures for at least one question shape. The ECE figures are therefore pre-fitting, on purpose.
- Latency is one measurement of one process on one machine, and includes the Runner dispatch path; treat it as a magnitude, not a benchmark.
- Expectations were inherited from the source material for the routing and triage families rather than re-authored; where a label is arguable, the disagreement table is the place that shows it.
