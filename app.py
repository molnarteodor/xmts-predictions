import os
from flask import Flask, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XMTS AI · Instant Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-dark: #0a0a0a; --card-bg: #151515; --card-border: #282828;
    --accent-cyan: #06b6d4; --accent-gold: #eab308; --accent-orange: #f97316;
    --text-main: #f8fafc; --text-muted: #94a3b8; --bar-green: #22c55e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
  body { background: var(--bg-dark); color: var(--text-main); padding: 10px; }
  .container { max-width: 600px; margin: 0 auto; }
  .header-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
  .sync-btn { background: #1f1f1f; border: 1px solid var(--card-border); color: var(--text-muted); padding: 6px 10px; border-radius: 8px; font-size: 11px; font-weight: 700; cursor: pointer; }
  .tabs-wrapper { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 8px; scrollbar-width: none; }
  .tab-btn { background: #1c1c1c; border: 1px solid var(--card-border); color: var(--text-muted); padding: 9px 13px; border-radius: 10px; font-weight: 700; white-space: nowrap; cursor: pointer; font-size: 12px; }
  .tab-btn.active { background: rgba(234, 179, 8, 0.16); border-color: var(--accent-gold); color: #fff; }
  .league-filter-bar { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 10px; scrollbar-width: none; }
  .league-chip { background: #141414; border: 1px solid #2a2a2a; color: #cbd5e1; padding: 5px 10px; border-radius: 8px; font-size: 11px; font-weight: 600; white-space: nowrap; cursor: pointer; }
  .league-chip.active { background: var(--accent-gold); color: #000; border-color: var(--accent-gold); font-weight: 800; }
  .date-picker-bar { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 12px; scrollbar-width: none; }
  .date-chip { background: #1f1f1f; border: 1px solid var(--card-border); color: var(--text-muted); padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: bold; white-space: nowrap; cursor: pointer; }
  .date-chip.active { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }
  .league-section { margin-bottom: 20px; }
  .league-section-header { display: flex; justify-content: space-between; align-items: center; background: linear-gradient(90deg, rgba(234,179,8,0.16) 0%, rgba(22,22,22,0.95) 100%); border-left: 4px solid var(--accent-gold); border-radius: 10px; padding: 10px 14px; margin-bottom: 10px; font-weight: 800; font-size: 13px; color: #fff; }
  .league-badge-count { font-size: 11px; color: var(--accent-gold); background: rgba(0,0,0,0.5); padding: 3px 8px; border-radius: 6px; font-weight: 700; }
  .glass-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 16px; padding: 15px; margin-bottom: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.45); }
  .match-basic { display:flex; flex-direction:column; gap:8px; }
  .pred-row { display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.45); border-radius: 10px; padding: 10px; }
  .risk-tag { font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; text-transform: uppercase; }
  .risk-Scăzut { background: rgba(16,185,129,0.2); color: #34d399; }
  .risk-Mediu { background: rgba(245,158,11,0.2); color: #fbbf24; }
  .btn-expand { width: 100%; background: #1f1f1f; border: 1px solid #eab308; color: #fff; padding: 9px; border-radius: 10px; font-weight: bold; cursor: pointer; margin-top: 8px; font-size: 12px; }
  .golden-panel { display: none; margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--card-border); }
  .golden-header { text-align: center; color: var(--accent-gold); font-size: 15px; font-weight: 800; margin-bottom: 12px; text-transform: uppercase; }
  .h2h-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 12px; }
  .h2h-val { width: 65px; text-align: center; font-weight: 800; padding: 5px 4px; border-radius: 6px; background: #222; color: var(--accent-gold); }
  .h2h-label { flex: 1; text-align: center; color: #cbd5e1; font-weight: bold; }
  .bars-section { margin-top: 14px; }
  .bar-row { display: flex; align-items: center; margin-bottom: 7px; font-size: 12px; font-weight: bold; }
  .bar-label { width: 100px; color: #fff; }
  .bar-track { flex: 1; background: rgba(255,255,255,0.06); border-radius: 12px; height: 18px; position: relative; }
  .bar-fill { height: 100%; background: var(--bar-green); border-radius: 12px; display: flex; justify-content: flex-end; align-items: center; padding-right: 8px; color: #fff; font-size: 10px; }
  .acc-item { background: #1a1a1a; border: 1px solid #333; border-radius: 10px; margin-bottom: 8px; }
  .acc-header { padding: 10px 14px; display: flex; justify-content: space-between; cursor: pointer; color: #fff; font-weight: bold; font-size: 12px; }
  .acc-body { padding: 10px 14px; border-top: 1px solid #2a2a2a; font-size: 12px; color: var(--text-muted); display: none; line-height: 1.5; }
  .ticket-config { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 15px; }
  .odds-btn { background: #222; border: 1px solid var(--card-border); color: #fff; padding: 8px 12px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 13px; }
  .odds-btn.active { background: var(--accent-gold); color: #000; border-color: var(--accent-gold); }
  .ticket-match-row { display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; margin-bottom: 8px; font-size: 13px; }
  .result-badge { font-weight: 800; font-size: 11px; padding: 2px 6px; border-radius: 4px; }
  .res-pending { background: rgba(148, 163, 184, 0.1); color: #94a3b8; }
</style>
</head>
<body>
<div class="container">
  <div class="header-bar">
    <div style="font-size:20px; font-weight:800; color:var(--accent-gold);">XMTS PREDICTIONS</div>
    <button class="sync-btn" id="syncBtn" onclick="render()">🔄 Actualizează</button>
  </div>

  <div class="tabs-wrapper">
    <button class="tab-btn active" onclick="switchTab('meciuri', this)">⚽ Ligi Naționale</button>
    <button class="tab-btn" onclick="switchTab('cl', this)" style="border-color:var(--accent-cyan); color:var(--accent-cyan);">🏆 Champions League</button>
    <button class="tab-btn" onclick="switchTab('el', this)" style="border-color:var(--accent-orange); color:var(--accent-orange);">🟠 Europa League</button>
    <button class="tab-btn" onclick="switchTab('bilete', this)" style="border-color:var(--accent-gold); color:var(--accent-gold);">🎟️ Generator Bilete</button>
  </div>

  <div id="dateSelectorContainer"></div>
  <div id="leagueFilterContainer"></div>
  <div id="content"><div class="glass-card" style="text-align:center;">Se încarcă...</div></div>
</div>

<script>
const MATCHES = [
  { league: "UEFA Champions League", league_code: "CL", league_icon: "🏆", league_priority: 1, is_cl: true, is_el: false, date: "2026-10-27", time: "22:00", home: "Real Madrid", away: "AC Milan", bookmaker: "Model AI", principal: "1 (Real Madrid)", principal_pct: 68.4, risc: "Scăzut", exp_goals_home: 2.1, exp_goals_away: 0.9, form_home: "WWDWW", form_away: "WDWWL", probs: {home: 68.4, draw: 18.2, away: 13.4, over25: 64.0, btts: 52.0}, market_options: [{name: "1 (Real Madrid)", prob: 0.684, odds: 1.45}, {name: "Peste 2.5 goluri", prob: 0.64, odds: 1.72}] },
  { league: "UEFA Champions League", league_code: "CL", league_icon: "🏆", league_priority: 1, is_cl: true, is_el: false, date: "2026-10-27", time: "22:00", home: "Manchester City", away: "Borussia Dortmund", bookmaker: "Model AI", principal: "Peste 2.5 goluri", principal_pct: 71.2, risc: "Scăzut", exp_goals_home: 2.3, exp_goals_away: 1.2, form_home: "WWWWW", form_away: "WDWLW", probs: {home: 62.1, draw: 20.0, away: 17.9, over25: 71.2, btts: 60.5}, market_options: [{name: "Peste 2.5 goluri", prob: 0.712, odds: 1.58}, {name: "1 (Manchester City)", prob: 0.621, odds: 1.52}] },
  { league: "UEFA Champions League", league_code: "CL", league_icon: "🏆", league_priority: 1, is_cl: true, is_el: false, date: "2026-10-28", time: "22:00", home: "Barcelona", away: "Bayern Munich", bookmaker: "Model AI", principal: "GG - Ambele marchează", principal_pct: 65.5, risc: "Mediu", exp_goals_home: 1.8, exp_goals_away: 1.7, form_home: "WWWDW", form_away: "WWWWW", probs: {home: 44.0, draw: 25.5, away: 30.5, over25: 68.0, btts: 65.5}, market_options: [{name: "GG - Ambele marchează", prob: 0.655, odds: 1.62}, {name: "Peste 2.5 goluri", prob: 0.68, odds: 1.60}] },
  { league: "UEFA Europa League", league_code: "EL", league_icon: "🟠", league_priority: 2, is_cl: false, is_el: true, date: "2026-10-29", time: "22:00", home: "FCSB", away: "Porto", bookmaker: "Model AI", principal: "2 (Porto)", principal_pct: 58.2, risc: "Mediu", exp_goals_home: 0.9, exp_goals_away: 1.8, form_home: "DWLWW", form_away: "WWWDW", probs: {home: 22.0, draw: 19.8, away: 58.2, over25: 54.0, btts: 48.0}, market_options: [{name: "2 (Porto)", prob: 0.582, odds: 1.75}, {name: "Sub 2.5 goluri", prob: 0.56, odds: 1.80}] },
  { league: "UEFA Europa League", league_code: "EL", league_icon: "🟠", league_priority: 2, is_cl: false, is_el: true, date: "2026-10-29", time: "22:00", home: "Roma", away: "Nice", bookmaker: "Model AI", principal: "1 (Roma)", principal_pct: 61.5, risc: "Scăzut", exp_goals_home: 1.9, exp_goals_away: 1.0, form_home: "WDWWL", form_away: "DWWDL", probs: {home: 61.5, draw: 23.0, away: 15.5, over25: 55.0, btts: 51.0}, market_options: [{name: "1 (Roma)", prob: 0.615, odds: 1.65}, {name: "Peste 1.5 goluri", prob: 0.75, odds: 1.35}] },
  { league: "Premier League (Anglia)", league_code: "E0", league_icon: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", league_priority: 10, is_cl: false, is_el: false, date: "2026-10-24", time: "17:00", home: "Arsenal", away: "Chelsea", bookmaker: "Model AI", principal: "1 (Arsenal)", principal_pct: 63.2, risc: "Scăzut", exp_goals_home: 2.0, exp_goals_away: 1.0, form_home: "WWWWV", form_away: "WDWWL", probs: {home: 63.2, draw: 21.0, away: 15.8, over25: 59.0, btts: 53.0}, market_options: [{name: "1 (Arsenal)", prob: 0.632, odds: 1.58}, {name: "Peste 2.5 goluri", prob: 0.59, odds: 1.78}] },
  { league: "Premier League (Anglia)", league_code: "E0", league_icon: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", league_priority: 10, is_cl: false, is_el: false, date: "2026-10-24", time: "19:30", home: "Liverpool", away: "Manchester United", bookmaker: "Model AI", principal: "Peste 2.5 goluri", principal_pct: 69.0, risc: "Scăzut", exp_goals_home: 2.2, exp_goals_away: 1.3, form_home: "WWWDW", form_away: "DWLWW", probs: {home: 59.0, draw: 22.0, away: 19.0, over25: 69.0, btts: 64.0}, market_options: [{name: "Peste 2.5 goluri", prob: 0.69, odds: 1.60}, {name: "GG - Ambele marchează", prob: 0.64, odds: 1.68}] },
  { league: "La Liga (Spania)", league_code: "SP1", league_icon: "🇪🇸", league_priority: 11, is_cl: false, is_el: false, date: "2026-10-24", time: "22:00", home: "Real Madrid", away: "Barcelona", bookmaker: "Model AI", principal: "GG - Ambele marchează", principal_pct: 72.5, risc: "Scăzut", exp_goals_home: 2.1, exp_goals_away: 1.9, form_home: "WWWWW", form_away: "WWWDW", probs: {home: 45.0, draw: 24.0, away: 31.0, over25: 75.0, btts: 72.5}, market_options: [{name: "GG - Ambele marchează", prob: 0.725, odds: 1.52}, {name: "Peste 2.5 goluri", prob: 0.75, odds: 1.50}] },
  { league: "Serie A (Italia)", league_code: "I1", league_icon: "🇮🇹", league_priority: 12, is_cl: false, is_el: false, date: "2026-10-24", time: "19:00", home: "Juventus", away: "Inter", bookmaker: "Model AI", principal: "Sub 2.5 goluri", principal_pct: 61.0, risc: "Mediu", exp_goals_home: 1.1, exp_goals_away: 1.0, form_home: "WDWWL", form_away: "WWWDW", probs: {home: 38.0, draw: 34.0, away: 28.0, over25: 39.0, btts: 45.0}, market_options: [{name: "Sub 2.5 goluri", prob: 0.61, odds: 1.70}, {name: "Șansă Dublă 1X", prob: 0.72, odds: 1.32}] },
  { league: "SuperLiga (România)", league_code: "RO1", league_icon: "🇷🇴", league_priority: 15, is_cl: false, is_el: false, date: "2026-10-24", time: "20:30", home: "FCSB", away: "Rapid Bucuresti", bookmaker: "Model AI", principal: "1 (FCSB)", principal_pct: 57.0, risc: "Mediu", exp_goals_home: 1.7, exp_goals_away: 1.1, form_home: "WWWDW", form_away: "WDWLL", probs: {home: 57.0, draw: 25.0, away: 18.0, over25: 53.0, btts: 52.0}, market_options: [{name: "1 (FCSB)", prob: 0.57, odds: 1.80}, {name: "Peste 1.5 goluri", prob: 0.78, odds: 1.38}] }
];

let currentTab = 'meciuri';
let selectedDate = 'ALL';
let selectedClDate = 'ALL';
let selectedElDate = 'ALL';
let selectedLeagueFilter = 'ALL';
let selectedTargetOdds = 10;

function toggleGoldenPanel(btn) {
  const panel = btn.nextElementSibling;
  const isHidden = panel.style.display === 'none' || panel.style.display === '';
  panel.style.display = isHidden ? 'block' : 'none';
  btn.innerText = isHidden ? 'Ascunde Analiză' : 'Deschide Analiză, Formă & Cartonașe';
}

function toggleAccordion(header) {
  const body = header.nextElementSibling;
  body.style.display = body.style.display === 'block' ? 'none' : 'block';
}

function renderMatchCard(m) {
  const p = m.probs;
  const pronostic = m.principal || "Echilibrat";
  const pronostic_pct = m.principal_pct || "-";
  const cc = m.corners_cards || {exp_cards: 4.3, exp_corners: 9.6};
  
  return `
    <div class="glass-card">
      <div class="match-basic">
        <div style="font-size:11px;color:var(--text-muted);display:flex;justify-content:space-between;align-items:center;">
          <span>${m.date} · ${m.bookmaker}</span>
          <span class="result-badge res-pending">🕒 ${m.time}</span>
        </div>
        <div style="font-size:16px;font-weight:800;text-align:center; margin-top:2px;">${m.home} <span style="color:var(--accent-gold);">VS</span> ${m.away}</div>
        <div class="pred-row" style="margin-top:4px;">
          <span style="font-size:13px;font-weight:700;color:#fff;">⭐ ${pronostic} <span style="color:var(--accent-gold);">(${pronostic_pct}%)</span></span>
          <span class="risk-tag risk-${m.risc}">${m.risc}</span>
        </div>
      </div>
      <button class="btn-expand" onclick="toggleGoldenPanel(this)">Deschide Analiză, Formă & Cartonașe</button>
      <div class="golden-panel">
        <div class="golden-header">PROBABILITĂȚI & EXPECTED GOALS</div>
        <div class="h2h-row">
          <div class="h2h-val">${m.exp_goals_home}</div>
          <div class="h2h-label">Expected Goals (xG)</div>
          <div class="h2h-val">${m.exp_goals_away}</div>
        </div>
        <div class="bars-section">
          <div class="bar-row"><div class="bar-label">1 (Gazde):</div><div class="bar-track"><div class="bar-fill" style="width: ${p.home}%;">${p.home}%</div></div></div>
          <div class="bar-row"><div class="bar-label">X (Egal):</div><div class="bar-track"><div class="bar-fill" style="width: ${p.draw}%; background:#3b82f6;">${p.draw}%</div></div></div>
          <div class="bar-row"><div class="bar-label">2 (Oaspeți):</div><div class="bar-track"><div class="bar-fill" style="width: ${p.away}%; background:#a855f7;">${p.away}%</div></div></div>
          <div class="bar-row"><div class="bar-label">Peste 2.5:</div><div class="bar-track"><div class="bar-fill" style="width: ${p.over25}%;">${p.over25}%</div></div></div>
          <div class="bar-row"><div class="bar-label">GG (Ambele):</div><div class="bar-track"><div class="bar-fill" style="width: ${p.btts}%;">${p.btts}%</div></div></div>
        </div>
        <div style="margin-top: 14px;">
          <div class="acc-item"><div class="acc-header" onclick="toggleAccordion(this)"><div>📈 Formă Echipe</div><div>▼</div></div><div class="acc-body" style="display:block;">🏠 <b>${m.home}:</b> ${m.form_home}<br>✈️ <b>${m.away}:</b> ${m.form_away}</div></div>
          <div class="acc-item"><div class="acc-header" onclick="toggleAccordion(this)"><div>🟨 Cartonașe & Cornere</div><div>▼</div></div><div class="acc-body" style="display:block;">🟨 Cartonașe: ~<b>${cc.exp_cards}</b><br>🚩 Cornere: ~<b>${cc.exp_corners}</b></div></div>
        </div>
      </div>
    </div>`;
}

function getTabMatches() {
  return MATCHES.filter(m => {
    if (currentTab === 'cl') return m.is_cl;
    if (currentTab === 'el') return m.is_el;
    return !m.is_cl && !m.is_el;
  });
}

function renderDateSelector() {
  if (currentTab === 'bilete') return '';
  const tabMatches = getTabMatches();
  const datesSet = [...new Set(tabMatches.map(m => m.date))].sort();
  let activeD = (currentTab === 'cl') ? selectedClDate : (currentTab === 'el' ? selectedElDate : selectedDate);
  
  let chips = `<button class="date-chip ${activeD === 'ALL' ? 'active' : ''}" onclick="selectDate('ALL')">📅 Toate (${tabMatches.length})</button>`;
  chips += datesSet.map(d => `<button class="date-chip ${activeD === d ? 'active' : ''}" onclick="selectDate('${d}')">${d}</button>`).join('');
  return `<div class="date-picker-bar">${chips}</div>`;
}

function renderLeagueFilter(dayMatches) {
  if (currentTab !== 'meciuri' || !dayMatches.length) return '';
  const leagues = [...new Set(dayMatches.map(m => m.league))];
  let html = `<button class="league-chip ${selectedLeagueFilter === 'ALL' ? 'active' : ''}" onclick="setLeagueFilter('ALL')">Toate Ligile (${dayMatches.length})</button>`;
  leagues.forEach(l => {
    const count = dayMatches.filter(m => m.league === l).length;
    html += `<button class="league-chip ${selectedLeagueFilter === l ? 'active' : ''}" onclick="setLeagueFilter('${l}')">${l} (${count})</button>`;
  });
  return `<div class="league-filter-bar">${html}</div>`;
}

function setLeagueFilter(lName) { selectedLeagueFilter = lName; render(); }
function selectDate(d) {
  selectedLeagueFilter = 'ALL';
  if (currentTab === 'cl') selectedClDate = d;
  else if (currentTab === 'el') selectedElDate = d;
  else selectedDate = d;
  render();
}

function renderGroupedSections(matches) {
  if (!matches.length) return `<div class="glass-card" style="text-align:center;">Niciun meci găsit.</div>`;
  const groups = {};
  matches.forEach(m => {
    if (!groups[m.league]) groups[m.league] = { icon: m.league_icon, items: [] };
    groups[m.league].items.push(m);
  });
  return Object.keys(groups).map(leagueName => `
    <div class="league-section">
      <div class="league-section-header"><span>${groups[leagueName].icon} ${leagueName}</span><span class="league-badge-count">${groups[leagueName].items.length} meciuri</span></div>
      ${groups[leagueName].items.map(renderMatchCard).join('')}
    </div>
  `).join('');
}

function renderTicketGenerator() {
  let pool = [];
  MATCHES.forEach(m => {
    if (m.market_options) {
      m.market_options.forEach(opt => {
        if (opt.prob >= 0.50 && opt.odds >= 1.25 && opt.odds <= 3.50) {
          pool.push({ match: `${m.home} - ${m.away}`, league: `${m.league} (${m.date})`, market: opt.name, odds: opt.odds, prob: opt.prob, score: opt.prob * (1.0 / Math.abs(opt.odds - 1.65)) });
        }
      });
    }
  });
  pool.sort((a, b) => b.score - a.score);

  let selectedPicks = [], currentOdds = 1.0;
  for (let item of pool) {
    if (selectedPicks.length >= 10) break;
    if (!selectedPicks.some(p => p.match === item.match) && currentOdds < selectedTargetOdds) {
      selectedPicks.push(item);
      currentOdds *= item.odds;
    }
  }

  let oddsButtons = [5, 10, 20, 50].map(val => `<button class="odds-btn ${selectedTargetOdds === val ? 'active' : ''}" onclick="setTargetOdds(${val})">Cotă ${val}</button>`).join('');
  let picksHtml = selectedPicks.map((p, idx) => `
    <div class="ticket-match-row">
      <div><div style="font-weight:bold; color:#fff;">${idx+1}. ${p.match}</div><div style="font-size:11px; color:var(--text-muted);">${p.league}</div><div style="font-size:12px; color:var(--accent-cyan);">👉 <b>${p.market}</b></div></div>
      <div style="text-align:right;"><div style="font-weight:800; font-size:15px; color:var(--accent-gold);">@${p.odds}</div><div style="font-size:10px; color:#34d399;">Prob: ${Math.round(p.prob*100)}%</div></div>
    </div>
  `).join('');

  return `
    <div class="glass-card">
      <div style="font-weight:800; font-size:16px; margin-bottom:10px; color:var(--accent-gold);">🎟️ Generator Bilete Inteligente</div>
      <div class="ticket-config">${oddsButtons}</div>
      <div style="background:rgba(0,0,0,0.5); border:1px solid var(--card-border); border-radius:12px; padding:12px; margin-top:15px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid #333; padding-bottom:8px;">
          <span>Cotă Țintă: ~${selectedTargetOdds}</span><span style="background:var(--accent-gold); color:#000; font-weight:800; padding:4px 10px; border-radius:8px;">Total: ${currentOdds.toFixed(2)}</span>
        </div>
        ${picksHtml || '<div style="text-align:center; padding:20px; color:var(--text-muted);">Fără selecții.</div>'}
      </div>
    </div>`;
}

function setTargetOdds(val) { selectedTargetOdds = val; render(); }

function render() {
  document.getElementById('dateSelectorContainer').innerHTML = renderDateSelector();
  const c = document.getElementById('content'), lc = document.getElementById('leagueFilterContainer');

  if (currentTab === 'bilete') {
    lc.innerHTML = '';
    c.innerHTML = renderTicketGenerator();
    return;
  }

  const activeD = (currentTab === 'cl') ? selectedClDate : (currentTab === 'el' ? selectedElDate : selectedDate);
  const tabMatches = getTabMatches();
  const dayMatches = (activeD === 'ALL') ? tabMatches : tabMatches.filter(m => m.date === activeD);

  lc.innerHTML = renderLeagueFilter(dayMatches);
  const filtered = (currentTab === 'meciuri' && selectedLeagueFilter !== 'ALL') ? dayMatches.filter(m => m.league === selectedLeagueFilter) : dayMatches;
  c.innerHTML = renderGroupedSections(filtered);
}

function switchTab(t, btn) {
  currentTab = t;
  selectedLeagueFilter = 'ALL';
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  render();
}

render();
</script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
