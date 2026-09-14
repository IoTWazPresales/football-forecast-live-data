#!/usr/bin/env python3
"""Final transport wrapper for HBT-1.3 live market intelligence."""
from typing import Any
import time
import hbt_collect_live_data as xhr
import hbt_collect_market_intelligence_v4_runtime as run


def xhr_understat_players(league:str,year:int,cache:dict[str,Any])->list[dict[str,Any]]:
    code=run.v4.UNDERSTAT.get(league)
    if not code:return []
    key=f'xhr|{code}|{year}';old=(cache.get('understat') or {}).get(key);now=time.time()
    if old and now-float(old.get('cachedAt') or 0)<12*3600:return old.get('players') or []
    try:
        raw=xhr.http_json(f'https://understat.com/getLeagueData/{code}/{year}',25,2)
        rows=raw.get('players') or [] if isinstance(raw,dict) else []
        cache.setdefault('understat',{})[key]={'cachedAt':now,'players':rows}
        return rows
    except Exception:return (old or {}).get('players') or []

run._original_understat=xhr_understat_players
run.v4.understat_players=run.robust_understat_players

if __name__=='__main__':
    raise SystemExit(run.main())
