# HBT market-first decision policy — 6 November 2026

Status: **proposal implemented in isolated research feature branch; not promoted**.
Scope: HBT Football Forecast Lab only. Frozen captures, settled results,
trained weights and bookmaker execution rules are unchanged.

## Business objective

For each discovered fixture on the requested date, enumerate **all supported,
offered and modelled markets**. Show the estimated **unconditional probability of
winning a bet**, independently of its price and value gate. Then add observed
bookmaker odds (when independently and freshly verified) and calculate
expected profit. Do not discard a probability ranking just because odds are
missing, expected value is negative, or the bet cannot yet be staked.

"All markets" means all discoverable market/selection combinations from
configured sources. A fixture may contain *unmodelled* market offerings:
their probabilities must remain **unavailable**, not guessed. Markets unsupported
by the current model (player anytime/first scorer, red card, penalty, etc.)
require dedicated predictors, event rules, data and calibration before they
can appear as probabilities or enter a forecast-based chain.

## Three rankings, never conflated

1. **Highest chance:** rank all model-backed selections by
   `profitProbability` descending, even when odds are absent, the bet is
   negative EV, or funding blockers exist. A DNB refund counts as a push, not
   a win. The shortlist must label model type, evidence and uncertainty.
2. **Highest expected return:** among independently quoted offers, maximize
   `expectedProfitPerRand`, which may be negative. This is a descriptive
   ranking of available prices, not an endorsement or stake instruction.
3. **High-chance value intersection:** among priced markets with
   `expectedProfitPerRand >= 0`, maximize win probability, and show its
   expected profit and all funding blockers. The existing more restrictive
   R1/R2 minimum-EV and evidence gates are shown separately, not used to hide
   the first two rankings.

Expose all model-backed markets in the per-fixture table sorted by estimated
win probability, with market family, price/quote timestamp, win/push/loss,
fair odds, estimated return per R1, bookmaker and execution blockers.
A global daily leader view may surface the most likely bet per scored fixture.
Every discovered but unscored fixture remains visible as **unscored**, and
must not receive invented percentages.

## Probability, price and profit

For a non-push market with modelled win probability `p` and decimal price
`o`: expected net profit per R1 staked is `p * (o - 1) - (1-p)`.
For a DNB market with win `w`, push `d` and loss `l`:
expected net profit per R1 is `w * (o - 1) - l`.
Show the probability of a *win* and a *non-loss* separately.

A low-odds high-probability bet can be negative expected value. Profitability
cannot be calculated without real quotes. Bookmaker implied probabilities
are a useful calibration comparator but never silently replace HBT's own
model forecast or become its football-feature input.

## Chains

Present 2–4-leg same-day **research chains**, with distinct fixtures, selected
from the supported market probability board including validated event markets.
Return individual legs, quote timestamps, combined decimal odds only when all
legs are quoted, approximate joint win probability, expected return, and risk
and uncertainty flags. Preserve the Frechet probability bounds and the explicit
`dependenceValidated=False` and `stakeReady=False` flags until genuine
joint calibration exists.

Joint probability under independence is only an assumption, not an approved
estimate. Shared-team, competition, time or model risks can correlate legs.
Same-game combinations must never be calculated by multiplying marginal
probabilities; they require separately estimated and validated joint outcomes.
DNB/push legs require a refund-state settlement model before they can enter
standard all-win parlay calculations.

More legs produce a larger payout only if all legs win; they generally lower
the chance of an all-win ticket. Never imply that chaining turns a
negative-value selection into a positive-value bet.

## Funding/alert separation

A market is eligible to **display** as soon as a validated, attributable
model probability exists. This is not permission to recommend a real-money
stake. The live decision must explicitly retain R1/R2 provenance, clean
prospective performance, independent kickoff/fixture identity, confirmed-XI
where required, stale-data checks, quote freshness, market eligibility and
chain dependence. Never invent bookmaker odds or call absent sources zero.

If the selection is not verified and stake-ready, show **WATCH / RESEARCH /
INSUFFICIENT DATA** with blockers. Even high-probability bets are not certain.

The existing hourly readiness alert remains unchanged unless separately
reviewed; research-market discovery and funded betting authorization are
different workflows. Do not auto-place wagers, change stakes, override frozen
history, or promote models.

## Verified inventory at policy creation

- Existing research desk: 1X2, DC, DNB; goal distributions only when supplied;
  event totals only with held-out evidence; 2–4 leg research chains.
- Missing operational capabilities: full live Fusion/score-model runtime in
  this repository, complete player and referee-event models, fresh verified
  bookmaker quotes (current price source unconfigured), comprehensive
  calibration and validated chains.
- Scope isolation: HBT only; no CIP, Reclaim or other project inputs.

## Implementation in this feature branch

- Include every supported modelled market in chance-first table by default,
  sorted by unconditional win probability and with EV displayed separately.
- Store `highestProbabilityMarket`, `highestQuotedExpectedReturnMarket`,
  `highestProbabilityNonnegativeEVMarket` on each scored fixture.
- Add `dailyProbabilityLeaders`, without filtering on R1/R2 funding status.
- Permit eligible model-backed event markets into probability-first *shadow*
  chain search; keep original funding blocks and no automatic stakes.
- Regression tests cover event-market eligibility in shadow chains and
  probability-first versus EV ordering.

## Next implementation gaps, not solved by ranking changes

1. Restore reliable forecast coverage (104 discovered, two L0 fallback,
   zero full-model forecasts in the 6 November snapshot).
2. Configure a legitimate price source and validate quotes per fixture and
   market selection, period and time.
3. Restore score probabilities, and independently model player scorer,
   first scorer, red cards and other offered event markets.
4. Improve pre-kickoff independent captured/settled prospective evidence,
   model calibration and probability intervals.
5. Extend pairing/search to market-aware chains with independently verified
   joint dependence and proper settlement rules before any funded suggestion.
