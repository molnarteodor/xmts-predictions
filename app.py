import os
import json
import psycopg2
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

# .strip() sterge automat orice Enter sau spatiu ramas la finalul URL-ului in Render
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def get_db_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    return None

def init_db():
    conn = get_db_connection()
    if not conn:
        print("ATENTIE: DATABASE_URL nu este setat!")
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jack_project (
                id SERIAL PRIMARY KEY,
                data TEXT NOT NULL
            );
        """)
        cur.execute("SELECT COUNT(*) FROM jack_project;")
        if cur.fetchone()[0] == 0:
            default_data = {
                "initial_bankroll": 500.0,
                "target_bankroll": 800.0,
                "bankroll": 500.0,
                "bets": []
            }
            cur.execute("INSERT INTO jack_project (data) VALUES (%s);", [json.dumps(default_data)])
        conn.commit()
        cur.close()
        conn.close()
        print("PostgreSQL conectat si initializat cu succes!")
    except Exception as e:
        print("Eroare la init_db:", e)

init_db()

@app.route("/api/project", methods=["GET", "POST"])
def api_project():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Fara conexiune DB"}), 500
    try:
        cur = conn.cursor()
        if request.method == "POST":
            body = request.get_json(silent=True)
            if body and "bankroll" in body and "bets" in body:
                cur.execute("DELETE FROM jack_project;")
                cur.execute("INSERT INTO jack_project (data) VALUES (%s);", [json.dumps(body)])
                conn.commit()
                cur.close()
                conn.close()
                print(f"Salvat in DB: bankroll={body['bankroll']}, pariuri={len(body['bets'])}")
                return jsonify(body)

        cur.execute("SELECT data FROM jack_project ORDER BY id DESC LIMIT 1;")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            data = row[0]
            return jsonify(json.loads(data) if isinstance(data, str) else data)
    except Exception as e:
        print("Eroare API DB:", e)
        if conn:
            conn.close()

    return jsonify({"initial_bankroll": 500.0, "target_bankroll": 800.0, "bankroll": 500.0, "bets": []})

HTML_PAGE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<title>XMTS · Neural HUD</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root { --bg:#020408; --card-bg:rgba(10,15,28,0.75); --card-border:rgba(0,243,255,0.22); --neon-cyan:#00f3ff; --neon-gold:#ffb703; --neon-green:#06d6a0; --neon-red:#ef476f; --text-main:#f8fafc; --text-muted:#64748b; }
  * { box-sizing:border-box; margin:0; padding:0; font-family:'Plus Jakarta Sans',sans-serif; -webkit-tap-highlight-color:transparent; }
  html, body { height:100%; width:100%; background:var(--bg); color:var(--text-main); overflow:hidden; }
  .app-shell { display:flex; flex-direction:column; height:100dvh; max-width:520px; margin:0 auto; position:relative; }
  .top-hud { display:flex; justify-content:space-between; align-items:center; padding:14px 18px; background:rgba(2,4,8,0.9); backdrop-filter:blur(20px); border-bottom:1px solid var(--card-border); z-index:20; }
  .hud-brand { display:flex; align-items:center; gap:10px; }
  .hud-logo { width:38px; height:38px; border-radius:12px; background:linear-gradient(135deg,var(--neon-cyan),var(--neon-gold)); display:flex; align-items:center; justify-content:center; font-family:'Orbitron',sans-serif; font-weight:900; color:#020408; font-size:16px; box-shadow:0 0 15px rgba(0,243,255,0.4); }
  .hud-title { font-family:'Orbitron',sans-serif; font-size:14px; font-weight:900; letter-spacing:1px; color:#fff; display:block; }
  .hud-status { font-size:10px; color:var(--neon-green); font-weight:700; text-transform:uppercase; }
  .hud-bank { background:rgba(6,214,160,0.1); border:1px solid rgba(6,214,160,0.4); color:var(--neon-green); padding:8px 14px; border-radius:14px; font-family:'Orbitron',sans-serif; font-size:13px; font-weight:700; cursor:pointer; }
  .sub-bars { background:rgba(5,9,18,0.6); border-bottom:1px solid var(--card-border); padding:10px 14px 8px; }
  .h-scroll { display:flex; gap:8px; overflow-x:auto; scrollbar-width:none; padding-bottom:2px; }
  .h-scroll::-webkit-scrollbar { display:none; }
  .cyber-chip { background:rgba(15,23,42,0.8); border:1px solid var(--card-border); color:var(--text-muted); padding:7px 14px; border-radius:10px; font-size:11px; font-weight:700; white-space:nowrap; cursor:pointer; }
  .cyber-chip.active { background:var(--neon-cyan); color:#020408; border-color:var(--neon-cyan); font-weight:800; }
  .cyber-chip-gold.active { background:var(--neon-gold); color:#020408; border-color:var(--neon-gold); }
  .viewport { flex:1; overflow-y:auto; padding:14px 14px 90px; -webkit-overflow-scrolling:touch; }
  .cyber-sec-head { display:flex; justify-content:space-between; align-items:center; background:linear-gradient(90deg,rgba(0,243,255,0.1),rgba(10,15,28,0.6)); border-left:3px solid var(--neon-cyan); border-radius:8px; padding:9px 14px; margin:14px 0 10px; font-family:'Orbitron',sans-serif; font-size:11px; font-weight:700; color:var(--neon-cyan); }
  .cyber-card { background:var(--card-bg); border:1px solid var(--card-border); border-radius:18px; padding:16px; margin-bottom:12px; box-shadow:0 10px 30px rgba(0,0,0,0.6); }
  .card-top { display:flex; justify-content:space-between; align-items:center; font-size:11px; color:var(--text-muted); margin-bottom:10px; }
  .status-badge { padding:3px 9px; border-radius:6px; font-weight:800; font-size:9px; font-family:'Orbitron',sans-serif; }
  .st-live { background:rgba(239,71,111,0.2); color:var(--neon-red); border:1px solid var(--neon-red); }
  .st-ft { background:rgba(6,214,160,0.2); color:var(--neon-green); border:1px solid var(--neon-green); }
  .st-ns { background:rgba(255,255,255,0.05); color:#cbd5e1; border:1px solid rgba(255,255,255,0.1); }
  .teams-container { display:flex; justify-content:space-between; align-items:center; margin:8px 0 12px; }
  .team-name { width:40%; font-size:14px; font-weight:800; line-height:1.3; }
  .team-name.away { text-align:right; }
  .score-display { background:rgba(15,23,42,0.9); border:1px solid var(--card-border); padding:6px 14px; border-radius:12px; font-family:'Orbitron',sans-serif; font-weight:900; font-size:13px; color:var(--neon-gold); }
  .prediction-panel { background:rgba(2,4,8,0.8); border:1px solid var(--card-border); border-radius:14px; padding:12px 14px; display:flex; justify-content:space-between; align-items:center; }
  .pred-main { font-size:12px; font-weight:800; color:#fff; }
  .pred-sub { font-size:10px; color:var(--text-muted); margin-top:3px; }
  .odd-chip { background:rgba(255,183,3,0.12); border:1px solid var(--neon-gold); color:var(--neon-gold); padding:5px 11px; border-radius:10px; font-family:'Orbitron',sans-serif; font-weight:800; font-size:12px; }
  .action-bar { display:flex; gap:8px; margin-top:10px; }
  .cyber-btn { flex:1; background:rgba(15,23,42,0.9); border:1px solid var(--card-border); color:var(--text-main); padding:9px; border-radius:12px; font-size:11px; font-weight:700; cursor:pointer; }
  .cyber-btn.accent { background:rgba(6,214,160,0.15); border-color:rgba(6,214,160,0.5); color:var(--neon-green); flex:0.7; }
  .analytics-drawer { display:none; margin-top:12px; padding-top:12px; border-top:1px dashed var(--card-border); font-size:11px; }
  .matrix-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:6px; margin-bottom:10px; }
  .matrix-cell { background:rgba(15,23,42,0.8); padding:8px; border-radius:10px; text-align:center; border:1px solid var(--card-border); }
  .matrix-cell b { display:block; color:var(--neon-gold); font-family:'Orbitron',sans-serif; font-size:12px; margin-top:3px; }
  .vault-hero { background:linear-gradient(135deg,#091526,#020408); border:1px solid rgba(0,243,255,0.4); border-radius:22px; padding:20px; margin-bottom:16px; }
  .vault-profile { display:flex; align-items:center; gap:14px; margin-bottom:16px; }
  .vault-avatar { width:64px; height:64px; border-radius:50%; border:2.5px solid var(--neon-cyan); background:#020408; display:flex; align-items:center; justify-content:center; font-size:28px; flex-shrink:0; }
  .vault-quote { font-style:italic; font-size:11px; color:var(--neon-cyan); background:rgba(0,243,255,0.06); padding:9px 13px; border-radius:12px; border-left:2.5px solid var(--neon-cyan); }
  .vault-kpi-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:14px; }
  .vault-kpi { background:rgba(2,4,8,0.6); border:1px solid var(--card-border); border-radius:12px; padding:10px; text-align:center; }
  .v-lbl { font-size:9px; color:var(--text-muted); text-transform:uppercase; font-family:'Orbitron',sans-serif; }
  .v-val { font-size:13px; font-family:'Orbitron',sans-serif; font-weight:900; margin-top:4px; }
  .cyber-progress { width:100%; height:10px; background:rgba(255,255,255,0.04); border-radius:99px; margin-top:14px; overflow:hidden; border:1px solid var(--card-border); }
  .cyber-progress-fill { height:100%; background:linear-gradient(90deg,var(--neon-green),var(--neon-cyan)); border-radius:99px; transition:0.4s; }
  .bet-ticket { background:var(--card-bg); border:1px solid var(--card-border); border-radius:16px; padding:14px; margin-bottom:10px; }
  .bet-ticket-actions { display:flex; gap:6px; margin-top:10px; flex-wrap:wrap; }
  .t-btn { flex:1; padding:7px; border-radius:10px; border:1px solid var(--card-border); font-size:11px; font-weight:800; cursor:pointer; background:rgba(15,23,42,0.9); color:#fff; min-width:65px; }
  .t-win { background:rgba(6,214,160,0.15); border-color:var(--neon-green); color:var(--neon-green); }
  .t-loss { background:rgba(239,71,111,0.15); border-color:var(--neon-red); color:var(--neon-red); }
  .t-edit { background:rgba(0,243,255,0.15); border-color:var(--neon-cyan); color:var(--neon-cyan); }
  .bottom-hud-nav { position:fixed; bottom:0; left:50%; transform:translateX(-50%); width:100%; max-width:520px; height:72px; background:rgba(2,4,8,0.94); backdrop-filter:blur(22px); border-top:1px solid var(--card-border); display:flex; justify-content:space-around; align-items:center; z-index:30; }
  .hud-nav-item { display:flex; flex-direction:column; align-items:center; justify-content:center; color:var(--text-muted); font-size:9px; font-family:'Orbitron',sans-serif; font-weight:700; gap:4px; cursor:pointer; background:none; border:none; width:25%; height:100%; text-transform:uppercase; }
  .hud-nav-item .ico { font-size:20px; }
  .hud-nav-item.active { color:var(--neon-cyan); text-shadow:0 0 12px rgba(0,243,255,0.6); }
</style>
</head>
<body>
<div class="app-shell">
  <div class="top-hud">
    <div class="hud-brand">
      <div class="hud-logo">J</div>
      <div>
        <span class="hud-title">JACK 500 HUD</span>
        <span class="hud-status" id="liveClock">● DB Synced</span>
      </div>
    </div>
    <div class="hud-bank" onclick="switchNav('proiect')">💰 <span id="topBankroll">500.00</span> RON</div>
  </div>
  <div class="sub-bars" id="subBars">
    <div class="h-scroll" id="dateBar"></div>
    <div class="h-scroll" id="leagueBar" style="margin-top:6px;"></div>
  </div>
  <div class="viewport" id="viewport"></div>
  <nav class="bottom-hud-nav">
    <button class="hud-nav-item active" id="nav-meciuri" onclick="switchNav('meciuri')"><span class="ico">⚽</span><span>Meciuri</span></button>
    <button class="hud-nav-item" id="nav-europa" onclick="switchNav('europa')"><span class="ico">🏆</span><span>Europa</span></button>
    <button class="hud-nav-item" id="nav-proiect" onclick="switchNav('proiect')"><span class="ico">⚡</span><span>Jack Vault</span></button>
    <button class="hud-nav-item" id="nav-bilete" onclick="switchNav('bilete')"><span class="ico">🎟️</span><span>Bilete</span></button>
  </nav>
</div>
<script>
const LEAGUES = [
  {slug:"eng.1",name:"Premier League",icon:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",cat:"nat"},
  {slug:"esp.1",name:"La Liga",icon:"🇪🇸",cat:"nat"},
  {slug:"ita.1",name:"Serie A",icon:"🇮🇹",cat:"nat"},
  {slug:"ger.1",name:"Bundesliga",icon:"🇩🇪",cat:"nat"},
  {slug:"fra.1",name:"Ligue 1",icon:"🇫🇷",cat:"nat"},
  {slug:"rou.1",name:"SuperLiga României",icon:"🇷🇴",cat:"nat"},
  {slug:"ned.1",name:"Eredivisie",icon:"🇳🇱",cat:"nat"},
  {slug:"por.1",name:"Primeira Liga",icon:"🇵🇹",cat:"nat"},
  {slug:"tur.1",name:"Süper Lig",icon:"🇹🇷",cat:"nat"},
  {slug:"gre.1",name:"Super League Grecia",icon:"🇬🇷",cat:"nat"},
  {slug:"uefa.champions",name:"UEFA Champions League",icon:"🏆",cat:"eu"},
  {slug:"uefa.europa",name:"UEFA Europa League",icon:"🟠",cat:"eu"},
  {slug:"uefa.europa.conf",name:"UEFA Conference League",icon:"🟢",cat:"eu"}
];
const ELITE_BOOST = {"real madrid":0.45,"barcelona":0.45,"manchester city":0.45,"bayern munich":0.45,"liverpool":0.4,"arsenal":0.4,"inter":0.36,"psg":0.4,"paris saint-germain":0.4,"bayer leverkusen":0.34,"borussia dortmund":0.32,"atletico madrid":0.32,"juventus":0.3,"ac milan":0.3,"napoli":0.32,"sporting cp":0.3,"benfica":0.28,"fc porto":0.28,"fcsb":0.24,"cfr cluj":0.2,"universitatea craiova":0.2,"galatasaray":0.26,"fenerbahce":0.26};

let currentNav = "meciuri", selectedDate = "", selectedLeague = "ALL", cacheByDate = {}, europaMatches = [], targetTicketOdds = 5;
let project = { initial_bankroll: 500.0, target_bankroll: 800.0, bankroll: 500.0, bets: [] };

const roDateStr = d => d.toLocaleDateString("sv-SE", { timeZone: "Europe/Bucharest" });
const roTimeStr = d => d.toLocaleTimeString("ro-RO", { timeZone: "Europe/Bucharest", hour: "2-digit", minute: "2-digit" });

function getDatesList() {
  const list = [], now = new Date(), labels = {"-1":"Ieri","0":"Azi","1":"Mâine"};
  for (let i = -1; i <= 5; i++) {
    const d = new Date(now.getTime() + i * 86400000), iso = roDateStr(d), p = iso.split("-"), s = p[2] + "." + p[1];
    list.push({ iso, ymd: iso.replace(/-/g, ""), label: labels[String(i)] ? `${labels[String(i)]} (${s})` : s });
  }
  return list;
}

function formScore(f) {
  let s = 0;
  for (let ch of (f || "").toUpperCase().slice(-5)) s += ch === "W" ? 0.08 : (ch === "D" ? 0.01 : (ch === "L" ? -0.07 : 0));
  return s;
}

function poissonPmf(k, lam) {
  let f = 1;
  for (let i = 2; i <= k; i++) f *= i;
  return Math.exp(-lam) * Math.pow(lam, k) / f;
}

function analyzeMatch(ev, lg) {
  const comp = ev.competitions[0], cs = comp.competitors;
  const home = cs.find(c => c.homeAway === "home") || cs[0], away = cs.find(c => c.homeAway === "away") || cs[1];
  const hName = home.team.displayName || home.team.name, aName = away.team.displayName || away.team.name;
  const dt = new Date(comp.date || ev.date), stState = (comp.status && comp.status.type && comp.status.type.state) || "pre";
  const hScore = home.score !== undefined ? parseInt(home.score, 10) : null, aScore = away.score !== undefined ? parseInt(away.score, 10) : null;
  const hForm = home.form || "WWDWL", aForm = away.form || "WDLWD";
  const hBoost = (ELITE_BOOST[hName.toLowerCase()] || 0) + formScore(hForm), aBoost = (ELITE_BOOST[aName.toLowerCase()] || 0) + formScore(aForm);
  let seed = 0;
  for (let ch of (hName + aName)) seed = (seed * 31 + ch.charCodeAt(0)) % 1000;
  const micro = (seed % 20 - 10) / 100;
  const lamH = Math.max(0.65, Math.min(3.1, 1.4 + hBoost - aBoost * 0.35 + micro));
  const lamA = Math.max(0.5, Math.min(2.7, 1.05 + aBoost - hBoost * 0.35 - micro * 0.5));
  let pH = 0, pD = 0, pA = 0, pO15 = 0, pO25 = 0, pGG = 0;
  for (let h = 0; h <= 7; h++) for (let a = 0; a <= 7; a++) {
    const p = poissonPmf(h, lamH) * poissonPmf(a, lamA);
    if (h > a) pH += p; else if (h === a) pD += p; else pA += p;
    if (h + a > 1.5) pO15 += p;
    if (h + a > 2.5) pO25 += p;
    if (h > 0 && a > 0) pGG += p;
  }
  const tot = pH + pD + pA; pH /= tot; pD /= tot; pA /= tot;
  const p1X = pH + pD, pX2 = pA + pD;
  const candidates = [
    { name: `1 (${hName})`, prob: pH, odd: Math.max(1.2, Math.min(6.5, +(0.94 / pH).toFixed(2))) },
    { name: `2 (${aName})`, prob: pA, odd: Math.max(1.22, Math.min(7.5, +(0.94 / pA).toFixed(2))) },
    { name: "Peste 1.5 Goluri", prob: pO15, odd: Math.max(1.18, Math.min(1.65, +(0.94 / pO15).toFixed(2))) },
    { name: "Peste 2.5 Goluri", prob: pO25, odd: Math.max(1.42, Math.min(2.45, +(0.94 / pO25).toFixed(2))) },
    { name: "GG (Ambele marchează)", prob: pGG, odd: Math.max(1.48, Math.min(2.4, +(0.94 / pGG).toFixed(2))) },
    { name: "Șansă Dublă 1X", prob: p1X, odd: Math.max(1.15, Math.min(1.85, +(0.94 / p1X).toFixed(2))) },
    { name: "Șansă Dublă X2", prob: pX2, odd: Math.max(1.16, Math.min(1.95, +(0.94 / pX2).toFixed(2))) }
  ];
  let valid = candidates.filter(c => c.odd >= 1.3 && c.odd <= 2.2);
  if (!valid.length) valid = candidates;
  valid.sort((a, b) => b.prob - a.prob);
  const best = valid[0];
  return {
    id: ev.id, league: lg.name, icon: lg.icon, cat: lg.cat, date: roDateStr(dt), time: roTimeStr(dt),
    status: stState === "post" ? "FT" : (stState === "in" ? "LIVE" : "NS"),
    home: hName, away: aName, hScore, aScore, hForm, aForm, lamH: lamH.toFixed(2), lamA: lamA.toFixed(2),
    pick: best.name, prob: Math.round(best.prob * 100), odd: +best.odd.toFixed(2),
    tipsterScore: best.prob * (best.odd >= 1.4 ? 1.15 : 1.0),
    expCorners: +(9.2 + (lamH + lamA - 2.3) * 0.9).toFixed(1),
    expCards: +(4.2 + (0.35 - Math.abs(pH - pA)) * 1.6).toFixed(1),
    probs: { p1: Math.round(pH*100), pX: Math.round(pD*100), p2: Math.round(pA*100), o25: Math.round(pO25*100), gg: Math.round(pGG*100), o15: Math.round(pO15*100) }
  };
}

async function loadMatchesForDate(iso) {
  if (cacheByDate[iso]) { renderViewport(); return; }
  document.getElementById("viewport").innerHTML = `<div class="cyber-card" style="text-align:center;padding:28px;color:var(--neon-cyan);">⚡ Scanare meciuri <b>${iso}</b>...</div>`;
  const ymd = iso.replace(/-/g, "");
  const res = await Promise.all(LEAGUES.filter(l => l.cat === "nat").map(l =>
    fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${l.slug}/scoreboard?dates=${ymd}`)
      .then(r => r.json()).then(d => ({ l, evs: (d && d.events) || [] })).catch(() => ({ l, evs: [] }))
  ));
  const list = [];
  res.forEach(r => r.evs.forEach(ev => { const m = analyzeMatch(ev, r.l); if (m.date === iso) list.push(m); }));
  cacheByDate[iso] = list;
  autoSettleProjectBets(list);
  renderViewport();
}

async function loadEuropaMatches() {
  if (europaMatches.length) { renderViewport(); return; }
  document.getElementById("viewport").innerHTML = `<div class="cyber-card" style="text-align:center;padding:28px;color:var(--neon-gold);">🏆 Se încarcă UEFA...</div>`;
  const now = new Date(), s = roDateStr(new Date(now.getTime() - 2*86400000)).replace(/-/g, ""), e = roDateStr(new Date(now.getTime() + 18*86400000)).replace(/-/g, "");
  const res = await Promise.all(LEAGUES.filter(l => l.cat === "eu").map(l =>
    fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${l.slug}/scoreboard?dates=${s}-${e}`)
      .then(r => r.json()).then(d => ({ l, evs: (d && d.events) || [] })).catch(() => ({ l, evs: [] }))
  ));
  const list = [];
  res.forEach(r => r.evs.forEach(ev => list.push(analyzeMatch(ev, r.l))));
  list.sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
  europaMatches = list;
  renderViewport();
}

async function initProject() {
  try {
    const r = await fetch("/api/project");
    if (r.ok) {
      const srv = await r.json();
      if (srv && srv.bankroll !== undefined) project = srv;
    }
  } catch (e) { console.error(e); }
  recalcBankroll(false);
  renderViewport();
}

async function saveToDB() {
  try {
    const r = await fetch("/api/project", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(project) });
    document.getElementById("liveClock").innerText = r.ok ? "● DB Synced" : "● Eroare DB";
  } catch (e) {
    document.getElementById("liveClock").innerText = "● Eroare DB";
  }
}

function recalcBankroll(shouldSave = true) {
  let b = project.initial_bankroll || 500.0;
  (project.bets || []).forEach(bet => {
    if (bet.status === "WIN") b += bet.stake * (bet.odd - 1);
    else if (bet.status === "LOSS") b -= bet.stake;
  });
  project.bankroll = +b.toFixed(2);
  document.getElementById("topBankroll").innerText = project.bankroll.toFixed(2);
  if (shouldSave) saveToDB();
}

function checkBetOutcome(pick, h, a) {
  const t = h + a;
  if (pick.startsWith("1 (")) return h > a;
  if (pick.startsWith("2 (")) return a > h;
  if (pick.includes("Peste 2.5")) return t > 2.5;
  if (pick.includes("Peste 1.5")) return t > 1.5;
  if (pick.includes("GG")) return h > 0 && a > 0;
  if (pick.includes("1X")) return h >= a;
  if (pick.includes("X2")) return a >= h;
  return null;
}

function autoSettleProjectBets(list) {
  let ch = false;
  (project.bets || []).forEach(b => {
    if (b.status !== "PENDING") return;
    const f = list.find(m => String(m.id) === String(b.matchId) && m.status === "FT");
    if (f && f.hScore !== null) {
      const w = checkBetOutcome(b.pick, f.hScore, f.aScore);
      if (w !== null) { b.status = w ? "WIN" : "LOSS"; b.score = `${f.hScore}-${f.aScore}`; ch = true; }
    }
  });
  if (ch) recalcBankroll(true);
}

function addMatchToProject(matchId) {
  const all = [...(cacheByDate[selectedDate] || []), ...europaMatches];
  const m = all.find(x => String(x.id) === String(matchId));
  if (!m) return;
  if (!project.bets.some(b => String(b.matchId) === String(m.id))) {
    const stake = Math.max(15, Math.round((project.bankroll * 0.07) / 5) * 5);
    project.bets.unshift({ id: Date.now(), matchId: m.id, date: m.date, match: `${m.home} vs ${m.away}`, league: m.league, pick: m.pick, odd: m.odd, stake, status: "PENDING", score: "" });
    recalcBankroll(true);
  }
  switchNav("proiect");
}

function editBetDetails(id) {
  const b = project.bets.find(x => x.id === id);
  if (!b) return;
  const o = parseFloat(prompt(`Cotă nouă pentru ${b.match}:`, b.odd));
  if (isNaN(o) || o <= 1.01) return;
  const s = parseFloat(prompt("Miză nouă (RON):", b.stake));
  if (isNaN(s) || s <= 0) return;
  b.odd = +o.toFixed(2); b.stake = +s.toFixed(2);
  recalcBankroll(true); renderViewport();
}

function updateBetStatus(id, st) {
  const b = project.bets.find(x => x.id === id);
  if (b) { b.status = st; recalcBankroll(true); renderViewport(); }
}

function deleteBet(id) {
  if (!confirm("Ștergi acest pariu?")) return;
  project.bets = project.bets.filter(x => x.id !== id);
  recalcBankroll(true); renderViewport();
}

function toggleDrawer(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = el.style.display === "block" ? "none" : "block";
}

function renderSubBars() {
  const sb = document.getElementById("subBars");
  if (currentNav === "proiect") { sb.style.display = "none"; return; }
  sb.style.display = "block";
  const dates = getDatesList();
  if (!selectedDate) selectedDate = dates[1].iso;
  const dBar = document.getElementById("dateBar"), lBar = document.getElementById("leagueBar");
  if (currentNav === "europa") {
    dBar.innerHTML = `<span style="font-size:11px;color:var(--neon-gold);font-weight:800;font-family:'Orbitron',sans-serif;">🏆 SECTOR UEFA EUROPEAN</span>`;
    lBar.innerHTML = ""; return;
  }
  dBar.innerHTML = dates.map(d => `<button class="cyber-chip ${selectedDate===d.iso?'active':''}" onclick="selectDay('${d.iso}')">${d.label}</button>`).join("");
  const dayList = cacheByDate[selectedDate] || [], lgs = [...new Set(dayList.map(m => m.league))];
  lBar.innerHTML = `<button class="cyber-chip cyber-chip-gold ${selectedLeague==='ALL'?'active':''}" onclick="selectLeague('ALL')">Toate (${dayList.length})</button>` +
    lgs.map(lg => `<button class="cyber-chip cyber-chip-gold ${selectedLeague===lg?'active':''}" onclick="selectLeague('${lg}')">${lg} (${dayList.filter(m=>m.league===lg).length})</button>`).join("");
}

function renderMatchCard(m) {
  const stClass = m.status === "FT" ? "st-ft" : (m.status === "LIVE" ? "st-live" : "st-ns");
  const stText = m.status === "FT" ? `FT (${m.hScore}-${m.aScore})` : (m.status === "LIVE" ? `LIVE ${m.hScore}-${m.aScore}` : `🕒 ${m.time}`);
  const center = (m.status === "FT" || m.status === "LIVE") ? `${m.hScore} - ${m.aScore}` : "VS";
  return `<div class="cyber-card">
    <div class="card-top"><span>${m.icon} ${m.league} · ${m.date}</span><span class="status-badge ${stClass}">${stText}</span></div>
    <div class="teams-container"><div class="team-name">${m.home}</div><div class="score-display">${center}</div><div class="team-name away">${m.away}</div></div>
    <div class="prediction-panel"><div><div class="pred-main">⭐ ${m.pick}</div><div class="pred-sub">Siguranță: <b style="color:var(--neon-green);">${m.prob}%</b> · xG: ${m.lamH}-${m.lamA}</div></div><div class="odd-chip">@${m.odd.toFixed(2)}</div></div>
    <div class="action-bar"><button class="cyber-btn" onclick="toggleDrawer('dr-${m.id}')">📊 Matrice Analiză</button><button class="cyber-btn accent" onclick="addMatchToProject('${m.id}')">➕ Adaugă la Jack</button></div>
    <div class="analytics-drawer" id="dr-${m.id}">
      <div class="matrix-grid">
        <div class="matrix-cell">1<b>${m.probs.p1}%</b></div><div class="matrix-cell">X<b>${m.probs.pX}%</b></div><div class="matrix-cell">2<b>${m.probs.p2}%</b></div>
        <div class="matrix-cell">Peste 1.5<b>${m.probs.o15}%</b></div><div class="matrix-cell">Peste 2.5<b>${m.probs.o25}%</b></div><div class="matrix-cell">GG<b>${m.probs.gg}%</b></div>
      </div>
      <div>📈 Formă: <b>${m.hForm}</b> vs <b>${m.aForm}</b> | 🟨 ~${m.expCards} | 🚩 ~${m.expCorners}</div>
    </div>
  </div>`;
}

function renderProjectView() {
  const net = +(project.bankroll - project.initial_bankroll).toFixed(2);
  const roi = +((net / project.initial_bankroll) * 100).toFixed(1);
  const settled = project.bets.filter(b => b.status === "WIN" || b.status === "LOSS");
  const wins = project.bets.filter(b => b.status === "WIN").length;
  const wr = settled.length ? Math.round((wins / settled.length) * 100) : 0;
  const prog = Math.max(5, Math.min(100, Math.round(((project.bankroll - 500) / (project.target_bankroll - 500)) * 100)));
  const betsHtml = project.bets.map(b => {
    const pot = +(b.stake * b.odd).toFixed(2);
    const col = b.status === "WIN" ? "var(--neon-green)" : (b.status === "LOSS" ? "var(--neon-red)" : "var(--neon-gold)");
    const lbl = b.status === "WIN" ? `✔ WIN (+${(pot-b.stake).toFixed(2)})` : (b.status === "LOSS" ? `✖ LOSS (-${b.stake})` : `⏳ PENDING (${pot})`);
    return `<div class="bet-ticket">
      <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);font-family:'Orbitron',sans-serif;"><span>${b.date} · ${b.league}</span><span style="font-weight:800;color:${col};">${lbl}</span></div>
      <div style="font-size:14px;font-weight:800;margin:6px 0;">${b.match} ${b.score ? `(${b.score})` : ''}</div>
      <div style="font-size:12px;color:var(--neon-cyan);">Pronostic: <b>${b.pick}</b> | Cotă: <b style="color:var(--neon-gold);">@${b.odd.toFixed(2)}</b> | Miză: <b>${b.stake} RON</b></div>
      <div class="bet-ticket-actions">
        <button class="t-btn t-edit" onclick="editBetDetails(${b.id})">✏️ Cotă</button>
        <button class="t-btn t-win" onclick="updateBetStatus(${b.id},'WIN')">✔ Win</button>
        <button class="t-btn t-loss" onclick="updateBetStatus(${b.id},'LOSS')">✖ Loss</button>
        <button class="t-btn" onclick="deleteBet(${b.id})">🗑️ Șterge</button>
      </div>
    </div>`;
  }).join("");
  return `<div class="vault-hero">
    <div class="vault-profile"><div class="vault-avatar">👴</div><div><div style="font-family:'Orbitron',sans-serif;font-size:15px;font-weight:900;">Nea Jack HUD</div><div style="font-size:9px;color:var(--neon-cyan);font-family:'Orbitron',sans-serif;">POSTGRESQL VAULT</div></div></div>
    <div class="vault-quote">" Matematica nu minte niciodată. Respectăm banca și mergem la țintă! "</div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;padding-top:12px;border-top:1px solid var(--card-border);">
      <div><div class="v-lbl">Capital Activ (DB)</div><div style="font-family:'Orbitron',sans-serif;font-size:24px;font-weight:900;">${project.bankroll.toFixed(2)} <span style="font-size:13px;color:var(--neon-green);">RON</span></div></div>
      <div style="text-align:right;"><div class="v-lbl">Țintă</div><div style="font-family:'Orbitron',sans-serif;font-size:14px;font-weight:900;color:var(--neon-gold);">${project.target_bankroll} RON</div></div>
    </div>
    <div class="cyber-progress"><div class="cyber-progress-fill" style="width:${prog}%;"></div></div>
    <div class="vault-kpi-grid">
      <div class="vault-kpi"><div class="v-lbl">Profit Net</div><div class="v-val" style="color:${net>=0?'var(--neon-green)':'var(--neon-red)'};">${net>=0?'+':''}${net}</div></div>
      <div class="vault-kpi"><div class="v-lbl">ROI</div><div class="v-val" style="color:var(--neon-cyan);">${roi>=0?'+':''}${roi}%</div></div>
      <div class="vault-kpi"><div class="v-lbl">Win Rate</div><div class="v-val" style="color:var(--neon-gold);">${wr}%</div></div>
    </div>
  </div>
  <div class="cyber-sec-head"><span>📋 PORTOFOLIU DB (${project.bets.length})</span><span>POSTGRESQL</span></div>
  ${betsHtml || '<div class="cyber-card" style="text-align:center;color:var(--text-muted);padding:24px;">Portofoliu gol. Adaugă meciuri!</div>'}`;
}

function renderTicketsView() {
  const sorted = [...(cacheByDate[selectedDate] || []).filter(m => m.status === "NS")].sort((a, b) => b.prob - a.prob);
  let picks = [], tot = 1.0;
  for (let m of sorted) { if (picks.length >= 10) break; if (tot < targetTicketOdds) { picks.push(m); tot *= m.odd; } }
  const btns = [2, 5, 10, 20, 50].map(o => `<button class="cyber-chip cyber-chip-gold ${targetTicketOdds===o?'active':''}" onclick="targetTicketOdds=${o};renderViewport();">Cotă ${o}</button>`).join("");
  const rows = picks.map((m, i) => `<div style="display:flex;justify-content:space-between;align-items:center;padding:10px;background:rgba(15,23,42,0.8);border-radius:10px;margin-bottom:6px;border:1px solid var(--card-border);"><div><div style="font-size:13px;font-weight:800;">${i+1}. ${m.home} vs ${m.away}</div><div style="font-size:11px;color:var(--neon-cyan);">👉 ${m.pick} (${m.prob}%)</div></div><div class="odd-chip">@${m.odd.toFixed(2)}</div></div>`).join("");
  return `<div class="cyber-card"><div style="font-family:'Orbitron',sans-serif;font-size:13px;font-weight:900;color:var(--neon-gold);margin-bottom:10px;">🎟️ Neural Ticket Builder (${selectedDate})</div><div class="h-scroll" style="margin-bottom:12px;">${btns}</div><div style="display:flex;justify-content:space-between;padding-bottom:8px;margin-bottom:10px;border-bottom:1px solid var(--card-border);font-family:'Orbitron',sans-serif;font-size:12px;"><span>Țintă: ~${targetTicketOdds}</span><span style="color:var(--neon-green);">Total: ${tot.toFixed(2)}</span></div>${rows || 'Nu sunt suficiente meciuri.'}</div>`;
}

function renderViewport() {
  renderSubBars();
  const vp = document.getElementById("viewport");
  if (currentNav === "proiect") { vp.innerHTML = renderProjectView(); return; }
  if (currentNav === "bilete") { vp.innerHTML = renderTicketsView(); return; }
  const list = currentNav === "europa" ? europaMatches : (cacheByDate[selectedDate] || []).filter(m => selectedLeague === "ALL" || m.league === selectedLeague);
  if (!list.length) { vp.innerHTML = `<div class="cyber-card" style="text-align:center;padding:26px;color:var(--text-muted);">Niciun meci programat în această zi.</div>`; return; }
  const groups = {};
  list.forEach(m => { if (!groups[m.league]) groups[m.league] = { icon: m.icon, items: [] }; groups[m.league].items.push(m); });
  vp.innerHTML = Object.keys(groups).map(lg => `<div class="cyber-sec-head"><span>${groups[lg].icon} ${lg}</span><span>${groups[lg].items.length} meciuri</span></div>${groups[lg].items.map(renderMatchCard).join("")}`).join("");
}

function selectDay(iso) { selectedDate = iso; selectedLeague = "ALL"; loadMatchesForDate(iso); }
function selectLeague(lg) { selectedLeague = lg; renderViewport(); }
function switchNav(tab) {
  currentNav = tab;
  document.querySelectorAll(".hud-nav-item").forEach(b => b.classList.remove("active"));
  document.getElementById("nav-" + tab).classList.add("active");
  if (tab === "europa") loadEuropaMatches(); else renderViewport();
}

(async function startApp() {
  selectedDate = getDatesList()[1].iso;
  await initProject();
  await loadMatchesForDate(selectedDate);
})();
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
