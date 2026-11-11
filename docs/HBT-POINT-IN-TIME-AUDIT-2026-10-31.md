# HBT point-in-time research audit — 31 October 2026

**Authority:** `research/hbt-1.4-match-intelligence` at `87ef9768c58f2e1df3c20f49d823959170373dbe` (06:05:04 UTC). **Isolation:** HBT only. HBT-1.1.2L-R1, Test A, frozen parameters, historical captures, source artifacts, production execution and CIP/Reclaim/ASUS unchanged. No automatic merges, deployment, retraining, retuning, stakes or wagers.

## Verified 30 October senior men's settlements

Independent 90-minute final scores: [Konyaspor–Galatasaray 0–4](https://www.sportytrader.com/en/results-live/konyaspor-galatasaray-8628385/), [Le Havre–PSG 1–5](https://www.skysports.com/football/le-havre-vs-paris-saint-germain/7139460248674265232) corroborated by [Reuters](https://www.reuters.com/sports/soccer/hakimi-hat-trick-leads-psg-5-1-win-le-havre-2026-10-30/), and [Casa Pia–Sporting CP 0–2](https://www.fotmob.com/en-GB/matches/sporting-cp-vs-casa-pia-ac/bdp8hnv).

The original **L0 control** export was committed **29 Oct 23:44:16 UTC**, `c2b66822cc565bf5b1b93e1de2863253a81437d2`, Git blob `cad94ed20e67237a0d8a10636a1df87a02c445ab`, exported 29 Oct 23:44:13.087 UTC. All three original predictions predated their verified kickoffs. The same path was overwritten after kickoff at 30 Oct 20:57 UTC: **do not use that later export as original evidence**.

| Original L0 fixture | 1X2 [home, draw, away] | FT | Pick | Correct |
|---|---|---|---|---|
| Konyaspor–Galatasaray | [.451574,.255389,.293037] | 0–4 | Konyaspor | No |
| Le Havre–PSG | [.193981,.239993,.566025] | 1–5 | PSG | Yes |
| Casa Pia–Sporting | [.252676,.265923,.481401] | 0–2 | Sporting | Yes |

**30 Oct L0 (N=3):** 1X2 accuracy **2/3 (66.67%)**, multiclass Brier (sum of three squared errors) **0.48533443**, multiclass log loss **0.84254211**. Derived DC Brier: 1X **0.31902505**, X2 **0.10179764**, 12 **0.06451174**. No genuine L0 BTTS or goal totals. **Provisional cumulative L0, 23–30 Oct:** 49 predictions, 25 correct (**51.02%**), approximate Brier **0.64076**, log loss **1.05914**; the earlier 46 and their approximate aggregate scores were carried forward, not independently rescored today. No meaningful calibration conclusion.

## First settled pre-kickoff recovered-Fusion P1 first-add

Le Havre–PSG P1 capture was committed **30 Oct 16:41:43 UTC**, `4b2606bcc2286dce707c547fb394e87c584bf298`, original blob `b215b4ee19892217ce11a75b9ef4a33fd3c3d04c`; captured 16:41:39.281667 UTC, before independently verified 18:00 UTC kickoff. The first-add file is `hbt_live_data/captures/fusion/hbt_fusion_firstadd_2026-10-30_62ad9129e7633faac7fa6d5d_P1.json`. Source generated 16:41:39.224 UTC. The 90-minute result was **1–5**.

**P1 Fusion 1X2:** [.22526032,.23981576,.53492392]; correct away top pick; multiclass Brier **0.32454957**, log loss **0.62563075**, N=1. Fusion-derived DC Brier: 1X **0.21629576**, X2 **0.05074221**, 12 **0.05751160**.

**Genuine L4 score-distribution markets**, kept distinct from Fusion-derived 1X2/DC: 1X .51381424 (false; Brier .264005), X2 .72786947 (true; .074055), 12 .75831630 (true; .058411), BTTS Yes .61128707 (true; .151098), over 1.5 .81952046 (true; .032573), over 2.5 .59719058 (true; .162255), over 3.5 .37346031 (true; .392552). N=1 each. **This is unpromoted, research-only PRE-XI Fusion, not confirmed-XI P2, not a clean prospective calibration sample without full input-lineage proof, and not betting eligible.**

New evidence manifest: `docs/evidence/hbt_fusion_p1_settlement_2026-10-30.json`. New fail-closed scorer: `scripts/hbt_fusion_firstadd_settlement_audit_v1.py`, with 14 locally passing synthetic regression tests. It verifies the original Git blob SHA, pre-kickoff capture/commit clocks, independent 90-minute result and UTC kickoff, senior men's category, Fusion/L4 market lineage, and no ROI fabrication. Run against a locally checked-out authoritative branch with:

```bash
python scripts/hbt_fusion_firstadd_settlement_audit_v1.py --capture hbt_live_data/captures/fusion/hbt_fusion_firstadd_2026-10-30_62ad9129e7633faac7fa6d5d_P1.json --manifest docs/evidence/hbt_fusion_p1_settlement_2026-10-30.json
python -m unittest discover -s tests -p 'test_hbt_fusion_firstadd_settlement_audit_v1.py' -v
```

Synthetic tests were run locally; **the end-to-end CLI against a locally materialized original capture was not run**. GitHub's original first-add blob and timestamps were separately checked. No contemporaneous verified bookmaker odds or immutable pre-match selections: **R5 flat-stake hypothetical ROI unavailable**.

## Material forward coverage progress

Recovered Fusion inference/weights already existed; 30 Oct operational repair introduced scheduled forward shadow generation and exclusive-create first-add capture. At 31 Oct 06:05 UTC, the first-add capture directory contained **1 P1 for 30 Oct, 13 P1 for 31 Oct, 6 P1 for 1 Nov**, and **no P2**. These are raw research-only captures, not 20 clean settled matches. The current 31 Oct frozen bridge generated **20 L0 fallback** predictions, zero full Fusion; the separate 30 Oct 15:30 UTC forward Fusion shadow generated **13 research-only score distributions**, zero confirmed-XI and zero eligible bets. Do not merge different timestamps or model cohorts. Price status remains `PRICE_SOURCE_UNCONFIGURED`.

## Prioritized blockers and next experiment

1. **Competition category/identity**: review draft PR #2 alongside #7/#8. Brazilian Serie A vs Italian and German 2. Bundesliga vs first-division defects remain; do not confuse metadata contamination with proven training contamination. Test country/division/source-order and training lineage before changing any runtime.
2. **Clean P1/P2 prospective evidence**: audit all 13 original 31 Oct P1 capture identities, commit timestamps and input-source as-of times, then independently settle regulation-time results after final whistle. Confirmed XI/P2 currently absent. No retrospective relabelling.
3. **Missing 2026–27 history**: `sco.1`, `tr.1`, `uefa.cl` OpenFootball files absent (404); test replacement source with independent identity and timestamps, not stale-season backfill.
4. **Coverage and calibration**: frozen bridge `READY` does not mean full Fusion operational or bet-ready; one P1 settlement cannot establish calibration or edge. Require untouched prospective sample and appropriate no-vig baseline.
5. **Odds/value**: `ODDS_API_IO_KEY` unconfigured; no verified contemporaneous bookmaker prices, no defensible R5 ROI, no real-money readiness.

**Decision: NO_REAL_MONEY_BET.** All prior PRs untouched and unmerged; this PR adds only isolated research scorer, tests, manifest and audit.
