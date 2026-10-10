# HBT Saturday execution gates — 2026-10-10

Scope: research branch `research/hbt-1.4-match-intelligence` only. HBT-1.1.2 frozen predictive snapshot, coefficients, feature state and prospective football probabilities remain unchanged.

## Verified design problems

1. v1.3 ranked the highest raw market EV before governance; a quarantined market could hide a valid lower-EV alternative.
2. Pre-XI and L0 fallback forecasts could satisfy the original price/quality stake policy despite not being validated full-model confirmed-XI decisions.
3. Scanner `verified: true` meant scanner identity matched; it did **not** prove independently checked kickoff time. Ajax–NEC on 10 Oct demonstrated why this distinction matters.
4. Flat price rows previously lacked strict freshness, bookmaker, event identity and target-date checks. Provider fixture matching tolerated up to 12 hours.
5. An automatically funded accumulator could rely on an unvalidated independence assumption.
6. Corners, cards, shots and SOT exist in separate event intelligence; the 1X2/DC execution surface does not automatically value or fund those markets.

## Implemented downstream controls

- The existing `scripts/hbt_execution_surface_v1_3.py` now produces `fullMarketDecisionAudit` for all scored 1X2 and double-chance outcomes, with distinct most-likely outcome, conditional value, and high-probability chain role.
- Market choice favours a governance-eligible value candidate ahead of a higher raw-EV but quarantined candidate.
- Staking is R0 for non-FULL_MODEL, non-CONFIRMED_XI_READY, stale-coverage or missing-match-intelligence rows.
- Odds must be attributable to one bookmaker + event, the matching scanner date, and a price feed collected no more than 15 minutes ago.
- The odds collector uses strict two-team matching, at most 15 minutes difference in kickoff, and rejects non-scheduled/live provider events.
- An independently sourced kickoff confirmation is required for **execution**; otherwise the fixture is still shown for research but blocked.
- Auto-funded chains are disabled until a validated dependence/correlation assessment exists; shadow chains remain research only.
- `tests/test_hbt_governed_bet_execution.py` adds targeted regression checks.

## Independent kickoff evidence contract

Optional file: `hbt_live_data/hbt_independent_kickoffs_YYYY-MM-DD.json`

```json
{
  "targetDate": "2026-10-10",
  "confirmations": [
    {
      "home": "Ajax",
      "away": "NEC",
      "kickoffUtc": "2026-10-10T19:00:00Z",
      "independentSource": "club official fixture page",
      "sourceUrl": "https://english.ajax.nl/games/",
      "verifiedAt": "2026-10-10T09:00:00Z"
    }
  ]
}
```

This example would **block** an erroneously recorded scanner kickoff of 21:00Z; it does not silently rewrite the fixture or model prediction. A proper independent crosscheck collection process must still be integrated.

## Validation / release gate

- Run: `python -m unittest discover -s tests -p 'test_hbt_governed_bet_execution.py'`
- Run the full existing HBT guard and parity suites.
- Rerun the collector/scanner, frozen bridge and Saturday prospective execution workflow with target-date-consistent inputs.
- Verify real, independently sourced kickoffs, confirmed XI, current legitimate market prices, market identity and freshness **before** allowing stakes.
- No production model promotion or live funded execution is authorized by these changes.

**Not yet complete:** automated official fixture crosschecks, end-to-end event-market pricing, fixture-by-fixture empirical calibration and dependence modeling, and an observed passing CI run on the new code. Do not treat the research dashboard or R0 shadow chains as stake-ready.
