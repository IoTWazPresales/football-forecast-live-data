# HBT betting desk audit — 10 October 2026

## Outcome

The repaired research pipeline reconciles **25 of 25 previously scored fixtures**.
Frozen golden parity passes with maximum absolute error **1.11e-16** against the
existing 1e-9 tolerance. The new desk exposes **392 modelled market selections**:
200 exact 1X2/double-chance/DNB selections and 192 event selections on lines
recorded in the existing holdout artifact. These are modelled selections, **not
392 verified bookmaker offers**.

**No current executable bets.** The price collector reports
`PRICE_SOURCE_UNCONFIGURED`; all 25 forecasts are `L0 FALLBACK`; no final confirmed
XI forecast or independent kickoff proof is available. The historical prospective
card is retained byte-for-byte and remains behind the refreshed frozen export.
The recovered bridge explicitly emits `scoreMarkets: null`, so BTTS, goal totals
and team goal probabilities are unavailable on every scored fixture. A 1X2 vector
does not uniquely determine them.

The current discovery has 346 fixtures: 25 scored, 9 with insufficient model data,
16 not yet ready and 296 outside current supported coverage. There is no claim
that this covers every bookmaker or every football competition worldwide.

## Repairs implemented

- Scanner CI now uses the competition-specific 2.3 scanner. The three Dutch
  fixtures lost by an older scanner were recovered by rerunning the exact bridge.
- `--reconcile-existing` updates classifications after bridge generation without
  refetching discovery or restamping its source freshness. Main and forward
  workflows use it. Missing predictions in known fallback leagues are shown as
  not ready, rather than mislabelled unsupported.
- `hbt_build_betting_desk_v1.py` writes a JSON feed and searchable standalone HTML
  desk. Every scored fixture exposes home/draw/away, all three double chances and
  both DNB sides. Existing exact goal probabilities are supported when provided;
  absent probabilities remain explicitly missing.
- Highest profit probability and highest eligible value have separate fields.
  DNB profit probability is the unconditional win probability; a refund does not
  count as profit. DNB EV correctly accounts for the draw refund.
- Event tails use the existing event model/trainer calculation and existing
  frozen parameters. Only lines with held-out scores are surfaced. The older
  snapshot's under-6.5-card, under-13.5-corner and other extrapolated lines must
  not be called empirically validated line probabilities merely because the
  count-model family improved holdout NLL.
- 2–4-leg research chains have one fixture per leg, an explicitly unvalidated
  independence approximation, and Frechet probability bounds. Search is bounded
  to 16 probability candidates and 12 value candidates; it is not an exhaustive
  global optimum. Short-price/negative-EV legs remain watch candidates; they are
  not represented as profitable funded legs. DNB chains require a separate
  refund settlement tree and are excluded.
- Price normalization covers documented full-match ML, DC, DNB, BTTS and
  half-goal totals. Unrecognized event-price shapes remain raw/unpriced. No
  half-time, Asian quarter-line or player-price shape is guessed. Provider
  `updatedAt` and retrieval time are separate: fresh retrieval does not refresh
  an old quote. Row-level freshness, period, date, event consistency, kickoff
  match and post-freeze observation are checked.
- Execution audit eligibility now also reflects fixture timing/identity blocks.
  Existing frozen captures cannot be overwritten; new captures exclude started
  fixtures. No historical forecast was rewritten to incorporate a result or XI.
- Settlement supports canonical DRAW, HOME_DNB, AWAY_DNB, BTTS and half-goal
  totals keys. All captured main markets are settled, not only the displayed one.
- Missing surfaces or independent pre-match verification cannot become clean
  learning evidence. Scheduled forensics target yesterday in South Africa,
  rather than selecting the latest card, which may be in the future.
- The trainer's cold-start prior no longer consumes its own target counts.
  `maeCalibration` was an absolute outcome residual, not reliability calibration;
  future training uses the accurate metric name. Existing model parameters and
  promotion artifacts were not refitted or replaced.

## Learning result

The 9 October immutable card was audited: three forecast rows, two matched settled
results, zero verified executions and zero clean calibration rows. All three lack
independent pre-match identity/time proof. They remain process evidence, not
promotion evidence. The rebuilt registry has 112 audited rows, 102 legacy rows,
10 excluded guard rows and **zero clean guard-aware rows**.

Legacy recorded execution returned R27.09 on R29 of matched stakes, about -6.59%.
This incomplete exploratory record is not a current model validation, but it
demonstrates why a high winning-ticket count is insufficient to establish profit.
No weights were retuned and no hypothesis was automatically promoted.

## Remaining requirements

1. A valid Betway price source: configure the GitHub secret `ODDS_API_IO_KEY`, or
   supply legitimate current quotes with the documented provenance contract.
   Event market offer/settlement normalization still needs real provider samples.
2. The actual full deployed Fusion and score-distribution runtime. This repository
   has the recovered frozen L0 bridge, not an operational complete Fusion/BTTS
   runtime. Frozen L0 parity proves faithful execution, not predictive accuracy.
3. Timestamped independent kickoff verification and a final confirmed-XI capture
   with updated features and probabilities, stored as a separate immutable
   version rather than overwriting the original pre-XI card.
4. The HBT-1.4 chronological interaction training, family ablations, untouched
   holdout and reliability calibration required by the existing specifications.
   The registry still lists incomplete tactical, goalkeeper, set-piece, referee,
   workload, travel, manager, motivation, bench and player-impact families.
5. Prospective per-market calibration and a validated dependence/portfolio model
   before recommending funded chains. Tickets share team/model risk even when
   they contain different fixtures. Reusing legs across tickets concentrates it.
6. Actual local Forecast Lab UI integration. The attachment is a static snapshot;
   this repository contains the data/runtime scripts, not that application's UI
   source. The standalone desk and feed are provided as reviewable outputs.

## Verification

- 26 financial, timestamp, identity, causal and settlement tests pass.
- Exact frozen loader hash checks and golden parity pass.
- Intelligence integrity snapshot/verify and slate ranker checks pass.
- All 25 known scored fixtures reconcile; prior coverage regressions are zero.
- Existing prospective captures and match intelligence retain their original
  hashes. Frozen runtime chunks and parameter artifacts are unchanged.
- Workflow YAML parses; new read-only desk CI runs the tests and integrity checks.
- HTML content/script checks are available. A browser-render screenshot could
  not be obtained locally because Chromium is absent and its download failed.

All changes belong only to HBT and the research branch. Nothing from CIP, EIF,
Reclaim, Growbox, ASUS or Power BI was imported. The deployed frozen baseline is
not promoted or replaced by this work.
