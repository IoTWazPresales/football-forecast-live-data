#!/usr/bin/env python3
"""HBT slate scanner 2.3 identity hardening.

League-specific feeds are placed before ESPN_ALL so deduplication preserves
leagueHint/competition identity when both sources discover the same fixture.
This does not create or alter probabilities.
"""
from __future__ import annotations

import hbt_scan_slate_v2_1 as v

v.base.VERSION = "HBT-SLATE-SCANNER-2.3-IDENTITY"

# Add the five native top-flight model leagues so generic ESPN_ALL rows cannot
# erase their competition identity during merge/deduplication.
v.ESPN_LEAGUES.update({
    "en.1": ("eng.1", "Premier League"),
    "es.1": ("esp.1", "LaLiga"),
    "de.1": ("ger.1", "Bundesliga"),
    "it.1": ("ita.1", "Serie A"),
    "fr.1": ("fra.1", "Ligue 1"),
})


def parse_discovery_bundle(date):
    rows = []
    components = []
    successes = 0

    # Specific competition sources first. base.merge_sources keeps the first
    # occurrence's competition/leagueHint, so precedence is intentional.
    providers = [
        (f"ESPN:{c}", lambda c=c, s=s, l=l: v.espn_league(date, c, s, l))
        for c, (s, l) in v.ESPN_LEAGUES.items()
    ]
    providers += [
        (f"THESPORTSDB:{c}", lambda c=c, i=i, l=l: v.sportsdb_league(date, c, i, l))
        for c, (i, l) in v.SPORTSDB_LEAGUES.items()
    ]
    providers += [
        (f"OPENFOOTBALL:{c}", lambda c=c, l=l: v.openfootball_league(date, c, l))
        for c, l in v.OPENFOOTBALL_LEAGUES.items()
    ]
    providers.append(("ESPN_ALL", lambda: v._ORIG_ESPN(date)))

    for name, fn in providers:
        try:
            got, audit = fn()
            rows.extend(got)
            components.append(audit)
            successes += 1
        except Exception as exc:
            components.append({
                "source": name, "fetchedAt": v.base.now(), "status": "failed",
                "events": 0, "error": str(exc)[:240]
            })
    if not successes:
        raise RuntimeError("all discovery sources failed")
    return rows, {
        "source": "HBT_DISCOVERY_BUNDLE", "fetchedAt": v.base.now(),
        "status": "loaded", "events": len(rows),
        "successfulComponents": successes, "components": components,
    }


v.base.parse_espn = parse_discovery_bundle

if __name__ == "__main__":
    raise SystemExit(v.base.main())
