# HBT Fusion runtime recovery kit — 30 October 2026

## What this restores

The actual original single-file HBT browser application's Fusion / PRE-XI / confirmed-XI and L4 score-model **source code and original trained Fusion coefficient export**. This was recovered from the user's own HBT Library files. It is not a newly generated or approximated replacement.

The exact original source is `recovery/HBT_1_2R_R4_FROZEN_SNAPSHOT_RECOVERY.html`; SHA-256 `8d139104722ea51171c2a473f80ed69dfea6b2ba08466b39b7e95fafc9514de7`. Identical code is preserved in the dedicated GitHub branch `recovery/hbt-fusion-source-20261030`, Git blob `8d68270a2d99170faa3fe4023396fb301e1904cc`.

`recovery/HBT_FUSION_WITH_MODEL_EXPORT.html` adds **only** a read-only button, **Export HBT saved models**. It does not change training, inference, forecast probabilities, betting gates or stored records. The exporter is also available separately as `recovery/hbt_snapshot_exporter.js`.

## Original trained Fusion export FOUND

The user's Library also contains `HBT-1.0L-R1-intelligence-fusion-run.json` created 12 September 2026, included unchanged in this archive. It has the full five model coefficients under `deploymentSnapshot.models`: `l1`, `fullCore`, `preXiCore`, `homePoisson`, `awayPoisson`. These are preserved separately in `recovery/HBT-1.0L-R1-deploymentSnapshot.json` and committed to the recovery GitHub branch. SHA-256 of the complete original export is `484706e307b3a0a5aa8db98b39eb7b79c27911f20dbbaa3352b76971c4ea84c1`. No coefficients were changed.

`HBT_ORIGINAL_FUSION_REVALIDATION.json` was independently recomputed from the original match-level predictions using `scripts/hbt_revalidate_original_fusion.py`: **477 validation fixtures in 2018** and **378 confirmation fixtures in 2019**. On validation, full Fusion log loss was 0.98336 versus 0.98391 for L1; on confirmation, 0.99039 versus 0.99694. Both 95% date-block bootstrap intervals on the loss difference include zero. The PRE-XI challenger is not established as superior and no bookmaker odds were included. These are old retrospective holdouts, not modern clean prospective evidence or 2021–2026 Five-Year Live-Fusion tests.

The original L0 live deployment states are still not in this full-Fusion export. The Fusion export records the original L0 lock timestamp and hyperparameters, but not its per-club states and complete snapshot. The original deployed L0 needs to be recovered from browser state or proven identical to the GitHub frozen runtime before Fusion can be safely replayed live.

## Recover existing trained state (preserve original before retraining)

1. **Do not clear site data or retrain yet.** On the original PC and browser profile, open the HBT HTML at the **same URL/origin** used when the validated model was trained. Browser IndexedDB and localStorage are origin-specific. Serving this HTML on a new port or opening a copy from a different location will not make the old browser database visible.
2. Prefer running the original existing HBT page and paste `recovery/hbt_snapshot_exporter.js` into the browser developer console (understood source only); alternatively, open the supplied `HBT_FUSION_WITH_MODEL_EXPORT.html` **using the same origin** (e.g. replace the existing served document path, retaining a backup). This adds a button at the bottom right.
3. Click **Export HBT saved models**. This downloads a local JSON file. Nothing is sent to a server.
4. Run `python scripts/hbt_snapshot_audit.py HBT-original-browser-model-snapshots-....json --report snapshot_audit.json`. The exit code is 0 only when structurally complete original L0 and Fusion states were found; exit 2 means missing state. This is *not* a betting readiness signal.
5. Save the exported JSON outside your browser profile and treat it as sensitive unpublished model data. Keep its original download time, source machine, browser profile and URL as provenance. Do not overwrite old snapshots.

The browser DB is `FootballForecastLab`, stores `models` and `sources`. Important keys are `HBT-0.4a-deploy`, historical `snapshot:<created>`, `layer-result:FUSION10LIVE`, and `layer-result:FUSION09R1`. The original 11 September 2026 L0 target was `2026-09-11T20:30:57.701Z`.

**If these snapshots are absent, the full original *code* is restored but its old trained weights cannot be recovered exactly from code alone.** New training would be a new experimental snapshot, not the immutable original.

## Source-era caveat

The recovered Fusion training path explicitly fetches seasons **2014–15 through 2018–19**; the L1 historical performance source covers 2014–15 through 2019–20. This source should not be confused with a verified modern five-year 2021–2026 Fusion training and evaluation dataset. The earlier L0 handover reports 27,934 historical results, but those aggregate claims are not a new run of the current Fusion model. Its earlier 2019 confirmation is reused, and the source explicitly notes that the full Fusion advantage was modest. Do not report modern live-Fusion profitability from those results.

## Still NOT resolved by source recovery

- Original trained Fusion coefficients have been recovered and preserved; the exact L0 browser deployment snapshot and states have not been recovered from the original browser profile by this package alone.
- No combined L0+Fusion server-side runtime has been deployed or compared point-by-point against the browser app and frozen prospective captures.
- No verified current bookmaker offers and independent lineup proof have been obtained. Provider credentials are absent.
- Five-year point-in-time matched model/odds/results backtests and multi-date clean prospective confirmation remain outstanding.

**No real-money betting and no model promotion.** No unrelated projects are used. All output stays under HBT.
