/** Pure identity/parity checks for the immutable L0 projection boundary. */
export function fixtureKey(p) {
  const f=p?.fixture;
  if(!f||['date','league','home','away'].some(k=>typeof f[k]!=='string'||!f[k].trim()||f[k].includes('|')))
    throw Error('Missing or ambiguous frozen fixture identity');
  return [f.date,f.league,f.home,f.away].join('|');
}
export function originalFixtureProbabilities(predictions) {
  if(!Array.isArray(predictions))throw Error('Invalid frozen predictions');
  const result=new Map();
  for(const p of predictions){
    const key=fixtureKey(p);
    if(result.has(key))throw Error('Duplicate frozen fixture identity: '+key);
    if(!Array.isArray(p.probs)||p.probs.length!==3||
       !p.probs.every(x=>typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=1)||
       Math.abs(p.probs.reduce((sum,x)=>sum+x,0)-1)>1e-9)
      throw Error('Invalid frozen L0 probabilities: '+key);
    result.set(key,p.probs);
  }
  return result;
}
export function validateProjectedFixtures(original,projected) {
  if(!Array.isArray(projected)||projected.length!==original.size)throw Error('Projection altered target/count');
  const seen=new Set(),result=[];
  for(const p of projected){
    const key=fixtureKey(p);
    if(seen.has(key))throw Error('Duplicate projected fixture identity: '+key);
    seen.add(key);
    if(!original.has(key)||JSON.stringify(original.get(key))!==JSON.stringify(p.probs))
      throw Error('L0 probability changed for '+key);
    const v=p.structuralFeatures?.vec;
    if(!Array.isArray(v)||v.length!==11||!v.every(Number.isFinite))
      throw Error('Causal structural vector unavailable: '+key);
    result.push({fixture:key,structuralVectorLength:v.length});
  }
  return result;
}
