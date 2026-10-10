# Football Forecast Live Data

Public, machine-generated live intelligence feed for the HBT Football Forecast Lab.

The research branch contains collectors, governance scripts and a hash-verified
recovered frozen L0 snapshot bridge. It does not contain an operational complete
Fusion/goal-distribution app runtime or bookmaker credentials.

The feed is refreshed by GitHub Actions and consumed read-only by the local Forecast Lab.

Generated files live under `hbt_live_data/`.

On the research branch, build the complete market/coverage desk with:

```bash
python scripts/hbt_build_betting_desk_v1.py --date YYYY-MM-DD
```

The resulting `hbt_betting_desk_YYYY-MM-DD.json` and `.html` distinguish modelled
markets, verified current bookmaker offers, readiness blockers and shadow chains.
Missing data stays unavailable. The desk never places bets, guarantees wins,
promotes a research model or rewrites historical forecasts.

See `docs/HBT-BETTING-READINESS-2026-10-10.md` for the audit and remaining gates.
