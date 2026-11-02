# HBT point-in-time research audit — 2 November 2026

**Authority:** `research/hbt-1.4-match-intelligence` pinned at `10cb8ccd7b0aadbf17f9e810628d1f364b126b23`. HBT-only. Frozen `HBT-1.1.2L-R1`, Test A, all existing source artifacts, historic captures, parameters and prior draft PRs untouched. No CIP/Reclaim/ASUS cross-project changes.

## Newly verified — 1 November senior men's regulation-time results

Original frozen L0 first-add: commit `736adb22b33d6093b4568dd5aaf89974609d98c7` at **31 Oct 11:10:59Z**, original Git blob `2e8488e16bbf871833b1d513b8acea2af61c039a`. This immutable original contained **17 L0 forecasts**. The later same-path file was overwritten, so it is **not** the source for scoring.

Three original `nl.1` L0 forecasts were **women's Vrouwen Eredivisie** fixtures and must be excluded from the men's cohort: ADO Den Haag–Feyenoord, AZ Alkmaar–PEC Zwolle, and FC Utrecht–De Graafschap. Independent competition evidence is linked per exclusion in [the manifest](evidence/hbt_2026_11_01_category_aware_settlement_manifest.json). This establishes **output/category contamination**, not proven training-data contamination. In particular, PR #10's scanner fix does not retroactively make the frozen bridge's misclassified L0 rows valid. PR #2 is still draft; neither PR is modified here.

**Fourteen valid senior men's L0 forecasts** were settled against independent FT-90 results and UTC kickoff evidence. All original L0 commit times precede kickoff. The earliest independently verified kickoff is PEC Zwolle–ADO Den Haag at 11:15Z, just **4 minutes 1 second** after the original L0 commit. Dutch source clocks for Excelsior–Twente and Telstar–Utrecht require CET-to-UTC conversion; original L0 remains before kickoff. Evidence URLs and exact scores are in the manifest.

Six recovered-Fusion **PRE-XI P1** captures were first added in commit `a4c8c8931a30d6284e185f73a81f52e44d492fc6` at **30 Oct 15:30:56Z**, before all six verified kickoffs. Their six Git blob SHAs, first-add probabilities, and distinct L4 score-market probabilities are pinned in the manifest. No P2 captures were scored; no current mutable shadow output was substituted.

| 1 Nov cohort | N | Correct 1X2 | Accuracy | Multiclass Brier | Log loss |
|---|---:|---:|---:|---:|---:|
| Valid original L0 senior men | 14 | 8 | 57.14% | 0.61001359 | 1.03685696 |
| L0 on same six Fusion fixtures | 6 | 3 | 50.00% | 0.61935077 | 1.05777759 |
| Original recovered Fusion P1 | 6 | 4 | 66.67% | 0.59666367 | 1.01234647 |

**Fusion-derived DC Brier** (N=6 each): 1X **0.24607375**, X2 **0.28544989**, 12 **0.06514003**. **Separate L4 score-distribution Brier** (N=6 each): BTTS Yes **0.26124794**; over 1.5 **0.24507473**; over 2.5 **0.28538150**; over 3.5 **0.26205709**. These markets must not be mixed with Fusion's 1X2 vector.

**Descriptive reliability, not validated calibration:** Fusion top-pick confidence <50%: 3/4 correct, mean confidence 40.32%; >=50%: 1/2 correct, mean confidence 64.89%. L0 top-pick confidence <50%: 5/8 correct, mean 41.13%; >=50%: 3/6 correct, mean 60.26%. Six or fourteen observations are far too few to establish calibration.

## Provisional cumulative position

Earlier provisional cohorts (through 31 Oct) are carried forward **without independent full re-scoring today**. Frozen L0 **40/82 = 48.78%**, approximate Brier **0.64091**, log loss **1.06678**. Recovered Fusion P1 **13/20 = 65.00%**, approximate Brier **0.59522**, log loss **1.01348**. Do not present these as clean calibration, superiority, or a profitable betting edge. The Fusion input-feature source hashes, source timestamps and training lineage have not passed full independent as-of verification.

**R5 hypothetical flat-stake ROI: unavailable**, because `ODDS_API_IO_KEY` remains unconfigured and no verified contemporaneous bookmaker prices or immutable priced selections exist. Retrospective odds on results websites are not a substitute.

## Current readiness and prioritized blockers

As of the authoritative 2 Nov frozen control export at **04:05:25Z**, HBT emitted **2 L0 fallbacks, zero full Fusion forecasts**. The 2 Nov scanner snapshot is older (generated 1 Nov 11:56Z) and reports 63 discovered fixtures, 2 fallbacks, 6 current-model coverage gaps, 24 identity-unproven and 30 research-expansion candidates. Discovery completeness is not prediction readiness. The desk reports **zero ready singles**.

1. **Category integrity and source-qualified competition identity:** women's fixtures still entered frozen men's L0 output; source-order, country and division ambiguities remain. Independently review PR #2, then fail closed before ranking/settlement and audit men's historical-state lineage. Never edit frozen bridge or historic captures.
2. **Clean prospective lineage:** verify each P1/P2 capture's source feature as-of timestamps, raw hashes, league/team identities and confirmed-XI provenance; do not treat a collection-ready row as a prediction.
3. **Operational date-scoped full Fusion/goal runtime:** recovered research P1 is not a production-ready full model. Current frozen bridge remains L0-only.
4. **2026–27 historical feeds:** `sco.1`, `tr.1`, `uefa.cl` still 404 at upstream; validate alternative provider lineage without retroactive backfilling.
5. **Bookmaker pricing and prospective sample:** configure and verify a licensed provider separately before any hypothetical R5 ROI; no wagering authorization.

**Next independently testable experiment:** Add a read-only, source-qualified competition-category gate to a non-frozen consumer and regression-test these three 1 Nov women's fixtures plus 25 Oct leakage, with unknown categories quarantined. In parallel, independently attest first-add P1 source feature clocks and raw hashes. Do not merge, deploy, retune, promote, increase stakes, or touch unrelated projects.

## Audit limitations

The manifest is a manually reviewed settlement ledger with independent result/kickoff links; offline tests check schema, category, timestamp, probabilities, original P1 Git blobs and recomputed metrics. They **do not** fetch external match evidence or independently prove as-of input-feature lineage. All metrics remain research-only. No source capture, protected file, historic prediction or model parameter was changed.
