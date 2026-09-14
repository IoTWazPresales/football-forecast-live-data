#!/usr/bin/env python3
"""Identity-hardened entrypoint for HBT-1.4 historical intelligence.

Patches only canonical team-key normalization; all causal feature logic remains in
hbt_extract_match_intelligence_v5. This exists because Football-Data and frozen HBT
use club prefixes/suffixes that Understat often omits (RC/SC/SD/CD/OGC/OSC/etc.).
"""
from __future__ import annotations
import re, unicodedata
import hbt_extract_match_intelligence_v5 as base

GENERIC={
 'fc','cf','afc','ac','ssc','sc','rc','sd','cd','ud','acf','ogc','osc','hsc','sco','ea','fsv','tsg','bsc','uc','us','ss','as','sv','vfb','vfl',
 'club','clube','football','futbol','fussball','calcio','societa','sportiva','de','do','del','the','stade','olympique','girondins'
}
ALIASES={
 'internazionale milano':'inter','internazionale':'inter','inter milan':'inter',
 'paris saint germain':'psg','paris sg':'psg',
 'marseille':'marseille','lyonnais':'lyon','rennais':'rennes',
 'strasbourg alsace':'strasbourg','deportivo alaves':'alaves','alaves':'alaves',
 'borussia monchengladbach':'monchengladbach','borussia m gladbach':'monchengladbach','m gladbach':'monchengladbach',
 'bayern munich':'bayern','bayern munchen':'bayern','tottenham hotspur':'tottenham',
 'wolverhampton wanderers':'wolves','leicester city':'leicester','manchester united':'man united','manchester city':'man city',
 'newcastle united':'newcastle','west ham united':'west ham','brighton and hove albion':'brighton',
 'real betis balompie':'betis','real betis':'betis','athletic club':'athletic bilbao',
 'hellas verona':'verona','chievo verona':'chievo','hamburger':'hamburg','koln':'cologne',
 'rasenballsport leipzig':'leipzig','rb leipzig':'leipzig','1899 hoffenheim':'hoffenheim',
 '1 mainz 05':'mainz 05','mainz 05':'mainz 05','nimes olympique':'nimes'
}

def key(s:str)->str:
    s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower().replace('&',' and ')
    toks=[t for t in re.sub(r'[^a-z0-9]+',' ',s).split() if t not in GENERIC and not t.isdigit()]
    k=' '.join(toks)
    return ALIASES.get(k,k)

base.key=key

if __name__=='__main__':
    raise SystemExit(base.main())
