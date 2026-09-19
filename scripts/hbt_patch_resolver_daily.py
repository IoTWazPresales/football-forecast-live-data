#!/usr/bin/env python3
from __future__ import annotations
import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

OUT=Path('scripts/.hbt_resolver_v3_tmp.mjs')

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--date',required=True);a=ap.parse_args()
    d=dt.date.fromisoformat(a.date)
    subprocess.run([sys.executable,'scripts/hbt_patch_resolver_v3.py'],check=True)
    s=OUT.read_text(encoding='utf-8')
    tag=d.strftime('%d%b').upper()
    s=s.replace('2026-09-18',a.date).replace('18SEP',tag)
    OUT.write_text(s,encoding='utf-8')
    print(f'daily resolver patched for {a.date} ({tag})')
    return 0
if __name__=='__main__':raise SystemExit(main())
