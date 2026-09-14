#!/usr/bin/env python3
"""Transport hardening for HBT 2018 tactical/travel extraction."""
import hbt_collect_live_data as understat_http
import hbt_extract_tactical_travel_2018 as extract

# Its Understat calls require the AJAX headers already implemented by the main
# performance collector. ESPN/Open-Meteo calls also tolerate this helper.
extract.p.http_json = understat_http.http_json

if __name__ == '__main__':
    raise SystemExit(extract.main())
