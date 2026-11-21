# HBT end-to-end completion contract — 2026-11-06

## Objective

Deliver and independently test a genuinely working HBT football analysis system,
not another static dashboard. For every discovered fixture in a clearly
enumerated *supported* league slate, HBT must discover offered markets,
calculate evidenced model-backed selection probabilities, match independently
verified current bookmaker quotes, produce distinct high-win-probability and
high-expected-return rankings, propose evidence-labelled singles and multi-leg
research chains, and capture eventual regulation-time settlement without
forecast/result leakage. Missing or unsupported inputs are flagged, never
fabricated.

## Protected project boundaries

Repository: `IoTWazPresales/football-forecast-live-data`.
Authoritative branch: `research/hbt-1.4-match-intelligence`.
Isolated implementation branch: `research/hbt-market-first-board-2026-11-06`.
Draft review: PR #14. Do not merge into authoritative research or main, do
not overwrite frozen L0/HBT-1.1.2L-R1, trained coefficients, original captures,
or completed historical settlements without separately proved acceptance.
HBT has no dependency on CIP, Reclaim, EIF, ASUS, financial projects, or their
data. No automatic wagers or stake changes.

## Recovered original source, do not rebuild from scratch

The user's saved, original `HBT_Fusion_Recovery_2026-10-30.zip` contains
`HBT-1.0L-R1-deploymentSnapshot.json` (original trained 5-model coefficients),
`HBT-1.0L-R1-intelligence-fusion-run.json`, original HTML Fusion/L4/confirmed-XI
source, and revalidation scripts. The repository already holds
`runtime/hbt_fusion_inference_exact.mjs`,
`runtime/hbt_frozen_fusion_deployment.json` and
`scripts/hbt_recovered_fusion_shadow.mjs`. The recovery branch
`recovery/hbt-fusion-source-20261030` exists; inspect the recovered runtime
and its provenance before creating any replacement. October 30 original
revalidation: 477 2018 validation and 378 2019 confirmation matches;
difference confidence intervals include zero, hence no claimed live edge.

## Verified baseline at planning

Snapshot 2026-11-06: 104 discovered; 98 unsupported competition,
4 insufficient data, 2 frozen L0, 0 full-model forecasts, 0 quote-matched
markets. Price feed `PRICE_SOURCE_UNCONFIGURED`, secret
`ODDS_API_IO_KEY` missing. Current intelligence has 8 older confirmed-XI
fixtures with player props but zero current confirmed-XI recomputations.
Historical clean guard-aware prospective rows = 0 in forensic learning
assessment. The new dashboard UI is interactive and CI passed, but HBT's
underlying market execution flow is not end-to-end ready.

## Ordered engineering work and acceptance criteria

1. **Full Fusion runtime and current inputs.** Reuse recovered original
   coefficients, proven score distribution and shadow inference. Fix
   `performance.json` / `player_features.json` identity, date and freshness
   join, inspect real shadow output from current supported fixtures, preserve
   L0 and exact hash evidence. Do NOT convert recovered shadow into a
   "validated funded" prediction. Acceptance: pre-kickoff 1X2 and goal-score
   market probabilities generated with source lineage on at least several
   independent supported fixture dates; golden coefficient and L0 parity
   unchanged; shortages explicitly audited.
2. **Fixture provenance/coverage.** Normalize competition identity
   (generic ESPN `regular-season` must not be treated as a league identity).
   Verify official kickoff UTC, participant identities and supported league
   classification independently where possible. Acceptance: no cross-league
   silent joins; full input and discovery reconciliation; target dates correct;
   coverage demonstrated on multiple live slates. Explicitly show 0 if
   selected league was genuinely unforecastable.
3. **Market completeness.** Map all offered markets to a stable ontology,
   but calculate numerical probabilities *only when separately supported*.
   Existing family: 1X2, DC, DNB, L4 BTTS, totals, team goals, event
   corners/cards/shots, player shots/SOT/anytime scorer when actual validated
   model outputs can be safely joined. First scorer and red cards require
   independent training, historical event labels, calibration, and bookmaker
   settlement verification; underperforming red-card model stays research-only.
   Acceptance: every supported market either has evidence-backed probability
   and explainable data quality, or is clearly unavailable; no inferred
   goal markets from just 1X2; DNB refunds treated as pushes.
4. **Odds integration.** Provider-backed, source-attributed prices matched by
   event ID, exact market, period, line, player and current timestamp.
   Preserve bookmaker independent of model forecast. Existing secret
   `ODDS_API_IO_KEY` is absent; no credential can be invented.
   Acceptance: authenticated real price source or verifiable manually
   captured quotes, stale/conflicting prices rejected, negative-EV displayed
   separately from expected-win chance.
5. **Chain engine.** Rank two objectives (chance and return), calculate
   odds/EV for 2–4 legs and optional same-match combo only with independently
   validated joint model. Model dependence/correlated legs, exclusion rules
   and DNB refund settlement. Research chains remain explicitly unfunded
   until joint evidence and R1/R2 requirements pass.
6. **Live dashboard/service.** Replace local manually imported snapshot with
   source-linked build and always show retrieval and as-of times.
   Provide fixture explorer, full modelled market table, probability/
   quoted-value leaderboards, chain studio, missing-data diagnostic,
   calibration/settlement evaluation, and exports. Acceptance: reproducible
   one-command startup or published reproducible read-only dashboard link,
   and desktop/mobile browser end-to-end tests, no stale odds presented current.
7. **Evidence and final audit.** Preserve original prospective forecasts
   immutable at pre-kickoff and verify 90-minute results independently.
   Report Brier, log loss, calibration reliability, baseline/no-vig
   comparison, by-market sample size/dates, drift and leakage diagnostics.
   Prospective confirmation on multiple days is required before calling
   funded strategies validated; passing software tests alone is insufficient.

## Completion decision

**Dashboard/demo complete** requires P0-P6 engineering contracts and current
readable outputs with no silently missing critical systems. Supported-market
coverage is enumerated, not claimed universal. Any unavailable player/
first-scorer, red-card or bookmaker market must be clearly flagged.

**Real-money recommendation ready** is a separate stricter decision:
sufficient clean independently verified prospective outcomes and reliable
calibration versus credible bookmaker/no-vig or simple baselines,
working current verified odds, confirmed lineups and risk/EV gates, and
at least one truly eligible real future single. No bet is guaranteed.
A complete interface does not itself authorize betting.

## Execution / notification contract

Each engineering iteration should inspect actual repository evidence and
current branch head, work on small isolated reviewable commits, run real
tests and browser checks, leave a concise checkpoint in GitHub, and tackle
the next unblocked dependency. Never report success merely because a file
was refreshed, a test suite passed or model output was generated.
Notify the user only when the actual integrated system passes completion
criteria, or once if a specific external credential or inaccessible
original asset requires the user's direct action.
