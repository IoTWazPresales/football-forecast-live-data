# HBT history-feed provenance audit — 30 October 2026

## Authority and immutable boundaries

Authoritative branch: research/hbt-1.4-match-intelligence, observed at 049489ca534b6a3ee6e7801ea724acd73b7c507f (30 Oct 09:35 UTC). Frozen HBT-1.1.2L-R1, Test A, source captures, prior forecasts, and historic metrics remain unchanged. This audit introduces no model inference, training, data substitution, betting selection, odds, or stake change. It is isolated from CIP, Reclaim and ASUS.

## Newly independently verified source failure mechanism

- At 30 Oct 09:34:57 UTC, hbt_live_data/forecast_bridge_status.json reports three 404 Not Found state-advance source failures: 2026-27/sco.1, 2026-27/tr.1, and 2026-27/uefa.cl.
- GitHub's upstream OpenFootball directory API, https://api.github.com/repos/openfootball/football.json/contents/2026-27?ref=master, returned only: de.1.json, en.1.json, en.2.json, es.1.json, fr.1.json, it.1.json, nl.1.json, pt.1.json. **None of the three requested files exists in the current upstream 2026–27 directory.** This supports missing upstream season coverage rather than a transient 404. The directory listing is mutable; later additions can change the result.
- The upstream 2025–26 directory contains sco.1.json and tr.1.json but no uefa.cl.json. Older files are **not** valid substitutes for 2026–27 updates and must not be silently used as current-season evidence.

## Current model coverage, no settlement backfill

- 30 Oct 09:35 UTC frozen-control forecast: **3 L0 fallback** predictions, **0 full Fusion**. Scanner: **141 discovered**, 3 fallback, 7 insufficient data, 131 unsupported; discoveryComplete=true is not prediction readiness. Price source remains PRICE_SOURCE_UNCONFIGURED.
- 29 Oct frozen-control forecast: **zero original predictions**. Its completed fixtures cannot add accuracy, Brier, log loss, calibration, or hypothetical R5 ROI observations. Carry-forward previously reported cumulative 23–28 Oct sample: 46 forecasts, 23 correct, 50.0% accuracy, approximately 0.65090 multiclass Brier and 1.07327 log loss. **Provisional:** no new independent re-scoring or verified price evidence in this audit.
- Full Fusion weights and inference artifacts exist under runtime/ and recovery is documented in docs/HBT-FUSION-RECOVERY-2026-10-10.md, but the active date-scoped output still has **zero Fusion predictions**. Distinguish recovered code/weights from current validated prediction readiness. Do not infer BTTS/goal-total outputs from 1X2 or old Fusion shadows.

## New read-only engineering diagnostic

Run: python scripts/hbt_history_feed_provenance_audit_v1.py --bridge hbt_live_data/forecast_bridge_status.json --season 2026-27

It fetches the current upstream season directory listing, cross-checks actual bridge failures, and distinguishes UPSTREAM_SEASON_FILE_ABSENT, FILE_PRESENT_BUT_REQUEST_FAILED, OTHER_SOURCE_FAILURE, and SOURCE_NOT_COVERED_BY_INDEX. It fails closed on missing/malformed input. It **does not** alter any runtime, state, forecast, source capture or odds.

Offline tests: python -m unittest discover -s tests -p 'test_hbt_history_feed_provenance_audit_v1.py' -v — **12 passed** on 30 Oct 2026.

## Prioritized unresolved gaps and next experiment

1. **Source coverage:** test an independently timestamped, competition-qualified 2026–27 match-results provider for Scotland, Turkey and UEFA Champions League. Verify score, regulation-time result, fixture identity, date, and historical state semantics against a controlled fixture sample. Do not plug it into frozen state advance before a parity and temporal-leakage audit.
2. **Competition provenance:** resolve PR #2 source-order identity conflict alongside research diagnostics PRs #7 and #8 (Brazilian Serie A and German second-tier leakage). Neither classification nor a collection-ready row authorizes model inference. Keep men's training lineage quarantined from women's, youth, reserves and college.
3. **Fusion operational coverage:** recover validated date-scoped structural features and score-distribution output without changing the frozen model. Recovered inference source alone is insufficient.
4. **Price and reliability:** configure a verified contemporaneous odds source and accumulate immutable pre-kickoff prospective forecasts with independently verified 90-minute settlements. Only then compute R5 flat-stake hypothetical ROI, calibration and sample-appropriate confidence intervals.

**Audit boundary:** This research identifies upstream file absence, not an approved replacement data source, a fixed forecast feed, a new model edge, or readiness for regular betting. Existing draft PR #2 is not merged or modified.
