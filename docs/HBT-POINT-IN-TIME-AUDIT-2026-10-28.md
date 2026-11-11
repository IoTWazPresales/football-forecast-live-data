# HBT point-in-time research audit — 2026-10-28 (Africa/Johannesburg)

## Scope and immutable evidence
- Authoritative branch `research/hbt-1.4-match-intelligence`, inspected at `9548671851545996e1501baa115099c56ae13125` (2026-10-28 05:55:01 UTC). HBT-1.1.2L-R1 and Test A unchanged.
- 27 Oct first-add forecast: commit `24d2bb8016425b6ec99a8e9b5920220f6c76518d` (00:52:15 UTC), forecast blob `cd5a3356b864ef2999893d74a19f419ba752aade`, exported 00:52:13 UTC; **zero predictions**. Same-run scanner blob `20c8b04a5d074cc7599550a857efb2bd2535245d`: 102 discovered, 3 Italian Serie A `INSUFFICIENT_DATA`, 99 unsupported. No retrospective probability assignment.
- 28 Oct first-add forecast: commit `c02efaa73c644aad905a624c87214794d45909f6` (00:16:57 UTC), forecast blob `6a67368af87635365581c69ee73b45bde55193d1`, exported 00:16:54 UTC; 8 L0 fallback, zero full Fusion. Same-run scanner blob `e58834ae174a3758c33c1fc118cc31b36d776109`: 180 discovered, 8 fallback, 8 insufficient, 164 unsupported. Source-listed earliest kickoff 17:30 UTC; independent kickoff confirmation remains outstanding.
- 28 Oct same-run bridge-status blob `d81778b1ecb387d49e8b2ee8b0dfcea20f60208b` reports six excluded fixtures, **three Brazilian Serie A fixtures incorrectly tagged `it.1`**. Scanner independently labels these fixtures `2026-brasileiro-serie-a`. This is **cross-competition metadata contamination in the bridge's excluded/identity surface**, not evidence of a scored Brazilian fixture or contaminated training.
- Scanner additionally classifies **five** `2026-brasileiro-serie-a` fixtures as `INSUFFICIENT_DATA` for the Italian full-model support contract, despite Brazil not being in `FULL_MODEL_LEAGUES`. Source: `scripts/hbt_scan_slate_v2.py`, `full_model_comp`: `any(x in s or s in x for x in FULL_MODEL_SLUGS if s)`, where `FULL_MODEL_SLUGS` contains unqualified `serie a`. The active scanner artifact is version 2.2. This false support classification inflates the reported supported-league gap count from the actual 3 Italian fixtures to 8. Draft PR #2 does not modify `full_model_comp` or the frozen bridge.

## Verified settled results and performance
27 Oct Italian Serie A regulation-time results: Sassuolo 2–6 Lazio, AS Roma 4–2 Cagliari, Torino 1–3 Como. Independently corroborated by Reuters (2026-10-27) and Sky Sports' October Serie A scoreboard. All three were among the original scanner's `INSUFFICIENT_DATA` fixtures and had **zero original 1X2 predictions**. Known Italian Serie A forecast coverage: **0/3**. No new 1X2 accuracy, Brier, log loss, reliability/calibration, or DC settlement metrics can be computed for this date. No genuine BTTS or goal-total forecasts. No verified contemporaneous bookmaker prices, so R5 flat-stake ROI remains unavailable.

Cumulative 23–26 Oct performance carried forward from prior audit, **provisional** pending independently machine-readable settlement manifest: 38 L0 fallback forecasts, 21 correct 1X2 (55.3%), approximate unhalved Brier 0.61245 and log loss 1.01805. Do not present as Fusion performance or betting readiness. The 27 Oct zero-prediction day adds no scored observation.

## 28 Oct forecast quality
Eight original forecasts: two Italian Serie A, six Scottish Premiership; all L0 fallback, no full Fusion. **Seven of eight** show `stale-ish` coverage, including AC Milan–Bologna at 2,278 days, St Johnstone–Motherwell at 528 days and five Scottish matches at ~361–364 days. No full prospective performance can be inferred until regulation-time settlement. The three 2026–27 history feeds `sco.1`, `tr.1`, `uefa.cl` still report HTTP 404; market prices remain `PRICE_SOURCE_UNCONFIGURED` (zero priced fixtures).

## Hypothesis and next engineering experiment
Hypothesis: generic `serie a` substring matching plus a bridge fixture-to-league association issue independently cause false support classification and `it.1` labels on Brazilian exclusions. Reproduce source-order permutations using 27–28 Oct first-add fixtures; replace substring league inference with explicit provider-backed, country-qualified competition IDs **in a separately reviewed future change**. Before touching any runtime, prove (a) Brazilian fixtures cannot enter Italian history/predictions, (b) unresolved country labels fail closed, (c) all eight 28 Oct genuine forecasts remain byte-identical, (d) PR #2's source-order logic and PR #5's category guard remain compatible. Never alter the immutable model, historical captures or protected artifacts.

## Research-only diagnostic
`scripts/hbt_competition_provenance_audit_v1.py` compares same-run scanner, bridge-status and forecast JSON supplied by caller; it flags explicit Brazil/Italy identity conflicts and never infers from bare `Serie A`. **14 offline synthetic regression tests passed** via `python -m unittest discover -s tests -p 'test_hbt_competition_provenance_audit_v1.py' -v`. Tests do not authenticate the Git source clock or replace independent results verification. No deploy, retune, merge or betting action authorized.

## PR state and isolation
Draft PR #2 competition identity, #3 clock provenance, #4 settlement metrics, #5 category leakage and #6 empty-snapshot readiness were open/unmerged at audit time. No unrelated projects (CIP, Reclaim, ASUS) accessed or modified. Research additions are isolated and must remain draft until independent review.

## External verification
- Reuters, 27 Oct 2026: https://www.reuters.com/sports/soccer/lazio-move-clear-top-6-2-win-over-10-man-sassuolo-2026-10-27/
- Sky Sports, Serie A October 2026: https://www.skysports.com/serie-a-scores-fixtures/2026-10-01
