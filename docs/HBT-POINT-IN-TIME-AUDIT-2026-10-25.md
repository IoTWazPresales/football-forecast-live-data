# HBT point-in-time settlement audit — 25 October 2026

**Isolation:** authoritative \`research/hbt-1.4-match-intelligence\` at \`ae8058c36e5026b686fa6884001f2bc43bd69bd7\`. HBT-1.1.2L-R1, Test A, historical captures, frozen forecasts, odds, staking and unrelated CIP/Reclaim/ASUS work remain unchanged. **No deployment or retuning.**

## Commit-pinned original forecasts

- **23 Oct:** first-add commit \`3be7b0c82a656dd21a6ea8c46444a8a0049257af\` (22 Oct 23:55:07Z); original blob \`a7179d0557eb67a96461d753cb58dcd6cb46973d\`, export 22 Oct 23:55:04.595Z. Five L0-only forecasts.
- **24 Oct:** first-add commit \`9b3cd165a7ab6f87b5c082843b3c16c9cd149648\` (23 Oct 23:32:30Z); original blob \`07d16a744bf17604a99bfadd9262090f877dd795\`, export 23 Oct 23:32:27.690Z. **15 L0-only forecasts, all before their 24 Oct fixtures.** Never substitute the overwritten latest same-path file.
- **25 Oct:** first-add commit \`66a3b8399e276eb36f94371077369e5bc3bd0388\` (24 Oct 22:16:24Z); original blob \`95b74b8c111d96f57da64a01e34c42f9fb1e52e3\`, export 24 Oct 22:16:21.908Z. **17 L0-only forecasts, zero Fusion, zero goal-market outputs**; not yet settled.

All 15 original 24 Oct fixtures matched independently verified **senior men's 90-minute finals**. Evidence: [Sky Sports 24 Oct full scoreboard](https://www.skysports.com/football-scores-fixtures/2026-10-24), [Soccerbase 24 Oct results](https://www.soccerbase.com/matches/results.sd?date=2026-10-24), [Bundesliga Augsburg–Union report](https://www.bundesliga.com/en/bundesliga/news/augsburg-union-berlin-match-report-highlights-matchday-7-massengo-haberer-39708), [Reuters Premier League](https://www.reuters.com/sports/soccer/jackson-double-ends-man-citys-perfect-run-villa-win-2-1-2026-10-24/), [Reuters Bundesliga](https://www.reuters.com/sports/soccer/rb-leipzig-thump-elversberg-bundesliga-philippe-sinks-hamburg-2026-10-24/), [Reuters Serie A](https://www.reuters.com/sports/soccer/roma-rally-draw-3-3-napoli-como-keep-winning-2026-10-24/). The source export/commit preceded the verified Saturday fixtures. **Exact UTC kickoff evidence for each of the 15 is not yet individually recorded in a machine-readable independent manifest**; the new scorer therefore requires this additional evidence before accepting a full governed daily manifest.

| League | Original 24 Oct fixture | 90-min FT | First-add top pick (prob.) | Correct |
|---|---|---|---|---|
| ENG | Aston Villa–Man City | 2–1 | Man City 51.79% | No |
| ESP | Rayo Vallecano–Elche | 0–3 | Rayo 39.12% | No |
| GER | Augsburg–Union Berlin | 1–1 | Augsburg 59.22% | No |
| ENG | Arsenal–Everton | 2–0 | Everton 44.73% | No |
| ENG | Coventry–Fulham | 0–1 | Fulham 45.48% | Yes |
| SCO | Dundee United–Aberdeen | 3–2 | Dundee Utd 47.94% | Yes |
| SCO | Falkirk–Kilmarnock | 3–0 | Falkirk 49.99% | Yes |
| SCO | Rangers–St Johnstone | 4–0 | Rangers 72.67% | Yes |
| SCO | St Mirren–Dundee | 2–1 | St Mirren 55.94% | Yes |
| ITA | Napoli–Roma | 3–3 | Roma 65.09% | No |
| ENG | Chelsea–Tottenham | 0–2 | Chelsea 59.59% | No |
| GER | Dortmund–Frankfurt | 1–0 | Dortmund 69.39% | Yes |
| ESP | Valencia–Villarreal | 1–2 | Villarreal 46.91% | Yes |
| POR | Alverca–Arouca | 0–1 | Alverca 38.11% | No |
| POR | Gil Vicente–Porto | 0–1 | Porto 70.87% | Yes |

## Metrics (first-add probabilities only)

| Metric | 23 Oct N=5 | 24 Oct N=15 | Combined N=20 |
|---|---:|---:|---:|
| Top-pick 1X2 accuracy | 2/5 40.0% | **8/15 53.3%** | **10/20 50.0%** |
| 1X2 unhalved multiclass Brier | 0.61791 | **0.57078** | **0.58256** |
| 1X2 natural log loss | 1.02925 | **0.95752** | **0.97546** |
| 1X Brier / log | 0.27743 / 0.75064 | 0.22308 / 0.62871 | 0.23667 / 0.65919 |
| X2 Brier / log | 0.18151 / 0.54926 | 0.21223 / 0.60778 | 0.20455 / 0.59315 |
| 12 Brier / log | 0.15897 / 0.49842 | 0.13546 / 0.44967 | 0.14134 / 0.46186 |
| BTTS / goal totals | No genuine outputs | No genuine outputs | **Not scoreable** |
| R5 flat-stake ROI | No verified contemporaneous prices/immutable selections | Same | **Unavailable** |

Double chance is derived **algebraically** from the original H/D/A vector, not a separate trained market. Uniform three-class baseline Brier is 0.66667 and log loss 1.09861, for context only. **N=20 is too small and selectively covered for reliability claims.** Top-pick reliability by original max probability: <40%: N=2, mean 38.62%, observed 0%; 40–50%: N=8, mean 46.96%, observed 50%; 50–60%: N=6, mean 55.83%, observed 50%; 60–70%: N=2, mean 67.24%, observed 50%; >=70%: N=2, mean 71.77%, observed 100%. Scottish 24 Oct was 4/4 **despite stale-ish 357–524-day states**; not a basis to trust stale training. England was 1/4; too small to conclude league skill.

**Coverage:** 15/15 is settlement coverage among *forecasted* 24 Oct fixtures, **not** global senior-men fixture coverage. Latest 25 Oct scanner: 343 discovered, **17 fallback, zero full model, 20 insufficient data, 306 unsupported**. Discovery completeness != prediction readiness. All 25 Oct fixtures are unsettled at this audit.

## Engineering blockers, hypothesis and next experiment

1. **Missing full Fusion and goal runtime:** 17 L0-only on 25 Oct. Trace runtime dependencies read-only; require deterministic offline parity before claiming model readiness.
2. **Source-ordered competition identity:** [draft PR #2](https://github.com/IoTWazPresales/football-forecast-live-data/pull/2) is still unmerged. It preserves specific-provider evidence and flags conflicts; run source-order permutations on copied fixtures, never merge automatically.
3. **2026–27 history feed 404:** \`sco.1\`, \`tr.1\`, \`uefa.cl\` still failing. Inspect upstream season routing; do not silently substitute stale history.
4. **Odds provider:** \`ODDS_API_IO_KEY\` remains unconfigured, \`PRICE_SOURCE_UNCONFIGURED\`, zero verified bookmaker prices; do not invent R5 ROI or price-derived bets.
5. **Prospective sample and identity quality:** only N=20, all fallback. Investigate surprising original Arsenal–Everton (Everton 44.73%) and Napoli–Roma (Roma 65.09%) probabilities as **hypotheses**, not immediate retuning triggers.
6. **Dutch DST rollover 25 Oct:** first-add includes Fortuna–Excelsior and PSV–Feyenoord with bare \`OPENFOOTBALL:nl.1\` local clocks. Independently reconcile Europe/Amsterdam to UTC; [draft PR #3](https://github.com/IoTWazPresales/football-forecast-live-data/pull/3) contains a separate source-clock guard, still unmerged.

**New research-only code:** \`scripts/hbt_settlement_metrics_v1.py\` scores 1X2 and algebraic DC with independently supplied UTC kickoff, first-add Git attestation, exact fixture identity, senior-men regulation-time final and external source URLs; rejects post-kickoff/duplicate/invalid cases. It does **not** automatically authenticate source URLs or Git history, retrieve results, calculate odds/ROI, or touch live models. \`tests/test_hbt_settlement_metrics_v1.py\`: **16 offline unit tests passed locally**, covering leakage, duplicate identity, category exclusions, missing markets, scoring and absent results. The table above was calculated separately from original vectors and verified finals; the new generic scorer is not yet an integrated daily pipeline.

**Next:** compile independent exact UTC kickoff manifest for all 24 Oct forecasts and 25 Oct Dutch fixtures, rerun the new scorer against it, then cross-check with this manual audit. Keep all frozen parameters, Test A, captures, PR #2/#3 and other projects untouched.
