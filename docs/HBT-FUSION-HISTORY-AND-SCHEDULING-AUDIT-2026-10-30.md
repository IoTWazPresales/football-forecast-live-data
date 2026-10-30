# HBT model recovery and historical validation — 2026-10-30

## Scope and safety

This is HBT-only research evidence. It does not promote models, merge weights, claim verified bookmaker prices, establish prospective calibration or authorize wagers.

## Source provenance

The user's original HBT Forecast Lab Library includes the 395,562-byte HTML `HBT_1_2R_R4_FROZEN_SNAPSHOT_RECOVERY.html` and the 1,136,405-byte original export `HBT-1.0L-R1-intelligence-fusion-run.json`, created 2026-09-12T11:15:44.195Z. The export contains model coefficients for L1, full XI core, pre-XI core, home Poisson and away Poisson, as well as match-level validation/confirmation predictions.

Before this audit, the HBT research repository had **already** recovered the full Fusion inference and deployment, at `runtime/hbt_fusion_inference_exact.mjs` and `runtime/hbt_frozen_fusion_deployment.json`. The user Library files were independently located and retained on an isolated recovery branch for provenance. The missing runtime claim in earlier readiness discussions was therefore inaccurate: the missing component was active default-branch scheduling of Fusion prospective generation, not the model inference code itself.

## Independent arithmetic check of historical original-export predictions

2018 validation: 477 matches on 57 distinct dates, 2018-08-31 to 2018-12-30.

- L1 log loss: 0.9839117302; full Fusion log loss: 0.9833605606.
- Paired delta Fusion − L1: −0.0005511697.
- 2,000 date-block bootstrap 95% interval: [−0.0070681653, +0.0059348264], includes zero.
- Full Fusion accuracy: 51.78%.

2019 confirmation: 378 matches on 55 distinct dates, 2019-03-01 to 2019-05-26.

- L1 log loss: 0.9969390342; full Fusion log loss: 0.9903918385.
- Paired delta Fusion − L1: −0.0065471957.
- 2,000 date-block bootstrap 95% interval: [−0.0152083, +0.0022414], includes zero.
- Full Fusion accuracy: 50.26%.

Both windows were reconstructed from individual probabilities/results in the original export rather than accepting its summary percentages. The 2019 confirmation period was previously reused by HBT, so it must **not** be represented as a fresh untouched holdout. This is not evidence of bookmaker profitability; the export contains no verified pre-match odds. These dates are only the exported 2018–19 Fusion validation windows, not a claim of verified five-year 2021–26 Fusion evaluation.

## Operational repair

The default `main` branch previously contained the scheduled live-data collector but lacked the prospective Fusion daily and forward-two-day workflow definitions that lived only on the research branch. Scheduled GitHub Actions launch from the default branch. The same guarded workflows were added to `main` with explicit checkout of `research/hbt-1.4-match-intelligence`, so no model branch or weights were promoted. The two-day run is scheduled 05:15 UTC; the daily run is scheduled 08:30 and 15:30 UTC.

New research sidecar `scripts/hbt_capture_fusion_firstadd_v1.py` records the **first** pre-kickoff full-Fusion P1 or P2 shadow prediction using an exclusive-create, separate file per fixture/stage under `hbt_live_data/captures/fusion/`. It checks source freshness, causal clock, fixture identity, supported competition, probability conservation and model status. It cannot rewrite historical records, cannot award clean evidence without independent result/identity checks and cannot authorize bets. `scripts/hbt_publish_research_outputs.py` rejects modifications to an existing immutable first-add file; unit tests test the invariant. Workflow integration was added to research and default-branch workflow definitions.

## Remaining hard gates

1. Independent pre-match bookmaker odds from an authorized provider or audited quote contract. HBT `market_prices.json` reports `PRICE_SOURCE_UNCONFIGURED`; this audit did not create, infer or bypass a credential.
2. Historical data lineage and genuinely untouched out-of-sample evaluation against *no-vig bookmaker* or credible baseline across the intended full five-year period, plus post-training recent era drift checks.
3. Sufficient independently settled, clean, multiple-date P1/P2 prospective evidence; the new first-add recorder creates future raw evidence, not clean evidence retroactively.
4. Competition-identity and independent fixture/kickoff gates, confirmed XI provenance and R1/R2 expected-value/risk checks. Existing HBT readiness blocks remain intact.

**Decision: NO_REAL_MONEY_BET.** No wagers placed, no automatic stake adjustments, no model promotion, no historical records relabelled as prospective.
