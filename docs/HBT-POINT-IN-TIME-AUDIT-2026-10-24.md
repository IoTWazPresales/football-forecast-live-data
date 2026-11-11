# HBT point-in-time research note — 24 October 2026

**Isolation:** authoritative base `research/hbt-1.4-match-intelligence` at `95b5e7481336392ff45f6cd4b7e294ca5ab3975d`. No HBT-1.1.2L-R1, Test A, historic capture, odds, betting, CIP, Reclaim or ASUS changes.

## First clean 23 October L0-only settlement

Use the **first-add** of `hbt_live_data/frozen_control_forecast_2026-10-23.json`: commit `3be7b0c82a656dd21a6ea8c46444a8a0049257af` (2026-10-22 23:55:07Z), source export `2026-10-22T23:55:04.595Z`, original blob `a7179d0557eb67a96461d753cb58dcd6cb46973d`. The latest same-path file was overwritten after kickoff and **must not** be used for prospective evaluation.

Five independently checked senior men's 90-minute finals:

| Fixture | FT | Original H/D/A | Top pick |
|---|---:|---:|---|
| Alanyaspor–Kocaelispor | 1–2 | 48.95 / 26.75 / 24.30% | wrong |
| Stuttgart–Mönchengladbach | 2–3 | 43.51 / 26.96 / 29.53% | wrong |
| Torino–Monza | 3–2 | 56.30 / 24.99 / 18.71% | correct |
| Ipswich–Nottingham Forest | 1–1 | 24.19 / 27.64 / 48.17% | wrong |
| Go Ahead Eagles–Telstar | 3–2 | 52.14 / 25.40 / 22.46% | correct |

**N=5:** top-pick accuracy **40%**; unhalved three-class Brier **0.61791**; natural-log loss **1.02925**. Algebraically derived double-chance Brier / log loss: **1X 0.27743 / 0.75064; X2 0.18151 / 0.54926; 12 0.15897 / 0.49842**. This is 5/5 **forecast settlement**, not global fixture coverage. N=5 is not sufficient to establish calibration. No genuine BTTS or goal-total forecast exists. R5 flat-stake ROI **unavailable** (no immutable pre-kickoff selections and verified contemporaneous bookmaker prices).

Independent evidence: [Alanyaspor FT](https://www.ysscores.com/en/match/5904778/Alanyaspor-vs-Kocaelispor), [Stuttgart official FT](https://www.bundesliga.com/en/bundesliga/news/vfb-stuttgart-borussia-monchengladbach-match-report-highlights-matchday-7-39693), [Torino FT](https://www.sofascore.com/news/torino-3-2-monza-belghali-shines-sofascore-rating-8-1), [Ipswich FT](https://www.nbcsports.com/soccer/news/premier-league-schedule-for-2026-27-season-released), [Go Ahead FT](https://www.skysports.com/football/go-ahead-eagles-vs-telstar/live/556771). Independently checked UTC kickoffs were 17:00, 18:30, 18:45, 19:00 and **18:00** respectively.

## New source-clock evidence and test

The original Go Ahead–Telstar row from `OPENFOOTBALL:nl.1` shows **20:00 without a timezone**, whereas independently verified kickoff was **18:00Z / 20:00 Europe/Amsterdam** ([UTC schedule](https://goalsat.com/match/2488-go-ahead-eagles-vs-telstar)). `scripts/hbt_scan_slate_v2_1.py` constructs the OpenFootball kickoff from bare local date/time. This is a provenance ambiguity, **not** evidence of leakage in that match: the first-add commit preceded actual kickoff. A hard-coded UTC offset would fail across the 25 October Dutch DST change.

New research-only `scripts/hbt_source_kickoff_guard_v1.py` verifies an explicitly mapped Dutch timezone against independent UTC evidence; quarantines missing, mismatched, nonexistent and DST-ambiguous clocks. Nine local offline tests passed; no production scanner modification. Operator-supplied evidence URLs are not automatically authenticated by the utility.

## Remaining blockers and next experiment

The first-add 24 Oct snapshot (commit `9b3cd165a7ab6f87b5c082843b3c16c9cd149648`, exported 23 Oct 23:32:27Z) contains **15 L0 fallback** forecasts, **zero full Fusion** and **zero goal-market outputs**. Current scanner: 413 discovered, 15 fallback, 25 insufficient, 373 unsupported; discovery completeness does not mean prediction readiness. Three 2026–27 history feeds (`sco.1`, `tr.1`, `uefa.cl`) still return 404; odds provider `ODDS_API_IO_KEY` is unconfigured, with zero verified prices. [Draft PR #2](https://github.com/IoTWazPresales/football-forecast-live-data/pull/2) is open and unmerged; its source-order competition identity fix remains separate.

**Next:** independently verify 24 Oct kickoff clocks/competition identities for the 15 frozen fallback rows; settle only after regulation-time finals, and run source-order permutation tests for PR #2 without merging. No model retune, promotion, betting or stake increase.
