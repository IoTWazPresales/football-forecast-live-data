# HBT Fusion recovery and actual betting list

The Forecast Lab source and existing Fusion deployment were recovered from the
September project artifacts. The missing-runtime gap is resolved; the price-feed
credential gap remains unresolved. No bet was placed.

## Recovered source and weights

- Application: `football_forecast_lab_hbt_1_2r_r4_slate_fixed.html`, preserved
  byte-for-byte as `runtime/hbt_forecast_lab_r4.html.gz.b64`.
- Deployment: the `deploymentSnapshot` from
  `HBT-1.0L-R1-intelligence-fusion-run.json`, created
  `2026-09-12T11:15:44.195Z`; saved as
  `runtime/hbt_frozen_fusion_deployment.json`.
- Original inference function bodies: `runtime/hbt_fusion_inference_exact.mjs`.
- Provenance, file hashes, original validation and limitations:
  `runtime/hbt_fusion_recovery_manifest.json`.

No refitting, retuning or model promotion occurred. The original frozen L0
control and historical immutable captures remain authoritative. An opt-in
serialization projection exports its existing structural feature vectors; it
does not change any L0 probability or feature calculation.

`scripts/hbt_recovered_fusion_shadow.mjs` verifies the recovery hashes, model
dimensions, L0 snapshot identity and parity before computing the original
performance, context, residual Fusion and Poisson/Dixon-Coles score stack.
Same-day results cannot enter performance history. Confirmed XI requires the
same date, both identities, finite features and a nonfuture timestamp within
30 minutes. Unsupported leagues and missing vectors cannot produce scores.

The current recovered run produces 13 score distributions. These expose BTTS,
totals and team-goal estimates as research. They never create funded bets.
The saved full Fusion validation has 477 rows and a log-loss difference of
-0.000551 versus L1, with a confidence interval spanning zero. Its 2019
confirmation was reused, and the earlier raw EV betting audit failed.
Restored inference is not proof of a reliable present-day betting edge.

## Operational outputs

The research daily and two-day workflows now restore the Fusion shadow after
L0 parity, retain immutable pre-kickoff control captures, collect prices
downstream, and export a fresh actual eligible-selection list. Default-branch
scheduled workflow definitions have not been promoted.

`scripts/hbt_build_bet_list_v1.py --date YYYY-MM-DD` rebuilds the desk against
the current clock and produces `hbt_bet_list_YYYY-MM-DD.json` and `.md`.
The list includes only selections passing all current checks, ordered by win
probability among eligible positive-value singles. Eligibility means reviewable,
not placed. Chain funding remains disabled.

The October 10 list currently has **zero eligible singles, zero eligible chains,
zero verified priced markets and zero placed bets**. Suggested stake is R0.
The complete scored/discovered fixture inventory remains in the betting desk;
discovery is not proof that a bookmaker offers a fixture or market.

## Price feed status

No existing `ODDS_API_IO_KEY` was found in the available HBT setup or environment.
The current provider output explicitly reports `PRICE_SOURCE_UNCONFIGURED`.
A direct public Betway event-page request returned an application shell without
teams or odds; the linked application script returned HTTP 403. Search-index
odds were weeks old and were not ingested as current prices.

The required private provider credential cannot be manufactured or recovered
from a GitHub secret. It must exist in an authorized source before it can be
configured. No subscription was purchased and no credential was exposed.

## Validation

42 existing Python contract tests and seven recovered-Fusion tests pass.
L0 golden parity remains `1.1102230246251565e-16` against the unchanged `1e-9`
tolerance. Node syntax, changed workflow YAML and embedded Python blocks pass.
Recovery tests cover tampered weights, base/residual composition, probability
conservation, exact independent BTTS, chronological performance filtering,
unsupported inputs, future XI clocks and adjacent-date XI rejection.
