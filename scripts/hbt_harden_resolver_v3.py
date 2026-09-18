from pathlib import Path

P=Path('scripts/.hbt_resolver_v3_tmp.mjs')
s=P.read_text(encoding='utf-8')

def rep(old,new,label):
    global s
    if old not in s:
        raise SystemExit(f'hardening anchor not found: {label}')
    s=s.replace(old,new,1)

# Repair the two dotted keys emitted by the first resolver-v3 patch builder.
s=s.replace("const FD={pl.1:'POL',ie.1:'IRL'};", "const FD={'pl.1':'POL','ie.1':'IRL'};")

old="""const C1_CODES=new Set(['en.2','es.2','it.2','be.1','pl.1','ie.1']);
const EXTRA_LEAGUE_LABELS=["""
new="""const C1_CODES=new Set(['en.2','es.2','it.2','be.1','pl.1','ie.1']);
const MODEL_NATIVE_CODES=new Set(['en.1','es.1','de.1','it.1','fr.1','nl.1','pt.1','sco.1','tr.1','uefa.cl']);
const EXTRA_LEAGUE_LABELS=["""
rep(old,new,'model-native code set')

old=r'''function fixtureLeague(row,hbtLeagueIndex){
 const date=String(row.kickoff||row.date||'').slice(0,10),k=fixtureKey(date,row.home,row.away),fromIntel=hbtLeagueIndex.get(k);if(fromIntel)return fromIntel;
 if(row.leagueHint)return String(row.leagueHint);
 const txt=normText(row.competition||row.competitionSlug||'');
 for(const [code,labels] of [...LEAGUE_LABELS,...EXTRA_LEAGUE_LABELS])if(labels.some(x=>txt===normText(x)||txt.includes(normText(x))))return code;
 return null;
}'''
new=r'''function fixtureLeague(row,hbtLeagueIndex){
 const date=String(row.kickoff||row.date||'').slice(0,10),k=fixtureKey(date,row.home,row.away),fromIntel=hbtLeagueIndex.get(k);if(fromIntel)return fromIntel;
 if(row.leagueHint)return String(row.leagueHint);
 const txt=normText(row.competition||row.competitionSlug||'');
 // Explicit lower divisions must be recognized before generic top-flight labels.
 if(txt.includes('german 2 bundesliga')||txt.includes('2 bundesliga'))return 'de.2';
 if(txt.includes('keuken kampioen divisie'))return 'nl.2';
 if(txt.includes('ligue 2'))return 'fr.2';
 if(txt.includes('scottish championship'))return 'sco.2';
 for(const [code,labels] of [...EXTRA_LEAGUE_LABELS,...LEAGUE_LABELS])if(labels.some(x=>txt===normText(x)||txt.includes(normText(x))))return code;
 return null;
}'''
rep(old,new,'league identity order')

old=r'''function stateResolve(states,name){
 const b=baseTeamKey(name);if(states.has(b))return b;
 const direct=teamKey(name);if(states.has(direct))return direct;
 const sig=identitySignature(name);if(!sig)return null;
 const exact=[],partial=[];
 for(const [k,st] of states){
   const ss=identitySignature(st?.display||k);if(!ss)continue;
   if(ss===sig)exact.push(k);
   else if(sig.length>=5&&ss.length>=5&&(ss.endsWith(' '+sig)||sig.endsWith(' '+ss)||ss.includes(sig)||sig.includes(ss)))partial.push(k);
 }
 if(exact.length===1)return exact[0];
 const u=[...new Set(partial)];return u.length===1?u[0]:null;
}'''
new=r'''function stateResolve(states,name){
 const b=baseTeamKey(name);if(states.has(b))return b;
 const direct=teamKey(name);if(states.has(direct))return direct;
 const sig=identitySignature(name);if(!sig)return null;
 const exact=[],partial=[];
 for(const [k,st] of states){
   const ss=identitySignature(st?.display||k);if(!ss)continue;
   if(ss===sig)exact.push(k);
   else if(sig.length>=5&&ss.length>=5&&(ss.endsWith(' '+sig)||sig.endsWith(' '+ss)||ss.includes(sig)||sig.includes(ss)))partial.push(k);
 }
 const freshest=keys=>keys.slice().sort((a,b)=>{
   const A=states.get(a),B=states.get(b),ad=String(A?.lastDate||''),bd=String(B?.lastDate||'');
   if(ad!==bd)return bd.localeCompare(ad);return (B?.hist?.length||0)-(A?.hist?.length||0);
 })[0]||null;
 // Multiple state keys with the same exact club signature are duplicate aliases,
 // not distinct clubs. Prefer the freshest state rather than failing identity.
 if(exact.length)return freshest(exact);
 const groups=new Map();for(const k of partial){const ss=identitySignature(states.get(k)?.display||k);if(!groups.has(ss))groups.set(ss,[]);groups.get(ss).push(k);}
 if(groups.size===1)return freshest([...groups.values()][0]);
 return null;
}'''
rep(old,new,'duplicate alias resolver')

old="""      const league=fixtureLeague(r,intelLeague),isC1=!!(league&&C1_CODES.has(league)),useDeploy=isC1?c1Packs.get(league):deploy;
      if(isC1&&!useDeploy){excluded.push({fixture:`${r.home} vs ${r.away}`,league,reason:'C1 state pack unavailable',competition:r.competition||r.competitionSlug||null});continue;}"""
new="""      const league=fixtureLeague(r,intelLeague),comp=normText(r.competition||r.competitionSlug||''),genericAmbiguous=!league&&!r.leagueHint&&['regular season','fall season','first stage'].includes(comp);
      if(genericAmbiguous){excluded.push({fixture:`${r.home} vs ${r.away}`,league:null,reason:'ambiguous generic competition identity',competition:r.competition||r.competitionSlug||null});continue;}
      const isC1=!!(league&&C1_CODES.has(league));
      if(league&&!MODEL_NATIVE_CODES.has(league)&&!isC1){excluded.push({fixture:`${r.home} vs ${r.away}`,league,reason:`no validated HBT transfer state for ${league}`,competition:r.competition||r.competitionSlug||null});continue;}
      const useDeploy=isC1?c1Packs.get(league):deploy;
      if(isC1&&!useDeploy){excluded.push({fixture:`${r.home} vs ${r.away}`,league,reason:'C1 state pack unavailable',competition:r.competition||r.competitionSlug||null});continue;}"""
rep(old,new,'competition safety gate')

P.write_text(s,encoding='utf-8')
print('resolver-v3 hardening applied')
