#!/usr/bin/env python3
"""Transport hardening for HBT-1.3 player-prop training."""
import hbt_collect_live_data as understat_http
import hbt_train_player_props_v4 as train

# Understat AJAX endpoints require X-Requested-With/Referer headers; the live
# performance collector already implements that contract.
train.net.http_json = understat_http.http_json

if __name__ == '__main__':
    raise SystemExit(train.main())
