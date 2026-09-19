#!/usr/bin/env python3
import json,sys,re,unicodedata
from pathlib import Path

def norm(x):
 s=unicodedata.normalize('NFKD',str(x or '')).encode('ascii','ignore').decode().lower()
 return ' '.join(re.sub(r'[^a-z0-9]+',' ',s).split())

def blocked(f):
 s=norm(' '.join(str(f.get(k) or '') for k in ('competition','competitionSlug','home','away')))
 toks=('women','womens','vrouw','vrouwen','female','feminine','femenina','feminino','frauen','ladies','liga f','nwsl','u17','u18','u19','u20','u21','u23','youth','reserve','reserves')
 return any(t in s for t in toks)

def main():
 date=sys.argv[1]
 p=Path(f'hbt_live_data/hbt_base_capture_{date}.json');x=json.load(open(p,encoding='utf-8'))
 rows=[]
 for r in x.get('predictions',[]):
  f=r['fixture'];h,d,a=map(float,r['probs'])
  if blocked(f):
   rows.append({'fixture':f"{f['home']} vs {f['away']}",'kickoffUTC':f.get('time'),'blocked':'IDENTITY_NAMESPACE_NON_MENS','competition':f.get('competition')});continue
  hd=h/(h+a) if h+a else 0;ad=a/(h+a) if h+a else 0
  z={'fixture':f"{f['home']} vs {f['away']}",'home':f['home'],'away':f['away'],'kickoffUTC':f.get('time'),'league':f.get('league'),'competition':f.get('competition'),'tier':r.get('tier'),'quality':r.get('quality'),'coverage':r.get('coverage'),'coveragePack':r.get('coveragePack'),'homeGames':((r.get('resolution') or {}).get('homeState') or {}).get('games'),'homeLast':((r.get('resolution') or {}).get('homeState') or {}).get('lastDate'),'awayGames':((r.get('resolution') or {}).get('awayState') or {}).get('games'),'awayLast':((r.get('resolution') or {}).get('awayState') or {}).get('lastDate'),'H':h,'D':d,'A':a,'1X':h+d,'X2':a+d,'12':h+a,'homeDNB':hd,'awayDNB':ad,'directionalP':max(h,a),'strongestDC':max(h+d,a+d,h+a)}
  rows.append(z)
 valid=[r for r in rows if not r.get('blocked')]
 blocked_rows=[r for r in rows if r.get('blocked')]
 valid.sort(key=lambda q:(q['directionalP'],q['quality']),reverse=True)
 out={'targetDate':date,'sourceCaptureSha256':x.get('immutableSha256'),'counts':{'basePredictions':len(rows),'validMens':len(valid),'blockedNamespace':len(blocked_rows)},'rankedByDirectionalProbability':valid,'blocked':blocked_rows}
 json.dump(out,open(f'hbt_live_data/hbt_base_ranked_{date}.json','w',encoding='utf-8'),indent=2,ensure_ascii=False)
 print(json.dumps({'counts':out['counts'],'top':valid[:20],'blocked':blocked_rows},indent=2,ensure_ascii=False))
if __name__=='__main__':main()
