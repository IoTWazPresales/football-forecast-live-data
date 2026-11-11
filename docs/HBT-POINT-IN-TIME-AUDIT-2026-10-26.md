# HBT point-in-time research audit — 26 October 2026

**Isolation:** Authoritative `research/hbt-1.4-match-intelligence`; HBT-1.1.2L-R1, Test A, historic captures, frozen parameters, betting stakes, deployments and unrelated projects unchanged. This PR is **draft and research-only**.

## Critical discovery: women's fixtures were ranked as men's L0 predictions

The **first-add 25 October** frozen forecast contains **17 L0 fallback predictions**. The same-run scanner explicitly identifies **two** as `2026-27-vrouwen-eredivisie`, but nevertheless reports `FALLBACK`, `rankEligible=true`, `hbtLeague=nl.1`:

| Original forecast fixture | Scanner competition | ESPN event | Correct action |
|---|---|---|---|
| FC Utrecht–ADO Den Haag | `2026-27-vrouwen-eredivisie` | `401882145` | Quarantine women's match |
| PEC Zwolle–FC Twente | `2026-27-vrouwen-eredivisie` | `401882144` | Quarantine women's match |

The third women's Heerenveen–AZ fixture (`401882146`) was classified unsupported, showing the error is **selective**. This is **confirmed prediction/ranking category contamination**, not evidence that women's *training results* entered the model. Training lineage needs a separate audit. Independently verified by [FC Twente official women's schedule](https://fctwente.nl/wedstrijden/vrouwen), [25 October women's fixtures](https://www.footballfixtures.org/eredivisie-women/fixtures?view=all) and [25 October scoreboard women's division](https://kickoffscore.com/matches/2026-10-25).

**First-add provenance:** commit `66a3b8399e276eb36f94371077369e5bc3bd0388` (2026-10-24 22:16:24Z); original frozen blob `95b74b8c111d96f57da64a01e34c42f9fb1e52e3`, exported 2026-10-24 22:16:21.908Z; same-run scanner blob `dbd96eccc9ca8a4420bc9da21ab3a29cdb3988e2`, generated 2026-10-24 22:16:23Z. Later overwritten same-path snapshots (including 25 Oct 19:54Z) are **not** valid substitutes for the first-add forecast.

## 25 October senior-men's 90-minute settlement

Original 17 forecasts = **15 independently verified senior-men results + 2 explicit women's quarantines**. The original export and first-add commit precede all 15 verified UTC kickoffs. Dutch local clocks on the **25 October DST transition**: Fortuna–Excelsior 12:15 CET = **11:15Z**; PSV–Feyenoord 14:30 CET = **13:30Z**.

| League | Fixture | FT | Original top pick | Hit |
|---|---|---|---|---|
| SCO | Hibernian–Celtic | 1–2 | Celtic | Y |
| NED | Fortuna–Excelsior | 1–0 | Fortuna | Y |
| ESP | Athletic–Getafe | 4–0 | Athletic | Y |
| TUR | Konyaspor–Gençlerbirliği | 2–0 | Konyaspor | Y |
| ENG | Palace–Newcastle | 0–2 | Newcastle | Y |
| ENG | Hull–Brentford | 1–1 | Brentford | N |
| ENG | Liverpool–Brighton | 2–0 | Liverpool | Y |
| ENG | Man United–Bournemouth | 0–3 | Man United | N |
| SCO | Motherwell–Hearts | 0–2 | Hearts | Y |
| NED | PSV–Feyenoord | 1–1 | PSV | N |
| FRA | Auxerre–Le Mans | 1–1 | Auxerre | N |
| ENG | Sunderland–Leeds | 0–0 | Leeds | N |
| POR | Rio Ave–Famalicão | 0–4 | Famalicão | Y |
| ESP | Barcelona–Real Madrid | 1–2 | Real Madrid | Y |
| POR | Sporting CP–Académico Viseu | 1–2 | Sporting | N |

Independent results and UTC kickoff: [KickoffScore 25 Oct](https://kickoffscore.com/matches/2026-10-25), [Soccerbase 25 Oct](https://www.soccerbase.com/matches/results.sd?date=2026-10-25), [Reuters EPL](https://www.reuters.com/sports/soccer/liverpool-grab-home-win-man-united-slump-another-defeat-pressure-mounts-carrick-2026-10-25/).

**N=15:** 1X2 accuracy **9/15 (60.0%)**, **unhalved multiclass Brier 0.64373**, natural log loss **1.05576**. Algebraic double-chance Brier/log: **1X 0.23821/0.66613; X2 0.20638/0.59960; 12 0.19914/0.58984**. Top-pick reliability: <40% N5 (mean 37.15%, hit 80%); 40–50% N8 (mean 46.61%, hit 50%); 50–60% N1 (51.22%, hit 100%); 60–70% N1 (68.25%, hit 0%); >=70% N0. All too sparse for calibration claims.

**Provisional cumulative 23–25 Oct**, combining the 23–24 Oct N20 in [draft PR #4](https://github.com/IoTWazPresales/football-forecast-live-data/pull/4): **N35, 19/35 = 54.29%, Brier 0.60878, log loss 1.00987**; DC Brier 1X 0.23733, X2 0.20533, 12 0.16611. Requires external machine-readable kickoff/result manifest before claiming automated scorer parity. 15/15 is valid-forecast settlement, **not global match coverage**. No genuine BTTS/goal-total outputs. **R5 flat-stake ROI unavailable** without verified contemporaneous bookmaker prices and immutable selections.

## Outstanding blockers and next experiment

First-add **26 Oct** file (`8923c6a6861eca29fbe1fb1bbe76f028855321f8`) contains **3 unsettled L0 fallback** forecasts, **zero Fusion**, zero goal outputs. Current scanner: 40 discovered, 3 fallback, 4 insufficient, 33 unsupported. Three history feeds `2026-27/sco.1`, `tr.1`, `uefa.cl` still return 404. Odds provider is `PRICE_SOURCE_UNCONFIGURED`; `ODDS_API_IO_KEY` absent. Draft PRs [#2 competition identity](https://github.com/IoTWazPresales/football-forecast-live-data/pull/2), [#3 source-clock guard](https://github.com/IoTWazPresales/football-forecast-live-data/pull/3), [#4 settlement metrics](https://github.com/IoTWazPresales/football-forecast-live-data/pull/4) remain unmerged.

**This PR adds a read-only diagnostic**, `scripts/hbt_category_leakage_audit_v1.py`, which checks caller-supplied commit-pinned Git blob hashes, reconciles original forecasts with same-run scanner identity, and quarantines explicit women/youth/reserve/college labels even when the scanner marks a forecast rank-eligible. Unknown or ambiguous competition identity stays unresolved. **11 offline tests passed**. It does **not** automatically authenticate first-add Git history, verify result URLs, score matches, change operational ranking, or edit frozen artifacts.

**Next:** add fail-closed explicit category exclusion **before** scanner `classify()`'s L0/Fusion branches and independently before execution/forecast capture, with source-order permutations alongside PR #2; audit men's training input lineage separately. Do not merge or deploy automatically.
