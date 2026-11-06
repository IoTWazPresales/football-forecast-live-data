#!/usr/bin/env python3
"""HBT read-only, self-contained market-first dashboard generated from governed desk data."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from hbt_build_betting_desk_v1 import ROOT, build


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>HBT · Market-first preview</title>
<style>
:root{color-scheme:dark;--bg:#0d1220;--panel:#172136;--line:#324056;--dim:#a7b5c9;--ink:#eaf1fc;--blue:#69b8ff;--amber:#eec778;--green:#73d6a5}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1390px;padding:28px 22px 70px;margin:auto}header{display:flex;align-items:flex-start;justify-content:space-between;gap:25px;flex-wrap:wrap}
h1{font-size:clamp(25px,4vw,38px);line-height:1.1;margin:5px 0 14px;letter-spacing:-.025em}h2{font-size:19px;margin:0 0 12px}
h3{font-size:15px;margin:0}.eyebrow{font-size:12px;color:var(--blue);text-transform:uppercase;letter-spacing:.11em;font-weight:700}
.sub{max-width:800px;color:var(--dim);margin:0 0 22px}.pill{border:1px solid #6c563c;border-radius:100px;color:var(--amber);padding:6px 11px;white-space:nowrap}
.cards{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:11px;margin:10px 0 20px}
.metric{background:var(--panel);border:1px solid var(--line);padding:15px;border-radius:11px}.metric strong{display:block;font-size:26px;font-variant-numeric:tabular-nums}.metric span{display:block;color:var(--dim);font-size:12px}
.notice{padding:13px 16px;background:#262739;border:1px solid #77613b;border-radius:10px;margin:18px 0;color:#f2dec1}
.layout{display:grid;grid-template-columns:1fr;gap:22px}.section{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:18px;margin-top:18px}
.controls{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:12px 0}input,select,button{color:var(--ink);background:#111b30;border:1px solid #485a74;border-radius:7px;font:inherit;padding:9px}
input[type=search]{flex:1;min-width:200px}input[type=checkbox]{accent-color:var(--blue)}label{color:var(--dim);display:flex;align-items:center;gap:5px;padding:4px}
.help{color:var(--dim);font-size:12px;margin:5px 0 13px}details.fixture{border:1px solid var(--line);border-radius:10px;margin:10px 0;overflow:hidden;background:#121c2e}
summary{padding:13px 16px;cursor:pointer;font-weight:650}summary:hover{background:#1e2d46}.fixture-details{padding:2px 16px 16px}
.tag{display:inline-block;border-radius:6px;padding:3px 7px;background:#2b3c56;font-size:11px;color:var(--dim);margin-left:6px}.data-table{overflow:auto}
table{border-collapse:collapse;width:100%;min-width:800px}th,td{padding:9px 10px;text-align:left;border-bottom:1px solid #2f3b50;vertical-align:top}th{font-size:12px;color:var(--dim);white-space:nowrap}td{font-variant-numeric:tabular-nums}td.wrap{min-width:170px}td.small{font-size:11px;color:var(--dim);min-width:220px}
.bars{height:6px;background:#2e3d55;width:110px;border-radius:6px;margin-top:5px}.bar{height:100%;background:var(--blue);border-radius:6px}
.good{color:var(--green)}.bad{color:#faa6a0}.muted{color:var(--dim)}.missing{color:var(--amber)}.flex{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.focus{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.focus article{background:#1d2a42;border:1px solid #344760;border-radius:9px;padding:10px}.focus small{color:var(--dim);display:block}
pre{white-space:pre-wrap;word-break:break-word}.chain{border:1px solid var(--line);border-radius:9px;padding:12px;margin:8px 0}
footer{color:var(--dim);font-size:12px;margin-top:28px}
@media(max-width:760px){main{padding:18px 12px}.cards{grid-template-columns:repeat(2,1fr)}.focus{grid-template-columns:1fr}.metric strong{font-size:22px}}
</style></head><body><main>
<header><div><div class="eyebrow">Football Forecast Lab · HBT Research</div><h1>Market-first betting desk</h1>
<p class="sub">Every <strong>supported modelled selection</strong>, ranked by estimated chance of winning. Compare independently with bookmaker prices and expected returns; inspect shadow chains. This is not a betting instruction.</p></div><span class="pill">Research preview · no wagers</span></header>
<div class="cards" id="metrics"></div><div class="notice" id="alert"></div>
<section class="section"><h2>Market-by-market predictions</h2>
<div class="controls"><input id="query" type="search" placeholder="Find a team or competition" aria-label="Search fixtures">
<select id="order"><option value="prob">Highest chance first</option><option value="ev">Highest EV first</option><option value="time">Kickoff time</option></select>
<label><input id="onlyPriced" type="checkbox">Quoted markets only</label>
<label><input id="onlyValue" type="checkbox">Nonnegative EV only</label></div>
<div class="help">Win probability is not a guarantee or a calibrated live edge. DNB refunds are not wins. Prices, when available, must include independent timestamped provenance. Missing means unavailable, not zero.</div><div id="fixtureList"></div></section>
<section class="section"><h2>2–4-leg shadow chains</h2><p class="help">Each chain uses distinct fixtures. Multiplying marginal probabilities assumes independence; the displayed probability bounds show how uncertain that assumption is. All chains remain research-only until the dependence and settlement rules are validated.</p><div id="chains"></div></section>
<section class="section"><h2>Discovered fixtures without model forecasts</h2><div class="help" id="unscoredLabel"></div><details><summary>View coverage gaps</summary><div class="data-table"><table><thead><tr><th>Fixture</th><th>Kickoff (SAST)</th><th>Competition</th><th>Coverage</th></tr></thead><tbody id="unscored"></tbody></table></div></details></section>
<footer><div id="source"></div> Read-only, snapshot-based. Never place bets from an expired screenshot or quote. No forecasts or pricing data are manufactured.</footer>
</main>
<script>
"use strict";
const desk=__HBT_SNAPSHOT_JSON__;
const $=id=>document.getElementById(id);
const esc=x=>String(x===null||x===undefined?"—":x).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pct=x=>typeof x==="number"?(x*100).toFixed(1)+"%":"—";
const num=x=>typeof x==="number"?x.toFixed(2):"—";
const signed=x=>typeof x==="number"?(x>=0?"+":"")+(x*100).toFixed(1)+"%":"—";
const ko=x=>{if(!x)return "unverified";try{return new Intl.DateTimeFormat("en-ZA",{timeZone:"Africa/Johannesburg",day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(x))+" SAST"}catch(e){return "unverified"}};
const fxName=f=>((f||{}).home||"?")+" vs "+((f||{}).away||"?");
const bestLabel=m=>m?esc(m.selection)+" · "+pct(m.profitProbability):"Unavailable";
const summary=desk.summary||{};
const covered=(desk.fixtures||[]).length,uncovered=(desk.unscoredFixtures||[]).length;
const metrics=[["Fixtures discovered",covered+uncovered],["Forecasted fixtures",covered],["Modelled selections",summary.marketsModelled||0],["Verified priced",summary.bookmakerPricedMarkets||0],["Stake-ready singles",summary.readySingles||0]];
$("metrics").innerHTML=metrics.map(([t,n])=>'<article class="metric"><strong>'+esc(n)+'</strong><span>'+esc(t)+'</span></article>').join("");
const quote=desk.quoteAudit||{};
$("alert").innerHTML="<strong>"+esc(desk.readiness||"NOT VERIFIED")+"</strong> · Price source: "+esc(quote.sourceStatus||"UNVERIFIED")+
 ". Forecast mode is displayed per fixture. Market prices and expected return cannot be assessed unless independent, fresh quotes exist. No bet is certain.";
function mkFocus(title,m){return '<article><small>'+esc(title)+'</small><div>'+bestLabel(m)+'</div>'+(m?'<small>Quote: '+num(m.observedOdds)+' · EV/R1: '+signed(m.expectedProfitPerRand)+'</small>':'')+'</article>'}
function mkRow(m){
 const p=Number(m.profitProbability||0);
 const quoted=m.observedOdds!==null&&m.observedOdds!==undefined;
 const risk=(m.fundingBlockers||[]).join(", ");
 return '<tr><td class="wrap"><strong>'+esc(m.selection)+'</strong><div class="muted">'+esc(m.family||m.market)+'</div></td>'+
 '<td><strong>'+pct(p)+'</strong><div class="bars"><div class="bar" style="width:'+Math.max(0,Math.min(100,p*100))+'%"></div></div></td>'+
 '<td>'+pct(m.pushProbability)+'</td><td>'+num(m.fairOdds)+'</td>'+
 '<td class="'+(quoted?"":"missing")+'">'+num(m.observedOdds)+(quoted?'<small class="muted"> '+esc(m.bookmaker||"")+'</small>':'')+'</td>'+
 '<td class="'+(m.expectedProfitPerRand>=0&&quoted?"good":quoted?"bad":"missing")+'">'+signed(m.expectedProfitPerRand)+'</td>'+
 '<td class="small">'+esc(m.source||"—")+'</td><td class="small">'+(m.stakeReady?'<span class="good">READY</span>':esc(risk||"Research / unavailable"))+'</td></tr>';
}
function renderFixtures(){
 const q=$("query").value.trim().toLowerCase(),onlyPriced=$("onlyPriced").checked,onlyValue=$("onlyValue").checked,order=$("order").value;
 const fs=(desk.fixtures||[]).filter(f=>fxName(f.fixture).toLowerCase().includes(q)||String((f.fixture||{}).league||"").toLowerCase().includes(q)).slice();
 if(order==="prob")fs.sort((a,b)=>(b.highestProbabilityMarket?.profitProbability||0)-(a.highestProbabilityMarket?.profitProbability||0));
 else if(order==="ev")fs.sort((a,b)=>(b.highestQuotedExpectedReturnMarket?.expectedProfitPerRand??-Infinity)-(a.highestQuotedExpectedReturnMarket?.expectedProfitPerRand??-Infinity));
 else fs.sort((a,b)=>String(a.kickoffVerification?.kickoffUtc||"").localeCompare(String(b.kickoffVerification?.kickoffUtc||"")));
 let visible=0;
 $("fixtureList").innerHTML=fs.map(f=>{
    const markets=(f.markets||[]).filter(m=>(!onlyPriced||m.observedOdds!=null)&&(!onlyValue||(m.expectedProfitPerRand!=null&&m.expectedProfitPerRand>=0))).sort((a,b)=>order==="ev"?((b.expectedProfitPerRand??-Infinity)-(a.expectedProfitPerRand??-Infinity)):(b.profitProbability-a.profitProbability));
    if(!markets.length)return "";
    visible++;
    const leader=f.highestProbabilityMarket,evleader=f.highestQuotedExpectedReturnMarket,bal=f.highestProbabilityNonnegativeEVMarket;
    return '<details class="fixture" open><summary>'+esc(fxName(f.fixture))+' <span class="tag">'+esc(f.predictionMode)+'</span><span class="tag">'+esc(ko(f.kickoffVerification?.kickoffUtc))+'</span><span class="tag">'+markets.length+' selections</span></summary>'+
    '<div class="fixture-details"><div class="focus">'+mkFocus("Highest chance",leader)+mkFocus("Best quoted EV",evleader)+mkFocus("Highest chance with EV ≥ 0",bal)+'</div>'+
    '<p class="help">Forecast coverage: '+esc(f.coverage)+' · Status: '+esc(f.readinessState||"unverified")+' · Betting blockers remain visible below.</p>'+
    '<div class="data-table"><table><thead><tr><th>Selection</th><th>Win chance</th><th>Refund</th><th>Fair odds</th><th>Current odds</th><th>EV/R1</th><th>Evidence</th><th>Blockers</th></tr></thead><tbody>'+markets.map(mkRow).join("")+'</tbody></table></div></div></details>';
 }).join("")||'<p class="missing">No scored fixtures or selections match these filters.</p>';
}
function renderChains(){
 const chains=(desk.chains||[]).slice(0,16);
 $("chains").innerHTML=chains.map(c=>'<div class="chain"><div class="flex"><strong>'+esc(c.legCount)+'-leg '+esc(c.objective||"SHADOW")+'</strong><span class="tag">Research only</span></div>'+
 '<div>'+esc((c.legs||[]).map(x=>fxName(x.fixture)+" — "+x.selection).join(" · "))+'</div>'+
 '<div class="help">Approx. all-win chance: '+pct(c.jointProbabilityIndependenceApprox)+' · Without independence: '+pct(c.jointProbabilityBounds?.lower)+'–'+pct(c.jointProbabilityBounds?.upper)+' · Combined odds: '+num(c.combinedOdds)+' · Expected profit/R1: '+signed(c.expectedProfitPerRandIndependenceApprox)+'</div>'+
 '<div class="help">Blocks: '+esc((c.fundingBlockers||[]).join(", ")||"No stake authorisation")+'</div></div>').join("")||'<p class="missing">No research chain candidates with current model coverage.</p>';
}
const gaps=desk.unscoredFixtures||[];
$("unscoredLabel").textContent=gaps.length+" discovered fixtures have no supported scored forecast. No probabilities are invented for them.";
$("unscored").innerHTML=gaps.map(f=>'<tr><td>'+esc(fxName(f))+'</td><td>'+esc(ko(f.kickoff))+'</td><td>'+esc(f.competition||f.leagueHint)+'</td><td>'+esc(f.hbtSupportLevel||f.classificationReason)+'</td></tr>').join("");
$("source").textContent="Snapshot: "+(desk.targetDate||"unknown")+" · Generated: "+(desk.generatedAt||"unknown")+" · Modelled markets only.";
["query","order","onlyPriced","onlyValue"].forEach(id=>$(id).addEventListener("input",renderFixtures));
renderFixtures();renderChains();
</script></body></html>'''


def render_dashboard(doc: dict) -> str:
    """HTML is self-contained and no source string can terminate the JSON script."""
    payload = json.dumps(doc, separators=(",", ":"), allow_nan=False)
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    assert "__HBT_SNAPSHOT_JSON__" in PAGE
    return PAGE.replace("__HBT_SNAPSHOT_JSON__", payload)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="Fixture date, YYYY-MM-DD (SAST)")
    ap.add_argument("--data-root", type=Path, default=ROOT)
    ap.add_argument("--output-dir", type=Path)
    args = ap.parse_args()
    datetime.strptime(args.date, "%Y-%m-%d")
    root = args.data_root
    out = args.output_dir or root
    out.mkdir(parents=True, exist_ok=True)
    doc = build(args.date, data_root=root)
    doc["previewPolicy"] = {
        "researchOnly": True, "autoBetting": False,
        "probabilityFirst": True,
        "missingMarketsUnscored": True,
        "sameFixtureChainsUnvalidated": True
    }
    html_path = out / f"hbt_market_first_preview_{args.date}.html"
    json_path = out / f"hbt_market_first_preview_{args.date}.json"
    html_path.write_text(render_dashboard(doc), encoding="utf-8")
    json_path.write_text(json.dumps(doc, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "html": str(html_path), "json": str(json_path),
        "date": args.date, "readiness": doc.get("readiness"),
        "summary": doc.get("summary"),
        "chains": len(doc.get("chains") or [])
    }, indent=2))


if __name__ == "__main__":
    main()
