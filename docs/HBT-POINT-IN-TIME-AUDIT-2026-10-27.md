# HBT point-in-time research audit — 27 October 2026

**Scope:** authoritative `research/hbt-1.4-match-intelligence` (inspected SHA `6cb4cf069ae285f59c09bf3f3c361917e83b0286`). Frozen HBT-1.1.2L-R1, Test A, historical captures, protected artifacts, odds, stakes, deployments and unrelated CIP/Reclaim/ASUS projects unchanged.

## 26 October — verified senior-men's 90-minute settlement

**Original forecast:** first-add commit `8923c6a6861eca29fbe1fb1bbe76f028855321f8` (2026-10-25T22:11:53Z), blob `aed8b6e1874eea35bab5d9e40baf587077a61ac8`, exported 2026-10-25T22:11:51.052Z. Same-run scanner blob `2f5291e7f10ef8bd269c759257fe3a3ad42b34a0` (generated 22:11:52Z). All three verified UTC kickoffs were later than export and commit. Do **not** substitute later same-path exports, including the 26 Oct 21:40Z overwrite.

| Fixture | UTC kickoff | 90-min FT | Original H/D/A | Original pick | Hit |
|---|---|---|---|---|---|
| Beşiktaş–İstanbul Başakşehir | 26 Oct 16:00Z | 2–0 | 49.09/27.14/23.77% | Beşiktaş | Yes |
| Çaykur Rizespor–Trabzonspor | 26 Oct 16:00Z | 3–4 | 29.75/27.14/43.11% | Trabzonspor | Yes |
| Galatasaray–Fenerbahçe | 26 Oct 18:30Z | 2–1 | 16.74/25.70/57.56% | Fenerbahçe | No |

Independent FT verification: [Betfred 2026–27 Süper Lig results](https://insights.betfred.com/football/competitions/turkiye/super-lig/results/). Cross-checks and kickoff provenance: [Sofascore Beşiktaş](https://www.sofascore.com/fr/football/match/basaksehir-fk-besiktas-jk/albsLlb), [FotMob Rizespor (16:00 UTC)](https://www.fotmob.com/matches/rizespor-vs-trabzonspor/16aj0h), [Futbol24 Galatasaray](https://www.futbol24.com/fr/match/2026/10/26/national/Turkiye/Super-Lig/2026-2027/Galatasaray/vs/Fenerbahce), [Beşiktaş 19:00 TRT = 16:00Z](https://en.wikipedia.org/wiki/2026%E2%80%9327_Be%C5%9Fikta%C5%9F_J.K._season), [Galatasaray 21:30 TRT = 18:30Z](https://stadiro.com/matches/turkey/super-lig/2026-10-26/galatasaray-v-fenerbahce/).

**26 Oct N3, all L0 FALLBACK:** 1X2 top-pick accuracy **2/3 (66.67%)**, unhalved multiclass Brier **0.65522**, natural log loss **1.11342**. Algebraic double-chance Brier **1X 0.23714, X2 0.34696, 12 0.07112**; DC log loss **0.65660, 0.95066, 0.31011** respectively. Top-pick confidence bins: 40–50% N2, 2/2; 50–60% N1, 0/1. Original states were **359, 360 and 2511 days stale**, respectively; the 2511-day Galatasaray case requires team/history lineage investigation.

**Provisional 23–26 Oct cumulative:** [draft PR #5](https://github.com/IoTWazPresales/football-forecast-live-data/pull/5) records prior 23–25 Oct N35, 19 hits, Brier 0.60878, log 1.00987. Including 26 Oct gives **N38, 21 hits (55.26%), Brier ≈0.61245, log ≈1.01805**, DC Brier **1X ≈0.23731, X2 ≈0.21651, 12 ≈0.15861**. Approximate combined values reflect rounded prior aggregates. All N38 were L0 fallback, not Fusion. N38 is too small and selectively covered for calibration/skill claims. Settlement 3/3 is not global senior-men fixture coverage. No genuine original BTTS or goal-total forecasts; no verified contemporaneous bookmaker prices/immutable selections, so **R5 flat-stake ROI is unavailable**.

## 27 October — zero date-scoped predictions despite discovery

First-add forecast commit `24d2bb8016425b6ec99a8e9b5920220f6c76518d`, export 2026-10-27T00:52:13.381Z, **0 predictions**. Same-run scanner 00:52:14Z: **102 discovered; 99 unsupported, 3 insufficient data, 0 fallback, 0 Fusion, 0 rank eligible**. Three unresolved Italian Serie A team identities: **Sassuolo–Lazio, AS Roma–Cagliari, Torino–Como**. The scanner says `discoveryComplete=true`; this describes configured-source reconciliation, **not forecast readiness**. This is the inspected snapshot, not a claim about later exports or unobserved fixtures. No 27 Oct results were settled.

Other blockers remain: 2026–27 `sco.1`, `tr.1`, `uefa.cl` history feeds return **404**; full Fusion/goal runtime missing; `market_prices.json` reports `PRICE_SOURCE_UNCONFIGURED`, `ODDS_API_IO_KEY` absent, **0 prices**. Collection-ready/XI rows do not imply prediction-ready.

## New research-only diagnostic

`scripts/hbt_snapshot_readiness_audit_v1.py` checks caller-supplied commit-pinned, same-run forecast/scanner JSON for frozen version, UTC timing, target-date identity, 1X2 probability shape, scanner count consistency and false discovery-versus-prediction readiness. It emits `ZERO_DATE_SCOPED_PREDICTIONS` and `DISCOVERY_COMPLETE_BUT_PREDICTION_EMPTY` independently of source discovery. **11 offline tests passed**: `python -m unittest discover -s tests -p 'test_hbt_snapshot_readiness_audit_v1.py' -v`. The diagnostic **does not authenticate first-add Git history, men's category, external kickoff/results, global coverage or betting readiness**. No operational scanner/forecast modifications.

**Priority:** (1) category exclusion before ranking/execution—women's leakage independently demonstrated in [draft PR #5](https://github.com/IoTWazPresales/football-forecast-live-data/pull/5), training contamination unproven; (2) source-order identity and zero-forecast readiness in [draft PR #2](https://github.com/IoTWazPresales/football-forecast-live-data/pull/2); (3) missing Fusion/goal runtime; (4) three history 404s and 2511-day stale case; (5) odds integration; (6) independent source-linked machine-readable settlement manifest to run [draft PR #4](https://github.com/IoTWazPresales/football-forecast-live-data/pull/4), with [draft PR #3](https://github.com/IoTWazPresales/football-forecast-live-data/pull/3) handling source clocks.

**Next experiment:** reproduce the three 27 Oct Serie A identity failures with copied source-order permutations; validate explicit category exclusion before scoring; run the 27 Oct artifacts through the read-only diagnostic. No merge, deploy, retune, promotion or stake increase.
