# HBT P0 recovered Fusion input trace — 6 November 2026

## Recovered originals verified locally

The user-owned Library archive `HBT_Fusion_Recovery_2026-10-30.zip`
was found, materialized and inspected in the current ChatGPT working container.
It contains unchanged original Fusion browser source, the original five-model
trained deployment export, original historical prediction export, and a
revalidation test kit. Seven isolated immutable-P1/P2 capture regression
tests passed with `PYTHONPATH=scripts python -m unittest discover -s tests`.
The original revalidation script recomputed 477 2018 validation fixture
rows and 378 2019 confirmation rows. These old holdouts are not live
prospective calibration.

GitHub research branch already has the exact inference port at
`runtime/hbt_fusion_inference_exact.mjs`, the original deployment
`runtime/hbt_frozen_fusion_deployment.json`, hash-locked manifest
`runtime/hbt_fusion_recovery_manifest.json`, and
`scripts/hbt_recovered_fusion_shadow.mjs`. Do **not** generate substitute
coefficients or rewrite the original frozen L0 control.

## Current input defects verified by direct repository reads

- `hbt_live_data/performance.json` has `generatedAt`
  **2026-11-01T19:52:15Z** while current 6 November input was generated
  about five days later; the recovered shadow expects source performance
  no older than 30 minutes for a clean capture. This stale source blocks
  an eligible live Fusion first-add.
- `hbt_live_data/player_features.json` was generated
  **2026-11-06T12:52:42Z**. Its Everton/Coventry row is
  `ok:false`, `reason:"outside confirmed-XI collection window"`.
  P1 pre-XI does not require confirmed-XI but P2 requires it.
- `hbt_live_data/frozen_control_forecast_2026-11-06.json` has 2 L0
  predictions and both lack `structuralFeatures`. The recovered shadow
  expressly requires a causal `structuralFeatures.vec` of length 11.
  The audited frozen bridge loader ALREADY supports opt-in
  `--with-structural-features` output projection **without modifying
  prediction logic or original coefficients**. Determine why the current
  published L0 control lacks that opt-in, and produce a separate hash-bound
  shadow input without overwriting immutable original capture.
- The only two 6 November scored forecasts are Everton/Coventry
  (en.1) and FC Famalicao/Arouca (pt.1). Recovered full Fusion
  `performance.json` supports five Big-5 leagues (en.1,es.1,de.1,
  it.1,fr.1), not pt.1. This is a documented coverage gap.
- `hbt_live_data/market_prices.json` remains
  `PRICE_SOURCE_UNCONFIGURED` with no `ODDS_API_IO_KEY`. Legitimate
  provider connection or independently auditable manually sourced odds
  must be added before profit/price labels can become current.
- `hbt_live_data/slate_scanner.json`: 104 discovered fixtures, 98
  unsupported, 4 insufficient, 2 fallback; `competition` often contains
  generic `regular-season`. This must be mapped to validated league
  identities rather than silently broadened.

## Next implementation steps with acceptance

1. Make a CI-only, read-only P1 Fusion rerun that projects L0 causal
   structural vectors using already audited `--with-structural-features`
   and verifies original L0 output parity; never overwrite immutable
   historical captures. Capture the list of `UNAVAILABLE` reasons.
2. Repair performance collector current-season freshness and tests;
   do not bypass the 30-minute P1 gate. Use an independent current
   source only if same feature semantics and leakage checks can be shown.
3. For eligible supported fixtures, generate score distributions
   and 1X2 P1/P2 models with source hashes, before kickoff and safely
   in research shadow. Date/identity and actual source freshness must pass.
4. Map validated shadow predictions into the market-first betting
   desk and current dashboard without mutating L0. Add regression and
   browser tests; unmodelled events remain unavailable, not fake 0%.
5. Continue the P0–P6 contract in
   `docs/HBT-END-TO-END-COMPLETION.md`.

**This is research-only; no stake authorisation, wager, model promotion,
cross-project data or branch merge.**
