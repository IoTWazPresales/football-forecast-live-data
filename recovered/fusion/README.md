# HBT Fusion runtime recovery kit — 30 October 2026

## What this restores

The actual original single-file HBT browser application's Fusion / PRE-XI / confirmed-XI and L4 score-model **source code**. This was recovered from the user's own HBT Library files. It is not a newly generated or approximated replacement.

The exact original source is `recovery/HBT_1_2R_R4_FROZEN_SNAPSHOT_RECOVERY.html`; SHA-256 `8d139104722ea51171c2a473f80ed69dfea6b2ba08466b39b7e95fafc9514de7`. Identical code is preserved in the dedicated GitHub branch `recovery/hbt-fusion-source-20261030`, Git blob `8d68270a2d99170faa3fe4023396fb301e1904cc`.

`recovery/HBT_FUSION_WITH_MODEL_EXPORT.html` adds **only** a read-only button, **Export HBT saved models**. It does not change training, inference, forecast probabilities, betting gates or stored records. The exporter is also available separately as `recovery/hbt_snapshot_exporter.js`.

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

- No original deployed browser snapshot has been recovered from the user's current browser profile by this package alone.
- No identical server-side runtime has been deployed or compared point-by-point against the browser app and frozen prospective captures.
- No verified current bookmaker offers and independent lineup proof have been obtained. Provider credentials are absent.
- Five-year point-in-time matched model/odds/results backtests and multi-date clean prospective confirmation remain outstanding.

**No real-money betting and no model promotion.** No unrelated projects are used. All output stays under HBT.
