# HBT point-in-time research audit — 1 November 2026

Authority: `research/hbt-1.4-match-intelligence` at `334d7c9300d02586821584322c3f66cef000f16a`. HBT-only. No CIP/Reclaim/ASUS cross-contamination. Frozen HBT-1.1.2L-R1, Test A, source artifacts, historical captures, model parameters and prior draft PRs unchanged.

## Point-in-time evidence
- Frozen 31 October L0 first-add: `ecc138e22b12b7ab036e6c2f3cbe9927868f5292` committed 00:26:08 UTC, Git blob `ad9dd1786318de5b3d8782e013b8e11bc8c01a0e`, 20 L0 forecasts.
- Recovered Fusion P1 first-add: `a4c8c8931a30d6284e185f73a81f52e44d492fc6` committed 30 October 15:30:56 UTC. All 13 original P1 Git blobs were checked against this commit tree and current authority. Original source/capture timestamps ~15:30:47 UTC. All predate independently verified kickoffs.
- Independent senior-men 90-minute FT and kickoff evidence per fixture in `docs/evidence/hbt_2026_10_31_settlement_manifest.json`. Core sources: [Guardian fixture schedule](https://www.theguardian.com/football/fixtures/2026/Oct/31), [Guardian Premier League FT](https://www.theguardian.com/football/live/2026/oct/31/manchester-city-v-brighton-bournemouth-v-leeds-and-more-clockwatch-live), [Betfred Bundesliga FT](https://insights.betfred.com/football/competitions/germany/bundesliga/results/), [Reuters Serie A FT](https://www.reuters.com/sports/soccer/milan-earn-3-1-derby-win-over-inter-roma-thump-udinese-5-2-2026-10-31/), [SPFL FT](https://spfl.co.uk/league/premiership/results) and [SPFL postponement](https://spfl.co.uk/clubs/dundee-united/fixtures).
- Dundee United–Hearts was **postponed**, so one L0 prediction is excluded from settlement. PSV–Willem II source `18:45` is local Netherlands time; independent UTC kickoff `17:45` ([UTC evidence](https://footballnation.eu/match/eredivisie/2026/791891/)); original L0 still predates kickoff.

## Verified descriptive results (31 October)
| Cohort | Settled | Correct 1X2 | Accuracy | Multiclass Brier | Log loss |
|---|---:|---:|---:|---:|---:|
| Original L0 fallback | 19/20 | 7 | 36.84% | 0.66404728 | 1.10852108 |
| L0 paired on Fusion fixtures | 13/13 | 5 | 38.46% | 0.64807728 | 1.08956517 |
| Recovered PRE-XI Fusion P1 | 13/13 | 8 | 61.54% | 0.61536840 | 1.04383068 |

Paired improvement is **3 additional correct predictions on 13 matches**, not evidence of superiority or profitability. Fusion-derived DC Brier (13 each): 1X 0.21323732, X2 0.26632650, 12 0.13580458. Separate genuine L4 score-market Brier: BTTS Yes 0.26647085; over 1.5 0.13806212; over 2.5 0.27154628; over 3.5 0.17839170. L4 DC: 1X 0.20787365, X2 0.25726479, 12 0.13512037. Never substitute `scoreMarkets.hda` for Fusion 1X2.

Descriptive reliability bins: Fusion top-pick confidence <50%: 4/6 correct, mean 43.08%; >=50%: 4/7 correct, mean 60.32%. N=13 is insufficient for calibration.

Provisional cumulative L0 23–31 Oct: 32/68 (47.06%), approximate Brier 0.64727, log loss 1.07294; prior 49 carried forward without full re-scoring. Recovered Fusion 30–31 Oct: 9/14 (64.29%), approximate Brier 0.59460, log loss 1.01396. **Input-feature as-of lineage not independently certified**; these are provisional settlements, not clean prospective calibration. No verified contemporaneous bookmaker prices, so hypothetical R5 ROI is unavailable.

## Engineering and next experiment
New isolated evidence manifest plus 10 synthetic/static manifest-invariant tests (the separate offline paired scorer and 16 synthetic tests were also prepared locally, but not included in this PR). The manifest is human-verified evidence; tests do not fetch external sources. Source SHA/commit checks were performed independently using GitHub, not end-to-end on a local authoritative checkout.

Blockers: (1) category/country/division identity and PR #2 review; (2) missing independently verified Fusion input as-of lineage and clean prospective P1/P2 sample; (3) operational full Fusion/goal runtime and true date-scoped readiness; (4) upstream 2026–27 `sco.1`, `tr.1`, `uefa.cl` 404s; (5) unconfigured Odds-API.io key and absent contemporaneous priced selections.

Next: verify 13 P1 source-feature hashes and timestamps, prove category/competition lineage, and settle 1 November P1 only after independently verified 90-minute FT. No merge, deployment, training, retuning, promotion, stake increase or wagers.
