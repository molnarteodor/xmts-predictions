import os
import json
import psycopg2
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

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
  :root { --bg:#020408; --card-bg:rgba(10,15,28,0.78); --card-border:rgba(0,243,255,0.22); --neon-cyan:#00f3ff; --neon-gold:#ffb703; --neon-green:#06d6a0; --neon-red:#ef476f; --text-main:#f8fafc; --text-muted:#64748b; }
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
  .team-name { width:40%; font-size:14px; font-weight:800; line-height:1.3; user-select:text; }
  .team-name.away { text-align:right; }
  .score-display { background:rgba(15,23,42,0.9); border:1px solid var(--card-border); padding:6px 14px; border-radius:12px; font-family:'Orbitron',sans-serif; font-weight:900; font-size:13px; color:var(--neon-gold); }
  .prediction-panel { background:rgba(2,4,8,0.8); border:1px solid var(--card-border); border-radius:14px; padding:12px 14px; display:flex; justify-content:space-between; align-items:center; gap:10px; }
  .pred-main { font-size:12px; font-weight:800; color:#fff; user-select:text; }
  .pred-sub { font-size:10px; color:var(--text-muted); margin-top:3px; line-height:1.4; }
  .odd-chip { background:rgba(255,183,3,0.12); border:1px solid var(--neon-gold); color:var(--neon-gold); padding:5px 11px; border-radius:10px; font-family:'Orbitron',sans-serif; font-weight:800; font-size:12px; }
  .action-bar { display:flex; gap:6px; margin-top:10px; }
  .cyber-btn { flex:1; background:rgba(15,23,42,0.9); border:1px solid var(--card-border); color:var(--text-main); padding:9px 6px; border-radius:12px; font-size:11px; font-weight:700; cursor:pointer; }
  .cyber-btn.accent { background:rgba(6,214,160,0.15); border-color:rgba(6,214,160,0.5); color:var(--neon-green); }
  .cyber-btn.copy-btn { flex:0.45; background:rgba(0,243,255,0.1); border-color:rgba(0,243,255,0.4); color:var(--neon-cyan); }
  .analytics-drawer { display:none; margin-top:12px; padding-top:12px; border-top:1px dashed var(--card-border); font-size:11px; }
  .matrix-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:6px; margin-bottom:10px; }
  .matrix-cell { background:rgba(15,23,42,0.8); padding:8px; border-radius:10px; text-align:center; border:1px solid var(--card-border); }
  .matrix-cell b { display:block; color:var(--neon-gold); font-family:'Orbitron',sans-serif; font-size:12px; margin-top:3px; }
  .vault-hero { background:linear-gradient(135deg,#091526,#020408); border:1px solid rgba(0,243,255,0.4); border-radius:22px; padding:20px; margin-bottom:14px; }
  .vault-profile { display:flex; align-items:center; gap:14px; margin-bottom:14px; }
  .vault-avatar { width:60px; height:60px; border-radius:50%; border:2.5px solid var(--neon-cyan); background:#020408; display:flex; align-items:center; justify-content:center; font-size:28px; flex-shrink:0; box-shadow:0 0 16px rgba(0,243,255,0.35); }
  .vault-quote { font-style:italic; font-size:11px; color:var(--neon-cyan); background:rgba(0,243,255,0.06); padding:9px 13px; border-radius:12px; border-left:2.5px solid var(--neon-cyan); }
  .vault-kpi-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:14px; }
  .vault-kpi { background:rgba(2,4,8,0.6); border:1px solid var(--card-border); border-radius:12px; padding:10px; text-align:center; }
  .v-lbl { font-size:9px; color:var(--text-muted); text-transform:uppercase; font-family:'Orbitron',sans-serif; }
  .v-val { font-size:13px; font-family:'Orbitron',sans-serif; font-weight:900; margin-top:4px; }
  .cyber-progress { width:100%; height:10px; background:rgba(255,255,255,0.04); border-radius:99px; margin-top:14px; overflow:hidden; border:1px solid var(--card-border); }
  .cyber-progress-fill { height:100%; background:linear-gradient(90deg,var(--neon-green),var(--neon-cyan)); border-radius:99px; transition:0.4s; }
  .jack-pick-card { background:linear-gradient(145deg,rgba(6,214,160,0.12),rgba(2,4,8,0.95)); border:1.5px solid var(--neon-green); border-radius:18px; padding:16px; margin-bottom:14px; box-shadow:0 0 25px rgba(6,214,160,0.15); }
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
  .toast-msg { position:fixed; top:76px; left:50%; transform:translateX(-50%); background:rgba(6,214,160,0.95); color:#020408; padding:8px 18px; border-radius:12px; font-family:'Orbitron',sans-serif; font-size:11px; font-weight:900; z-index:100; display:none; box-shadow:0 0 20px rgba(6,214,160,0.6); }
</style>
</head>
<body>
<div class="toast-msg" id="toastMsg">✅ COPIAT ÎN CLIPBOARD!</div>
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
  {slug:"eng.1",name:"Premier League",icon:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",cat:"nat",cBase:10.2,kBase:3.8},
  {slug:"esp.1",name:"La Liga",icon:"🇪🇸",cat:"nat",cBase:9.4,kBase:4.9},
  {slug:"ita.1",name:"Serie A",icon:"🇮🇹",cat:"nat",cBase:9.6,kBase:4.5},
  {slug:"ger.1",name:"Bundesliga",icon:"🇩🇪",cat:"nat",cBase:9.9,kBase:3.9},
  {slug:"fra.1",name:"Ligue 1",icon:"🇫🇷",cat:"nat",cBase:9.3,kBase:4.1},
  {slug:"rou.1",name:"SuperLiga României",icon:"🇷🇴",cat:"nat",cBase:8.8,kBase:4.8},
  {slug:"ned.1",name:"Eredivisie",icon:"🇳🇱",cat:"nat",cBase:10.4,kBase:3.4},
  {slug:"por.1",name:"Primeira Liga",icon:"🇵🇹",cat:"nat",cBase:9.7,kBase:4.7},
  {slug:"tur.1",name:"Süper Lig",icon:"🇹🇷",cat:"nat",cBase:9.5,kBase:5.1},
  {slug:"gre.1",name:"Super League Grecia",icon:"🇬🇷",cat:"nat",cBase:8.9,kBase:5.0},
  {slug:"uefa.champions",name:"UEFA Champions League",icon:"🏆",cat:"eu",cBase:9.8,kBase:4.2},
  {slug:"uefa.europa",name:"UEFA Europa League",icon:"🟠",cat:"eu",cBase:9.6,kBase:4.4},
  {slug:"uefa.europa.conf",name:"UEFA Conference League",icon:"🟢",cat:"eu",cBase:9.4,kBase:4.5}
];

const ELITE_TEAMS = [
  {k:"real madrid",b:0.45},{k:"barcelona",b:0.45},{k:"manchester city",b:0.45},{k:"bayern",b:0.45},
  {k:"liverpool",b:0.40},{k:"arsenal",b:0.40},{k:"inter",b:0.38},{k:"paris saint-germain",b:0.40},{k:"psg",b:0.40},
  {k:"leverkusen",b:0.34},{k:"dortmund",b:0.32},{k:"atletico",b:0.32},{k:"atlético",b:0.32},{k:"juventus",b:0.30},
  {k:"milan",b:0.30},{k:"napoli",b:0.32},{k:"sporting",b:0.32},{k:"benfica",b:0.30},{k:"porto",b:0.30},
  {k:"fcsb",b:0.25},{k:"cfr cluj",b:0.22},{k:"craiova",b:0.20},{k:"galatasaray",b:0.28},{k:"fenerbahce",b:0.28},{k:"fenerbahçe",b:0.28},
  {k:"ajax",b:0.26},{k:"psv",b:0.30},{k:"feyenoord",b:0.26},{k:"olympiacos",b:0.25},{k:"paok",b:0.24},{k:"panathinaikos",b:0.24}
];

let currentNav = "meciuri", selectedDate = "", selectedLeague = "ALL", cacheByDate = {}, europaMatches = [], targetTicketOdds = 5;
let project = { initial_bankroll: 500.0, target_bankroll: 800.0, bankroll: 500.0, bets: [] };

const roDateStr = d => d.toLocaleDateString("sv-SE", { timeZone: "Europe/Bucharest" });
const roTimeStr = d => d.toLocaleTimeString("ro-RO", { timeZone: "Europe/Bucharest", hour: "2-digit", minute: "2-digit" });

function copyText(txt) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(txt).catch(() => fallbackCopy(txt));
  } else {
    fallbackCopy(txt);
  }
  const t = document.getElementById("toastMsg");
  t.style.display = "block";
  setTimeout(() => { t.style.display = "none"; }, 1800);
}

function fallbackCopy(txt) {
  const ta = document.createElement("textarea");
  ta.value = txt; document.body.appendChild(ta); ta.select();
  document.execCommand("copy"); document.body.removeChild(ta);
}

function getEliteBoost(name) {
  const low = (name || "").toLowerCase();
  for (let e of ELITE_TEAMS) if (low.includes(e.k)) return e.b;
  return 0;
}

function extractTeamStrength(compObj, seed) {
  let score = 0, formDisplay = "";
  if (compObj.form && compObj.form.length >= 3) {
    formDisplay = compObj.form.toUpperCase().slice(-5);
    for (let ch of formDisplay) score += ch === "W" ? 0.08 : (ch === "D" ? 0.01 : (ch === "L" ? -0.07 : 0));
    return { score, formDisplay };
  }
  if (compObj.records && compObj.records.length > 0 && compObj.records[0].summary) {
    const parts = compObj.records[0].summary.split("-").map(x => parseInt(x, 10));
    if (parts.length === 3 && !isNaN(parts[0])) {
      const [w, d, l] = parts;
      const tot = w + d + l;
      if (tot > 0) {
        score = ((w * 3 + d) / (tot * 3) - 0.45) * 0.75;
        formDisplay = `${w}V-${d}E-${l}Î`;
        return { score, formDisplay };
      }
    }
  }
  const patterns = ["WWDWL", "WDWLD", "WWLWD", "DLWWD", "WLDWW", "LWDWL"];
  formDisplay = patterns[seed % patterns.length];
  for (let ch of formDisplay) score += ch === "W" ? 0.06 : (ch === "D" ? 0.01 : -0.05);
  return { score, formDisplay };
}

function getDatesList() {
  const list = [], now = new Date(), labels = {"-1":"Ieri","0":"Azi","1":"Mâine"};
  for (let i = -1; i <= 5; i++) {
    const d = new Date(now.getTime() + i * 86400000), iso = roDateStr(d), p = iso.split("-"), s = p[2] + "." + p[1];
    list.push({ iso, ymd: iso.replace(/-/g, ""), label: labels[String(i)] ? `${labels[String(i)]} (${s})` : s });
  }
  return list;
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

  let seed = 0;
  for (let i = 0; i < (hName + aName).length; i++) seed = (seed * 37 + (hName + aName).charCodeAt(i)) % 10000;

  const hInfo = extractTeamStrength(home, seed);
  const aInfo = extractTeamStrength(away, seed + 7);
  const hBoost = getEliteBoost(hName) + hInfo.score;
  const aBoost = getEliteBoost(aName) + aInfo.score;

  const micro = ((seed % 28) - 14) / 100;
  const lamH = Math.max(0.65, Math.min(3.15, 1.42 + hBoost - aBoost * 0.38 + micro));
  const lamA = Math.max(0.48, Math.min(2.75, 1.08 + aBoost - hBoost * 0.38 - micro * 0.5));

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
    { name: `1 (${hName})`, prob: pH, odd: Math.max(1.22, Math.min(6.5, +(0.93 / pH).toFixed(2))), w: 1.08 }, { name: `2 (${aName})`, prob: pA, odd: Math.max(1.25, Math.min(7.5, +(0.93 / pA).toFixed(2))), w: 1.07 },
    { name: "Peste 2.5 Goluri", prob: pO25, odd: Math.max(1.40, Math.min(2.45, +(0.93 / pO25).toFixed(2))), w: 1.06 },
    { name: "GG (Ambele marchează)", prob: pGG, odd: Math.max(1.45, Math.min(2.40, +(0.93 / pGG).toFixed(2))), w: 1.05 },
    { name: "Peste 1.5 Goluri", prob: pO15, odd: Math.max(1.20, Math.min(1.75, +(0.92 / pO15).toFixed(2))), w: 0.96 },
    { name: "Șansă Dublă 1X", prob: p1X, odd: Math.max(1.16, Math.min(1.90, +(0.91 / p1X).toFixed(2))), w: 0.94 },
    { name: "Șansă Dublă X2", prob: pX2, odd: Math.max(1.18, Math.min(1.98, +(0.91 / pX2).toFixed(2))), w: 0.94 }
  ];

  // Scor de valoare: favorizează cotele optime 1.38 - 1.95 cu probabilitate ridicată
  candidates.forEach(c => {
    const sweetSpot = (c.odd >= 1.38 && c.odd <= 1.95) ? 1.12 : ((c.odd >= 1.30 && c.odd <= 2.15) ? 1.0 : 0.75);
    c.valueScore = c.prob * c.w * sweetSpot;
  });

  let valid = candidates.filter(c => c.odd >= 1.32 && c.odd <= 2.15 && c.prob >= 0.52);
  if (!valid.length) valid = candidates.filter(c => c.odd >= 1.28 && c.odd <= 2.30);
  if (!valid.length) valid = candidates;
  valid.sort((a, b) => b.valueScore - a.valueScore);
  const best = valid[0];

  // Calcul realist pe baza profilului ligii, intensității ofensive (lamH+lamA) și echilibrului
  const cSpread = ((seed % 29) - 14) / 10;
  const kSpread = (((seed >> 3) % 23) - 11) / 10;
  const expCorners = Math.max(6.5, Math.min(13.5, +((lg.cBase || 9.5) + (lamH + lamA - 2.45) * 1.6 + cSpread).toFixed(1)));
  const balanceFactor = (0.45 - Math.abs(pH - pA)) * 2.2;
  const expCards = Math.max(2.5, Math.min(7.5, +((lg.kBase || 4.3) + balanceFactor + kSpread).toFixed(1)));

  return {
    id: ev.id, league: lg.name, icon: lg.icon, cat: lg.cat, date: roDateStr(dt), time: roTimeStr(dt),
    status: stState === "post" ? "FT" : (stState === "in" ? "LIVE" : "NS"),
    home: hName, away: aName, hScore, aScore, hForm: hInfo.formDisplay, aForm: aInfo.formDisplay,
    lamH: lamH.toFixed(2), lamA: lamA.toFixed(2),
    pick: best.name, prob: Math.round(best.prob * 100), odd: +best.odd.toFixed(2),
    tipsterScore: best.valueScore,
    expCorners, expCards,
    probs: { p1: Math.round(pH*100), pX: Math.round(pD*100), p2: Math.round(pA*100), o25: Math.round(pO25*100), gg: Math.round(pGG*100), o15: Math.round(pO15*100) }
  };
}

async function loadMatchesForDate(iso) {
  if (cacheByDate[iso]) { renderViewport(); return; }
  document.getElementById("viewport").innerHTML = `<div class="cyber-card" style="text-align:center;padding:2
