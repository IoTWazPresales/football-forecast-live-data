#!/usr/bin/env python3
"""Append last-complete-season league side priors to HBT event parameters."""
from __future__ import annotations
import csv, io, json, urllib.request
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[1];PATH=ROOT/'hbt_live_data'/'event_model_params.json'
LEAGUES={'E0':'en.1','SP1':'es.1','D1':'de.1','I1':'it.1','F1':'fr.1'}
COLS={'corners':('HC','AC'),'yellowCards':('HY','AY'),'shots':('HS','AS'),'shotsOnTarget':('HST','AST'),'redCards':('HR','AR')}
UA='Mozilla/5.0 (compatible; HBT-Event-Priors/1.0)'
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':UA});return urllib.request.urlopen(req,timeout=30).read().decode('utf-8-sig','replace')
def f(x):
 try:return float(x)
 except:return None
def main():
 p=json.load(open(PATH,encoding='utf-8'));priors={};sc='2526'
 for div,league in LEAGUES.items():
  rows=list(csv.DictReader(io.StringIO(get(f'https://www.football-data.co.uk/mmz4281/{sc}/{div}.csv'))));z={}
  for name,(hc,ac) in COLS.items():
   h=[f(r.get(hc)) for r in rows];a=[f(r.get(ac)) for r in rows];h=[x for x in h if x is not None];a=[x for x in a if x is not None]
   z[name]={'homeMean':sum(h)/len(h) if h else None,'awayMean':sum(a)/len(a) if a else None,'n':min(len(h),len(a))}
  priors[league]=z
 p['livePriorsSeason']=2025;p['livePriors']=priors;PATH.write_text(json.dumps(p,separators=(',',':')),encoding='utf-8');print(priors)
if __name__=='__main__':main()
