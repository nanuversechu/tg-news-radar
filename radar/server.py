"""The desk dashboard: stdlib HTTP server, one page, no build step.

The page takes its colours from the live Omarchy theme (see theme.py) and
re-reads them every refresh, so `omarchy theme set` restyles it in seconds.

It is organised around one question: what are people in this state searching
for and reading right now, and is it covered. Every search shows
its own coverage; clicking one narrows the board to the stories that answer it.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, poll, theme

PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__SLUG__</title>
<style>
  :root{
__THEME_VARS__
  }
  *{box-sizing:border-box; border-radius:0 !important}
  html{background:var(--bg)}
  body{
    margin:0; background:var(--bg); color:var(--text);
    font-family:"JetBrainsMono Nerd Font","CaskaydiaMono Nerd Font",ui-monospace,
      "JetBrains Mono","Cascadia Mono",Menlo,Consolas,monospace,"Noto Sans Telugu";
    font-size:13.5px; line-height:1.6; font-variant-ligatures:none;
    -webkit-font-smoothing:antialiased;
  }
  a{color:inherit}
  button,input{font:inherit; color:inherit}

  /* ---- top bar, in the manner of waybar ---- */
  .bar{display:flex; align-items:stretch; flex-wrap:wrap; position:sticky; top:0; z-index:10;
    background:var(--panel); border-bottom:1px solid var(--line); font-size:12.5px}
  .seg{padding:5px 12px; border-right:1px solid var(--line); white-space:nowrap;
    display:flex; align-items:center; gap:7px}
  .seg.name{background:var(--accent); color:var(--on_accent); font-weight:700; letter-spacing:.08em}
  .seg.right{margin-left:auto; border-right:none; border-left:1px solid var(--line); color:var(--muted)}
  .seg.dim{color:var(--muted)}
  .seg.btn{cursor:pointer; user-select:none}
  .seg.btn:hover{background:var(--sel); color:var(--text)}
  .dot{display:inline-block; width:7px; height:7px; background:var(--up)}
  .dot.bad{background:var(--down)}
  .dot.live{animation:pulse 2.2s ease-in-out infinite}
  @keyframes pulse{50%{opacity:.35}}
  .stale{background:var(--down); color:var(--bg); font-weight:700}
  .notice{padding:6px 14px; font-size:12.5px; border-bottom:1px solid var(--line);
    background:var(--panel); color:var(--warm)}
  .notice.bad{color:var(--down)}

  /* ---- source health panel ---- */
  #srcpanel{border-bottom:1px solid var(--line); background:var(--panel); font-size:12px}
  #srcpanel table{border-collapse:collapse; width:100%; max-width:1000px; margin:0 auto}
  #srcpanel td{padding:3px 12px; border-bottom:1px solid var(--line); white-space:nowrap}
  #srcpanel td.err{color:var(--down); white-space:normal}
  #srcpanel td.ok{color:var(--up)} #srcpanel td.warn{color:var(--warm)}
  #srcpanel td.num{text-align:right; color:var(--muted); font-variant-numeric:tabular-nums}

  .wrap{max-width:1000px; margin:0 auto; padding:18px 18px 80px}

  /* ---- section rules: "── LABEL ─────────────" ---- */
  .sec{display:flex; align-items:center; gap:10px; margin:24px 0 10px}
  .sec:first-of-type{margin-top:8px}
  .sec b{font-weight:700; font-size:11.5px; letter-spacing:.14em; text-transform:uppercase;
    color:var(--muted); white-space:nowrap}
  .sec .rule{flex:1; border-top:1px solid var(--line)}
  .sec .note,.sec .n{font-size:11.5px; color:var(--muted); white-space:nowrap}

  .ar{display:inline-block; width:1.2ch; font-weight:700}
  .ar.up,.up-c{color:var(--up)} .ar.down,.down-c{color:var(--down)}
  .ar.new{color:var(--accent)} .ar.flat{color:var(--muted)}
  .ap{color:var(--accent); font-size:10.5px; letter-spacing:.08em; font-weight:700}
  .warn-c{color:var(--warm)}

  /* ---- trend cells ---- */
  .grid{display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr));
    border-top:1px solid var(--line); border-left:1px solid var(--line)}
  .cell{border-right:1px solid var(--line); border-bottom:1px solid var(--line);
    padding:7px 10px; display:block; cursor:pointer; position:relative}
  .cell:hover{background:var(--sel)}
  .cell.on{background:var(--sel); outline:1px solid var(--accent); outline-offset:-1px}
  .cell .q{white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:13px; padding-right:16px}
  .cell .m{font-size:11.5px; color:var(--muted); margin-top:1px; display:flex;
    justify-content:space-between; gap:8px}
  .cell .cov{white-space:nowrap}
  .cell .cov.none{color:var(--warm)}
  .cell .ext{position:absolute; right:6px; top:5px; font-size:11px; color:var(--muted);
    text-decoration:none; padding:0 3px}
  .cell .ext:hover{color:var(--accent)}

  /* ---- trailing chips ---- */
  .chips{display:flex; flex-wrap:wrap; border-top:1px solid var(--line); border-left:1px solid var(--line)}
  .chip{padding:4px 10px; border-right:1px solid var(--line); border-bottom:1px solid var(--line);
    font-size:12px; color:var(--muted); text-decoration:none; white-space:nowrap}
  .chip:hover{background:var(--sel); color:var(--text)}
  .chip b{color:var(--text); font-weight:500}

  /* ---- top stories by place ---- */
  .cols{display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:0;
    border-top:1px solid var(--line); border-left:1px solid var(--line)}
  .col{border-right:1px solid var(--line); border-bottom:1px solid var(--line); min-width:0}
  .colhead{padding:5px 11px; font-size:11px; letter-spacing:.12em; text-transform:uppercase;
    color:var(--text); font-weight:700; border-bottom:1px solid var(--line); display:flex; gap:8px}
  .colhead i{font-style:normal; color:var(--muted); font-weight:400; letter-spacing:0; text-transform:none; margin-left:auto}
  .st{display:grid; grid-template-columns:4ch 1fr; gap:0 10px; padding:4px 11px; text-decoration:none;
    border-bottom:1px solid var(--line); align-items:baseline}
  .st:last-child{border-bottom:none}
  .st:hover{background:var(--sel)}
  .st .a{color:var(--muted); font-size:11.5px; text-align:right; font-variant-numeric:tabular-nums}
  .st .h{font-size:13px; line-height:1.45; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical}
  .st .o{color:var(--muted); font-size:11.5px}
  .st.new .a{color:var(--up)}

  /* ---- reading rows ---- */
  .rd{display:grid; grid-template-columns:7ch 1fr auto; gap:0 12px; align-items:baseline;
    padding:4px 11px; border:1px solid var(--line); border-top:none; text-decoration:none}
  .rd:first-child,.rd.first{border-top:1px solid var(--line)}
  .rd:hover{background:var(--sel)}
  .rd .r{color:var(--muted); font-size:11.5px; font-variant-numeric:tabular-nums; text-align:right}
  .rd .t{overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
  .rd .t.dim{color:var(--muted)}
  .rd .c{font-size:11.5px; white-space:nowrap; color:var(--muted)}
  .rd .c.yes{color:var(--up)}
  .rdhead{padding:6px 11px 2px; font-size:11px; letter-spacing:.1em; text-transform:uppercase;
    color:var(--muted); display:flex; gap:10px; align-items:baseline}
  .rdhead i{font-style:normal; letter-spacing:0; text-transform:none; font-size:11.5px}

  /* ---- toolbar ---- */
  .tools{display:flex; flex-wrap:wrap; gap:8px; margin:0 0 12px; align-items:stretch}
  .tabs{display:flex; border:1px solid var(--line)}
  .tabs button{font-size:12px; cursor:pointer; padding:3px 12px; background:transparent;
    border:none; border-right:1px solid var(--line); color:var(--muted)}
  .tabs button:last-child{border-right:none}
  .tabs button:hover{background:var(--sel); color:var(--text)}
  .tabs button.on{background:var(--accent); color:var(--on_accent); font-weight:700}
  .search{border:1px solid var(--line); background:transparent; padding:3px 10px; font-size:12px;
    min-width:200px; outline:none}
  .search:focus{border-color:var(--accent)}
  .search::placeholder{color:var(--muted)}
  .pill{display:flex; align-items:center; gap:8px; border:1px solid var(--accent); padding:2px 10px;
    font-size:12px; color:var(--accent)}
  .pill button{background:none; border:none; cursor:pointer; color:var(--muted); padding:0 2px}
  .pill button:hover{color:var(--down)}

  /* ---- story rows ---- */
  .row{display:grid; grid-template-columns:7ch 1fr; border:1px solid var(--line); border-top:none}
  .row:first-of-type{border-top:1px solid var(--line)}
  .row:hover,.row.cur{background:var(--sel)}
  .row.cur{outline:1px solid var(--accent); outline-offset:-1px}
  .gutter{border-right:1px solid var(--line); padding:8px 0; text-align:center;
    display:flex; flex-direction:column; align-items:center; gap:1px}
  .gutter .n{font-size:15px; font-weight:700; line-height:1.15; font-variant-numeric:tabular-nums}
  .gutter .d{font-size:11px; line-height:1.2}
  .gutter .sp{font-size:10px; color:var(--muted); line-height:1; margin-top:2px}
  .body{padding:8px 12px; min-width:0}
  .ttl{margin:0; font-size:13.5px; font-weight:600; line-height:1.5}
  .gloss{color:var(--muted); font-size:12.5px}
  .meta{color:var(--muted); font-size:12px; margin-top:2px}
  .meta .k{color:var(--text)}
  .why{color:var(--accent); font-size:12px; margin-top:3px}
  .fp{font-size:10.5px; letter-spacing:.06em; color:var(--accent); margin-left:8px; font-weight:700}
  .bar-t{letter-spacing:-.5px}
  .t-hot{color:var(--hot)} .t-warm{color:var(--warm)} .t-cool{color:var(--cool)}
  details{margin-top:4px}
  summary{cursor:pointer; list-style:none; color:var(--muted); font-size:12px}
  summary::-webkit-details-marker{display:none}
  summary:hover{color:var(--accent)}
  .links{margin-top:4px; border-top:1px solid var(--line)}
  .links a{display:flex; gap:10px; align-items:baseline; padding:3px 0; text-decoration:none;
    color:var(--muted); font-size:12.5px}
  .links a:hover{color:var(--text)}
  .links .t{overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0}
  .links .o{margin-left:auto; color:var(--muted); font-size:11.5px; white-space:nowrap}

  .empty{color:var(--muted); font-size:12.5px; padding:9px 11px; border:1px solid var(--line)}
  .keys{margin-top:26px; color:var(--muted); font-size:11.5px}
  .keys kbd{border:1px solid var(--line); padding:0 5px; margin-right:2px}
  @media (max-width:640px){ .seg.hide-sm{display:none} .row{grid-template-columns:6ch 1fr} }
</style></head><body>

<div class="bar">
  <span class="seg name">__SLUG__</span>
  <span class="seg" id="s-live"><span class="dot live"></span>live</span>
  <span class="seg dim" id="s-upd">connecting…</span>
  <span class="seg dim hide-sm" id="s-next"></span>
  <span class="seg dim hide-sm" id="s-cnt"></span>
  <span class="seg btn" id="s-src" title="source health">src —</span>
  <span class="seg right" id="s-theme"></span>
</div>
<div id="notices"></div>
<div id="srcpanel" hidden></div>

<div class="wrap">
  <div class="sec"><b>Searching now</b>
    <span class="rule"></span><span class="n" id="n-tr"></span></div>
  <div class="grid" id="trends"></div>

  <div class="sec"><b>Trailing</b><span class="note">was trending, has dropped off</span>
    <span class="rule"></span><span class="n" id="n-trail"></span></div>
  <div class="chips" id="trailing"></div>

  <div class="sec"><b>Top stories</b><span class="note">Google News · state and cities · no account, no cookies · last 2h</span>
    <span class="rule"></span><span class="n" id="n-sec"></span></div>
  <div class="cols" id="sections"></div>


  <div class="sec"><b>Story board</b><span class="note">everything published in the last 2 hours, scored</span>
    <span class="rule"></span><span class="n" id="n-board"></span></div>
  <div class="tools">
    <div class="tabs" id="filters">
      <button data-f="all" class="on">all</button>
      <button data-f="ap">__LOCAL_LOWER__ only</button>
      <button data-f="fresh">&lt;30m</button>
      <button data-f="trend">search-backed</button>
      <button data-f="moving">moving</button>
    </div>
    <div class="pill" id="pill" hidden><span id="pill-t"></span><button id="pill-x" title="clear">×</button></div>
    <input class="search" id="q" placeholder="/ filter…" autocomplete="off" spellcheck="false">
  </div>
  <div id="board"></div>

  <div class="sec"><b>Reading</b><span class="note">Telugu Wikipedia · most-viewed pages yesterday</span>
    <span class="rule"></span><span class="n" id="n-rd"></span></div>
  <div id="reading"></div>
  <div class="keys"><kbd>/</kbd>filter <kbd>j</kbd><kbd>k</kbd>move <kbd>o</kbd>open <kbd>1</kbd>–<kbd>5</kbd>tabs <kbd>s</kbd>sources <kbd>esc</kbd>clear</div>
</div>

<script>
const REGION=__REGION_JS__;
let FILTER='all', Q='', DATA=null, CUR=-1, TREND=null;   // TREND = {query, ids:Set}

const esc = s => String(s??'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ago = m => m<1?'now' : m<60?m+'m' : m<1440?Math.round(m/60)+'h' : Math.round(m/1440)+'d';
const tier = s => s>=70?'hot' : s>=48?'warm' : 'cool';
const fmtK = n => !n?'—' : n>=1e6?(n/1e6).toFixed(1)+'M+' : n>=1000?Math.round(n/1000)+'K+' : n+'+';
const BLOCKS='▁▂▃▄▅▆▇█';
const bar = (v,w) => { const on=Math.max(0,Math.min(w,Math.round(v*w))); return '█'.repeat(on)+'·'.repeat(w-on); };
const spark = b => ['trend','acceleration','corroboration','prominence','velocity','freshness']
  .map(k => BLOCKS[Math.max(0,Math.min(7,Math.round(((b||{})[k]||0)*7)))]).join('');
const ARROW = {up:'▲', down:'▼', new:'●', flat:'→'};
const arrow = d => `<span class="ar ${d}" title="${d}">${ARROW[d]||'→'}</span>`;

function applyTheme(t){
  if(!t||!t.roles) return;
  const r=document.documentElement.style;
  for(const [k,v] of Object.entries(t.roles)) r.setProperty('--'+k, v);
  document.getElementById('s-theme').textContent = (t.name||'theme') + (t.source==='fallback'?' (fallback)':'');
}

function trendCell(t,i){
  const d=t.direction||'flat';
  const geo = REGION.badges[t.geo] || t.geo;
  const n=t.coverage_outlets||0;
  const cov = n===0 ? '<span class="cov none">uncovered</span>'
            : n===1 ? '<span class="cov none">1 outlet</span>'
            : `<span class="cov">${n} outlets</span>`;
  const title=`${t.geo_label} · rising ${Math.round((t.rising||0)*100)}%`+(t.delta?` · ${t.delta}`:'')
    +(t.local?' · names a '+REGION.local+' place or person':'')+'\nclick to show the stories that answer this';
  const url='https://trends.google.com/trends/explore?q='+encodeURIComponent(t.query)+'&geo='+t.geo+'&date=now%201-d';
  const on = TREND && TREND.query===t.query ? 'on' : '';
  return `<div class="cell ${on}" data-i="${i}" title="${esc(title)}">
    <a class="ext" href="${url}" target="_blank" rel="noopener" title="open in Google Trends">↗</a>
    <div class="q">${arrow(d)} ${esc(t.query)}${t.local?' <span class="ap">AP</span>':''}</div>
    <div class="m"><span>${fmtK(t.traffic)}${geo!==REGION.local?' <span style="opacity:.7">'+geo+'</span>':''}</span>${cov}</div></div>`;
}

function trailChip(t){
  const url='https://trends.google.com/trends/explore?q='+encodeURIComponent(t.query)+'&geo='+t.geo+'&date=now%201-d';
  return `<a class="chip" href="${url}" target="_blank" rel="noopener" title="peaked ${fmtK(t.peak_traffic)} · lasted ${t.lasted_min}m">
    <span class="ar down">▼</span> <b>${esc(t.query)}</b> · ${fmtK(t.peak_traffic)} · gone ${ago(t.gone_min)}</a>`;
}

function sectionCols(list){
  const order=REGION.sections;
  const by={}; for(const r of list){ (by[r.section]=by[r.section]||[]).push(r); }
  return order.filter(k=>by[k]||true).map(k=>{
    const rows=(by[k]||[]).slice(0,10);
    const body = rows.length ? rows.map(r=>`<a class="st ${r.age_min<=30?'new':''}" href="${esc(r.url)}" target="_blank" rel="noopener"
        title="#${r.rank} in Google's ranking · ${esc(r.outlet)}">
        <span class="a">${ago(r.age_min)}</span>
        <span><span class="h">${esc(r.title)}</span><span class="o">${esc(r.outlet)}</span></span></a>`).join('')
      : `<div class="empty" style="border:none">nothing new in the last 2 hours</div>`;
    return `<div class="col"><div class="colhead">${esc(k)}<i>${rows.length?rows.length+' in 2h':''}</i></div>${body}</div>`;
  }).join('');
}

function readingRows(list){
  return list.slice(0,15).map((r,i)=>`<a class="rd ${i===0?'first':''}" href="${esc(r.url||'#')}" target="_blank" rel="noopener"
      title="${r.views?r.views.toLocaleString()+' views yesterday':''}">
    <span class="r">${r.views?fmtK(r.views).replace('+',''):'#'+r.rank}</span>
    <span class="t">${esc(r.title)}${r.local?' <span class="ap">AP</span>':''}</span>
    <span class="c ${r.covered?'yes':''}">${r.covered?'✓ on board':'—'}</span></a>`).join('');
}

function scoreTitle(c){
  const b=c.breakdown||{}, d=c.direction||'flat';
  const pct=v=>String(Math.round((v||0)*100)).padStart(3)+'%';
  const dir = d==='up'   ? `▲ rising: +${Math.round(c.score_delta)} vs 15 min ago`
            : d==='down' ? `▼ fading: ${Math.round(c.score_delta)} vs 15 min ago`
            : d==='new'  ? `● new: first seen this tick`
            :              `→ flat: unchanged vs 15 min ago`;
  return [`SCORE ${Math.round(c.score)} of 100 — how likely this grows in the next few hours`, dir, '',
    `search demand ${pct(b.trend)}  ${c.trend_query?'people are searching "'+c.trend_query+'"':'no live search matches it'}`,
    `acceleration  ${pct(b.acceleration)}  reports in the last 30 min vs the 90 before`,
    `outlets       ${pct(b.corroboration)}  ${c.outlet_count} independent newsroom${c.outlet_count===1?'':'s'} carry it`,
    `front page    ${pct(b.prominence)}  ${c.front_page_rank?'#'+c.front_page_rank+' on Google News top stories':'not on Google News top stories'}`,
    `velocity      ${pct(b.velocity)}  reports per hour`,
    `freshness     ${pct(b.freshness)}  newest report ${ago(c.age_min)} ago`, '',
    `the bars below are these six, in this order`].join('\n');
}

function row(c,i){
  const t=tier(c.score), d=c.direction||'flat';
  const tip=esc(scoreTitle(c));
  const langs=(c.languages||[]).map(l=>l==='te'?'తె':'en').join('+');
  const delta = d==='up'||d==='down' ? `<span class="d ${d}-c">${c.score_delta>0?'+':''}${Math.round(c.score_delta)}</span>`
              : d==='new' ? `<span class="d ar new">new</span>` : `<span class="d">&nbsp;</span>`;
  const why=c.trend_query ? `<div class="why">└─ searching "${esc(c.trend_query)}" · ${esc(c.trend_geo||'')}</div>` : '';
  const gloss=c.title_en ? `<div class="gloss">${esc(c.title_en)}</div>` : '';
  const outl = c.outlet_delta>0 ? ` <span class="up-c">+${c.outlet_delta}</span>` : '';
  const fp = c.front_page_rank ? `<span class="fp" title="rank on Google News top stories">GN #${c.front_page_rank}</span>` : '';
  const links=(c.links||[]).filter(l=>l.url).map(l=>
    `<a href="${esc(l.url)}" target="_blank" rel="noopener">
      <span class="t">${l.kind==='social'?'◆ ':l.kind==='video'?'▶ ':''}${esc(l.title)}</span>
      <span class="o">${esc(l.outlet)} ${ago(l.age_min)}</span></a>`).join('');
  return `<article class="row ${i===CUR?'cur':''}" data-i="${i}">
    <div class="gutter" title="${tip}">
      <span class="n t-${t}">${arrow(d)}${Math.round(c.score)}</span>${delta}
      <span class="sp">${spark(c.breakdown)}</span>
    </div>
    <div class="body">
      <h3 class="ttl">${esc(c.title)}${fp}</h3>
      ${gloss}
      <div class="meta"><span class="bar-t t-${t}">${bar(c.score/100,10)}</span>
        &nbsp; <span class="k">${c.outlet_count}</span> outlet${c.outlet_count===1?'':'s'}${outl}
        · ${ago(c.age_min)} · ${langs}${c.locality!==REGION.local?' · '+esc(c.locality):''}</div>
      ${why}
      ${links?`<details><summary>+ ${c.item_count} reports</summary><div class="links">${links}</div></details>`:''}
    </div></article>`;
}

const keep = c => {
  if(TREND && !TREND.ids.has(c.id)) return false;
  if(!TREND && c.extra) return false;   // below the top 60: only shown for a search
  if(FILTER==='ap' && c.locality!==REGION.local) return false;
  if(FILTER==='fresh' && c.age_min>30) return false;
  if(FILTER==='trend' && !c.trend_query) return false;
  if(FILTER==='moving' && !['up','new'].includes(c.direction)) return false;
  if(Q){ const h=(c.title+' '+(c.title_en||'')+' '+(c.trend_query||'')+' '+(c.outlets||[]).join(' ')).toLowerCase();
         if(!h.includes(Q)) return false; }
  return true;
};

let countdownTimer=null;
function renderBar(){
  const s=DATA.stats||{}; const now=Date.now();
  const last=DATA.last_tick?new Date(DATA.last_tick):null;
  const ageS=last?(now-last)/1000:0;
  const stale=last && ageS > (DATA.tick_seconds||300)*3;
  const live=document.getElementById('s-live');
  live.className='seg'+(stale?' stale':'');
  live.innerHTML= stale ? `▲ STALE ${ago(Math.round(ageS/60))}` : `<span class="dot live"></span>live`;
  document.getElementById('s-upd').textContent = last
    ? 'updated '+last.toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',hour12:false}) : 'first tick running…';
  const next=DATA.next_tick_at?new Date(DATA.next_tick_at):null;
  const nx=document.getElementById('s-next');
  clearInterval(countdownTimer);
  const tickDown=()=>{ if(!next){nx.textContent='';return;}
    const s=Math.max(0,Math.round((next-Date.now())/1000));
    nx.textContent = s>0 ? `next ${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}` : 'polling…'; };
  tickDown(); countdownTimer=setInterval(tickDown,1000);
  document.getElementById('s-cnt').textContent =
    `${s.clusters||0} stories · ${s.trends||0} trends` + (s.too_old?` · ${s.too_old} too old`:'');
  const ok=s.sources_ok??0, tot=s.sources_total??0;
  document.getElementById('s-src').innerHTML=`<span class="dot ${ok<tot?'bad':''}"></span>src ${ok}/${tot}`;

  const notes=[];
  if(DATA.last_error) notes.push(['bad','last tick failed: '+esc(DATA.last_error)]);
  if((DATA.degraded||[]).length) notes.push(['warn','degraded this tick: '+DATA.degraded.join(', ')+' — showing last good data for those']);
  const cd=Object.entries(DATA.cooldowns||{});
  if(cd.length) notes.push(['warn','cooling down: '+cd.map(([h,s])=>`${h} (${Math.ceil(s/60)}m)`).join(', ')]);
  document.getElementById('notices').innerHTML = notes.map(([k,t])=>`<div class="notice ${k==='bad'?'bad':''}">${t}</div>`).join('');
}

function renderSources(){
  const rows=(DATA.sources||[]).map(s=>{
    const lastFresh = s.last_fresh ? (Date.now()-new Date(s.last_fresh))/3600000 : null;
    const quiet = s.ok && s.kind==='news' && lastFresh!==null && lastFresh>24;
    return `<tr>
    <td class="${s.ok?(quiet?'warn':'ok'):'err'}">${s.ok?(quiet?'quiet':'ok'):'FAIL'}</td>
    <td>${esc(s.name)}</td><td class="num">${s.count}</td><td class="num">${s.fresh_count??''}${s.fresh_count!=null?' fresh':''}</td>
    <td class="num">${s.ms}ms</td>
    <td class="num">${s.last_ok?ago(Math.round((Date.now()-new Date(s.last_ok))/60000))+' ago':'never'}</td>
    <td class="${s.ok?'':'err'}">${s.ok?(quiet?'no fresh item in '+Math.round(lastFresh)+'h':''):esc(s.last_error)+(s.failures>1?` ×${s.failures}`:'')}</td></tr>`;}).join('');
  document.getElementById('srcpanel').innerHTML = rows?`<table>${rows}</table>`:'';
}

function setTrend(t){
  if(!t || (TREND && TREND.query===t.query)) TREND=null;
  else TREND={query:t.query, ids:new Set(t.coverage_ids||[])};
  const pill=document.getElementById('pill');
  pill.hidden=!TREND;
  if(TREND) document.getElementById('pill-t').textContent='answers "'+TREND.query+'"';
  CUR=-1; render();
}

function render(){
  if(!DATA) return;
  renderBar(); renderSources();
  const tr=(DATA.trends||[]).slice(0,30);
  document.getElementById('trends').innerHTML = tr.length ? tr.map(trendCell).join('') : '<div class="empty">no trend data yet</div>';
  document.querySelectorAll('#trends .cell').forEach(el=>el.onclick=e=>{ if(e.target.closest('a')) return; setTrend(tr[+el.dataset.i]); });
  const up=tr.filter(t=>t.direction==='up'||t.direction==='new').length, dn=tr.filter(t=>t.direction==='down').length,
        unc=tr.filter(t=>!t.coverage_outlets).length, loc=tr.filter(t=>t.local).length;
  document.getElementById('n-tr').textContent = tr.length ? `${up}▲ ${dn}▼ · ${loc} AP · ${unc} uncovered` : '';
  const trl=DATA.trailing||[];
  document.getElementById('trailing').innerHTML = trl.length ? trl.map(trailChip).join('') : '<div class="empty" style="border:none">nothing has dropped off in the last 90 minutes</div>';
  document.getElementById('n-trail').textContent = trl.length? trl.length+'' : '';
  const sec=DATA.sections||[];
  document.getElementById('sections').innerHTML = sectionCols(sec);
  document.getElementById('n-sec').textContent = sec.length ? `${sec.filter(r=>r.age_min<=30).length} in the last 30 min` : '';
  const rd=DATA.reading||[];
  document.getElementById('reading').innerHTML = rd.length ? readingRows(rd) : '<div class="empty">no reading data yet — Wikipedia loads on the hourly tick</div>';
  document.getElementById('n-rd').textContent = rd.length ? `${rd.filter(r=>r.covered).length} of ${rd.length} on the board` : '';

  const all=DATA.board||[];
  const b=all.filter(keep);
  if(CUR>=b.length) CUR=b.length-1;
  document.getElementById('board').innerHTML = b.length ? b.map(row).join('') : '<div class="empty">no stories match this filter</div>';
  document.getElementById('n-board').textContent = `${b.length}/${all.filter(c=>!c.extra).length}`;
  document.querySelectorAll('.row').forEach(el=>el.onclick=e=>{ if(e.target.closest('a,summary')) return; CUR=+el.dataset.i; markCur(); });
}
function markCur(){ document.querySelectorAll('.row').forEach(el=>el.classList.toggle('cur',+el.dataset.i===CUR));
  const el=document.querySelector('.row.cur'); if(el) el.scrollIntoView({block:'nearest'}); }

document.querySelectorAll('#filters button').forEach(btn=>btn.onclick=()=>setFilter(btn.dataset.f));
function setFilter(f){ FILTER=f; document.querySelectorAll('#filters button').forEach(x=>x.classList.toggle('on',x.dataset.f===f)); CUR=-1; render(); }
const qbox=document.getElementById('q');
qbox.oninput=()=>{ Q=qbox.value.trim().toLowerCase(); CUR=-1; render(); };
document.getElementById('pill-x').onclick=()=>setTrend(null);
document.getElementById('s-src').onclick=()=>{ const p=document.getElementById('srcpanel'); p.hidden=!p.hidden; };

document.addEventListener('keydown',e=>{
  if(e.target===qbox){ if(e.key==='Escape'){ qbox.value=''; Q=''; qbox.blur(); render(); } return; }
  if(e.ctrlKey||e.metaKey||e.altKey) return;
  const rows=document.querySelectorAll('.row');
  switch(e.key){
    case '/': e.preventDefault(); qbox.focus(); break;
    case 'j': if(rows.length){ CUR=Math.min(rows.length-1,CUR+1); markCur(); } break;
    case 'k': if(rows.length){ CUR=Math.max(0,CUR-1); markCur(); } break;
    case 'o': case 'Enter': { const el=document.querySelector('.row.cur .links a'); if(el) window.open(el.href,'_blank','noopener'); break; }
    case 'Escape': CUR=-1; if(TREND) setTrend(null); else { markCur(); render(); } break;
    case 's': document.getElementById('s-src').click(); break;
    case '1': setFilter('all'); break; case '2': setFilter('ap'); break; case '3': setFilter('fresh'); break;
    case '4': setFilter('trend'); break; case '5': setFilter('moving'); break;
  }
});

async function tick(){
  try{
    const [b,t]=await Promise.all([fetch('/api/board',{cache:'no-store'}), fetch('/api/theme',{cache:'no-store'})]);
    DATA=await b.json(); applyTheme(await t.json());
    if(TREND){ const live=(DATA.trends||[]).find(x=>x.query===TREND.query); if(live) TREND.ids=new Set(live.coverage_ids||[]); }
    render();
  }catch(e){ /* keep the last good board on screen */ }
}
tick(); setInterval(tick, 30000);
</script></body></html>
"""


def render_page() -> str:
    """The dashboard with this region's identity and the live theme baked in."""
    region = {
        "slug": config.REGION_SLUG,
        "name": config.REGION_NAME,
        "local": config.LOCAL_LABEL,
        "badges": config.GEO_BADGES,
        "sections": [name for name, _ in config.TOP_SECTIONS],
    }
    return (PAGE
            .replace("__THEME_VARS__", theme.css_vars())
            .replace("__REGION_JS__", json.dumps(region, ensure_ascii=False))
            .replace("__LOCAL_LOWER__", config.LOCAL_LABEL.lower())
            .replace("__SLUG__", config.REGION_SLUG))


class Handler(BaseHTTPRequestHandler):
    server_version = "APRadar/1.2"

    def log_message(self, fmt, *args):  # keep the console clean for tick output
        pass

    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(json.dumps(obj, default=str).encode("utf-8"),
                   "application/json; charset=utf-8", code)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        try:
            if path == "/":
                page = render_page()
                self._send(page.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/board":
                self._json(poll.snapshot())
            elif path == "/api/theme":
                self._json(theme.current())
            elif path == "/api/health":
                state = poll.snapshot()
                alive = poll.ensure_poller()
                stale = poll.is_stale()
                self._json({
                    "ok": state["last_error"] is None and alive and not stale,
                    "poller_alive": alive,
                    "stale": stale,
                    "last_tick": state["last_tick"],
                    "ticks": state["tick_count"],
                    "sources_ok": (state.get("stats") or {}).get("sources_ok"),
                    "sources_total": (state.get("stats") or {}).get("sources_total"),
                    "degraded": state.get("degraded", []),
                }, 200 if alive else 503)
            else:
                self._send(b"not found", "text/plain", 404)
        except Exception as e:  # a rendering bug must not take the server down
            self._json({"error": type(e).__name__, "detail": str(e)[:200]}, 500)


def serve() -> None:
    httpd = ThreadingHTTPServer((config.SERVER_HOST, config.SERVER_PORT), Handler)
    httpd.daemon_threads = True
    print(f"  dashboard  http://{config.SERVER_HOST}:{config.SERVER_PORT}", flush=True)
    httpd.serve_forever()
