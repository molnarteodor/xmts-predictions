import os
import json
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

PROJECT_FILE = "jack_500_state.json"

DEFAULT_PROJECT = {
    "initial_bankroll": 500.0,
    "target_bankroll": 800.0,
    "bankroll": 500.0,
    "bets": []
}

def load_project():
    try:
        if os.path.exists(PROJECT_FILE):
            with open(PROJECT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return dict(DEFAULT_PROJECT)

def save_project(data):
    try:
        with open(PROJECT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

@app.route("/api/project", methods=["GET", "POST"])
def api_project():
    if request.method == "POST":
        body = request.get_json(silent=True)
        if body and "bankroll" in body and "bets" in body:
            save_project(body)
            return jsonify(body)
    return jsonify(load_project())

HTML_PAGE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>JACK 500 · Cyber HUD</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #030508;
    --surface: rgba(13, 18, 30, 0.75);
    --surface2: rgba(22, 30, 48, 0.85);
    --border: rgba(6, 182, 212, 0.18);
    --border-glow: rgba(6, 182, 212, 0.45);
    --gold: #f59e0b;
    --gold-glow: rgba(245, 158, 11, 0.35);
    --cyan: #06b6d4;
    --cyan-glow: rgba(6, 182, 212, 0.35);
    --green: #10b981;
    --red: #ef4444;
    --text: #f1f5f9;
    --muted: #64748b;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; -webkit-tap-highlight-color: transparent; }
  html, body { height: 100%; width: 100%; background: var(--bg); color: var(--text); overflow: hidden; }
  
  /* Cyber Background Grid Effect */
  body::before {
    content: ""; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background-image: linear-gradient(rgba(6,182,212,0.03) 1px, transparent 1px),
                      linear-gradient(90deg, rgba(6,182,212,0.03) 1px, transparent 1px);
    background-size: 24px 24px; z-index: -1; pointer-events: none;
  }

  .app-shell { display: flex; flex-direction: column; height: 100dvh; max-width: 520px; margin: 0 auto; background: var(--bg); position: relative; }

  /* TOP HUD BAR */
  .top-bar {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; background: rgba(3, 5, 8, 0.88);
    backdrop-filter: blur(16px); border-bottom: 1px solid var(--border); z-index: 20;
  }
  .brand { display: flex; align-items: center; gap: 10px; }
  .brand-logo {
    width: 36px; height: 36px; border-radius: 10px;
    background: linear-gradient(135deg, var(--cyan), var(--gold));
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; color: #000; font-size: 16px; box-shadow: 0 0 14px var(--cyan-glow);
  }
  .brand-title { font-size: 15px; font-weight: 800; letter-spacing: 0.5px; background: linear-gradient(90deg, #fff, var(--cyan)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .brand-sub { font-size: 10px; color: var(--green); font-weight: 700; display: block; text-shadow: 0 0 8px rgba(16,185,129,0.4); }
  
  .bank-pill {
    background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.4);
    color: #34d399; padding: 7px 13px; border-radius: 12px; font-size: 13px; font-weight: 800;
    cursor: pointer; display: flex; align-items: center; gap: 6px; box-shadow: 0 0 12px rgba(16,185,129,0.2);
    transition: 0.2s;
  }
  .bank-pill:active { transform: scale(0.96); }

  /* SUB-BARS */
  .sub-bars { background: rgba(13, 18, 30, 0.6); border-bottom: 1px solid var(--border); padding: 8px 12px 6px; backdrop-filter: blur(8px); }
  .h-scroll { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; padding-bottom: 4px; }
  .h-scroll::-webkit-scrollbar { display: none; }
  .chip {
    background: var(--surface2); border: 1px solid var(--border); color: var(--muted);
    padding: 6px 12px; border-radius: 10px; font-size: 11px; font-weight: 700;
    white-space: nowrap; cursor: pointer; transition: 0.2s;
  }
  .chip.active { background: var(--cyan); color: #000; border-color: var(--cyan); font-weight: 800; box-shadow: 0 0 10px var(--cyan-glow); }
  .chip-gold.active { background: var(--gold); color: #000; border-color: var(--gold); box-shadow: 0 0 10px var(--gold-glow); }

  /* SCROLL VIEWPORT */
  .viewport { flex: 1; overflow-y: auto; padding: 12px; padding-bottom: 88px; -webkit-overflow-scrolling: touch; }

  .sec-head {
    display: flex; justify-content: space-between; align-items: center;
    background: linear-gradient(90deg, rgba(6,182,212,0.12), rgba(13,18,30,0.8));
    border-left: 3px solid var(--cyan); border-radius: 10px;
    padding: 8px 12px; margin: 12px 0 8px; font-size: 12px; font-weight: 800;
  }

  /* GLASS CARD */
  .card {
    background: var(--surface); border: 1px solid var(--border);
    backdrop-filter: blur(12px); border-radius: 16px; padding: 14px; margin-bottom: 10px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5); transition: 0.2s;
  }
  .card:hover { border-color: var(--border-glow); }
  .card-top { display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--muted); margin-bottom: 8px; }
  .status-pill { padding: 2px 8px; border-radius: 6px; font-weight: 800; font-size: 10px; }
  .st-live { background: rgba(239,68,68,0.2); color: #f87171; border: 1px solid var(--red); box-shadow: 0 0 8px rgba(239,68,68,0.3); }
  .st-ft { background: rgba(16,185,129,0.18); color: #34d399; }
  .st-ns { background: var(--surface2); color: #cbd5e1; }

  .teams-row { display: flex; justify-content: space-between; align-items: center; margin: 6px 0 10px; }
  .team-box { width: 42%; font-size: 14px; font-weight: 800; line-height: 1.25; }
  .team-box.away { text-align: right; }
  .score-box {
    background: var(--surface2); border: 1px solid var(--border);
    padding: 5px 12px; border-radius: 10px; font-weight: 800; font-size: 13px; color: var(--gold);
    box-shadow: 0 0 8px var(--gold-glow);
  }

  .pick-box {
    background: rgba(3, 5, 8, 0.75); border: 1px solid var(--border);
    border-radius: 12px; padding: 10px 12px; display: flex; justify-content: space-between; align-items: center;
  }
  .pick-title { font-size: 12px; font-weight: 800; color: #fff; }
  .pick-sub { font-size: 10px; color: var(--muted); margin-top: 2px; }
  .odd-badge {
    background: rgba(245,158,11,0.15); border: 1px solid var(--gold); color: var(--gold);
    padding: 4px 9px; border-radius: 8px; font-weight: 800; font-size: 12px; box-shadow: 0 0 8px var(--gold-glow);
  }

  .card-actions { display: flex; gap: 6px; margin-top: 9px; }
  .btn-sm {
    flex: 1; background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    padding: 8px; border-radius: 10px; font-size: 11px; font-weight: 700; cursor: pointer; transition: 0.15s;
  }
  .btn-sm:active { transform: scale(0.97); }
  .btn-proj { background: rgba(16,185,129,0.15); border-color: rgba(16,185,129,0.45); color: #34d399; flex: 0.7; }

  .details-drawer { display: none; margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--border); font-size: 11px; }
  .prob-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 8px; }
  .prob-cell { background: var(--surface2); padding: 7px; border-radius: 8px; text-align: center; border: 1px solid var(--border); }
  .prob-cell b { display: block; color: var(--gold); font-size: 13px; margin-top: 2px; }

  /* CYBER JACK HERO DASHBOARD */
  .hero-card {
    background: linear-gradient(145deg, #0d1424, #070a12);
    border: 1px solid var(--border-glow); border-radius: 20px; padding: 18px; margin-bottom: 14px;
    position: relative; overflow: hidden; box-shadow: 0 0 30px rgba(6,182,212,0.12);
  }
  .jack-profile { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; position: relative; z-index: 2; }
  .jack-avatar {
    width: 62px; height: 62px; border-radius: 50%; border: 2.5px solid var(--cyan);
    background: #12151e url('/jack_avatar.png') center/cover no-repeat;
    display: flex; align-items: center; justify-content: center; font-size: 26px;
    box-shadow: 0 0 18px var(--cyan-glow); flex-shrink: 0;
  }
  .jack-quote { font-style: italic; font-size: 11px; color: var(--cyan); background: rgba(6,182,212,0.08); padding: 8px 12px; border-radius: 10px; border-left: 2.5px solid var(--cyan); margin-top: 4px; line-height: 1.4; }

  .kpi-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 14px; }
  .kpi-box { background: rgba(0,0,0,0.45); border: 1px solid var(--border); border-radius: 12px; padding: 10px; text-align: center; }
  .kpi-lbl { font-size: 10px; color: var(--muted); }
  .kpi-val { font-size: 14px; font-weight: 800; margin-top: 3px; text-shadow: 0 0 8px rgba(255,255,255,0.2); }
  .prog-track { width: 100%; height: 10px; background: rgba(255,255,255,0.06); border-radius: 99px; margin-top: 12px; overflow: hidden; border: 1px solid var(--border); }
  .prog-fill { height: 100%; background: linear-gradient(90deg, var(--green), var(--cyan)); border-radius: 99px; box-shadow: 0 0 12px var(--cyan-glow); transition: 0.4s; }

  .bet-item {
    background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
    padding: 12px; margin-bottom: 8px; backdrop-filter: blur(10px);
  }
  .bet-actions { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
  .b-btn { flex: 1; padding: 7px; border-radius: 8px; border: 1px solid var(--border); font-size: 11px; font-weight: 800; cursor: pointer; background: var(--surface2); color: #fff; min-width: 65px; transition: 0.15s; }
  .b-btn:active { transform: scale(0.96); }
  .b-win { background: rgba(16,185,129,0.2); border-color: var(--green); color: #34d399; }
  .b-loss { background: rgba(239,68,68,0.2); border-color: var(--red); color: #f87171; }
  .b-edit { background: rgba(6,182,212,0.18); border-color: var(--cyan); color: #38bdf8; }

  /* BOTTOM HUD NAV */
  .bottom-nav {
    position: fixed; bottom: 0; left: 50%; transform: translateX(-50%);
    width: 100%; max-width: 520px; height: 70px;
    background: rgba(3, 5, 8, 0.94); backdrop-filter: blur(18px);
    border-top: 1px solid var(--border); display: flex; justify-content: space-around; align-items: center;
    padding-bottom: env(safe-area-inset-bottom); z-index: 30;
  }
  .nav-item {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    color: var(--muted); font-size: 10px; font-weight: 700; gap: 4px; cursor: pointer;
    background: none; border: none; width: 25%; height: 100%; transition: 0.2s;
  }
  .nav-item .ico { font-size: 18px; filter: drop-shadow(0 0 2px rgba(0,0,0,0.5)); }
  .nav-item.active { color: var(--cyan); text-shadow: 0 0 10px var(--cyan-glow); }
  .nav-item.active .ico { transform: translateY(-2px); }
</style>
</head>
<body>
<div class="app-shell">
  <div class="top-bar">
    <div class="brand">
      <div class="brand-logo">J</div>
      <div>
        <span class="brand-title">JACK 500 HUD</span>
        <span class="brand-sub" id="liveClock">● Neural Engine Active</span>
      </div>
    </div>
    <div class="bank-pill" onclick="switchNav('proiect')">
      💰 <span id="topBankroll">500.00</span> RON
    </div>
  </div>

  <div class="sub-bars" id="subBars">
    <div class="h-scroll" id="dateBar"></div>
    <div class="h-scroll" id="leagueBar" style="margin-top:6px;"></div>
  </div>

  <div class="viewport" id="viewport"></div>

  <nav class="bottom-nav">
    <button class="nav-item active" id="nav-meciuri" onclick="switchNav('meciuri')">
      <span class="ico">⚽</span><span>Meciuri</span>
    </button>
    <button class="nav-item" id="nav-europa" onclick="switchNav('europa')">
      <span class="ico">🏆</span><span>Europa</span>
    </button>
    <button class="nav-item" id="nav-proiect" onclick="switchNav('proiect')">
      <span class="ico">🧠</span><span>Jack 500</span>
    </button>
    <button class="nav-item" id="nav-bilete" onclick="switchNav('bilete')">
      <span class="ico">🎟️</span><span>Bilete</span>
    </button>
  </nav>
</div>

<script>
const LEAGUES = [
  {slug: "eng.1", name: "Premier League", icon: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", cat: "nat"},
  {slug: "esp.1", name: "La Liga", icon: "🇪🇸", cat: "nat"},
  {slug: "ita.1", name: "Serie A", icon: "🇮🇹", cat: "nat"},
  {slug: "ger.1", name: "Bundesliga", icon: "🇩🇪", cat: "nat"},
  {slug: "fra.1", name: "Ligue 1", icon: "🇫🇷", cat: "nat"},
  {slug: "rou.1", name: "SuperLiga României", icon: "🇷🇴", cat: "nat"},
  {slug: "ned.1", name: "Eredivisie", icon: "🇳🇱", cat: "nat"},
  {slug: "por.1", name: "Primeira Liga", icon: "🇵🇹", cat: "nat"},
  {slug: "tur.1", name: "Süper Lig", icon: "🇹🇷", cat: "nat"},
  {slug: "gre.1", name: "Super League Grecia", icon: "🇬🇷", cat: "nat"},
  {slug: "uefa.champions", name: "UEFA Champions League", icon: "🏆", cat: "eu"},
  {slug: "uefa.europa", name: "UEFA Europa League", icon: "🟠", cat: "eu"},
  {slug: "uefa.europa.conf", name: "UEFA Conference League", icon: "🟢", cat: "eu"}
];

const ELITE_BOOST = {
  "real madrid": 0.45, "barcelona": 0.45, "manchester city": 0.45, "bayern munich": 0.45,
  "liverpool": 0.40, "arsenal": 0.40, "inter": 0.36, "psg": 0.40, "paris saint-germain": 0.40,
  "bayer leverkusen": 0.34, "borussia dortmund": 0.32, "atletico madrid": 0.32, "juventus": 0.30,
  "ac milan": 0.30, "napoli": 0.32, "sporting cp": 0.30, "benfica": 0.28, "fc porto": 0.28,
  "fcsb": 0.24, "cfr cluj": 0.20, "universitatea craiova": 0.20, "galatasaray": 0.26, "fenerbahce": 0.26
};

let currentNav = "meciuri";
let selectedDate = "";
let selectedLeague = "ALL";
let cacheByDate = {};
let europaMatches = [];
let targetTicketOdds = 5;

let project = {
  initial_bankroll: 500.0,
  target_bankroll: 800.0,
  bankroll: 500.0,
  bets: []
};

function roDateStr(dateObj) {
  return dateObj.toLocaleDateString("sv-SE", { timeZone: "Europe/Bucharest" });
}

function roTimeStr(dateObj) {
  return dateObj.toLocaleTimeString("ro-RO", { timeZone: "Europe/Bucharest", hour: "2-digit", minute: "2-digit" });
}

function getDatesList() {
  const list = [];
  const now = new Date();
  const labels = {"-1": "Ieri", "0": "Azi", "1": "Mâine"};
  for (let i = -1; i <= 5; i++) {
    const d = new Date(now.getTime() + i * 86400000);
    const iso = roDateStr(d);
    const parts = iso.split("-");
    const shortD = parts[2] + "." + parts[1];
    const lbl = labels[String(i)] ? `${labels[String(i)]} (${shortD})` : shortD;
    list.push({ iso, ymd: iso.replace(/-/g, ""), label: lbl });
  }
  return list;
}

function formScore(formStr) {
  if (!formStr) return 0;
  let s = 0;
  for (let ch of formStr.toUpperCase().slice(-5)) {
    if (ch === "W") s += 0.08;
    else if (ch === "D") s += 0.01;
    else if (ch === "L") s -= 0.07;
  }
  return s;
}

function poissonPmf(k, lam) {
  let fact = 1;
  for (let i = 2; i <= k; i++) fact *= i;
  return Math.exp(-lam) * Math.pow(lam, k) / fact;
}

function analyzeMatch(ev, leagueObj) {
  const comp = ev.competitions[0];
  const competitors = comp.competitors;
  const home = competitors.find(c => c.homeAway === "home") || competitors[0];
  const away = competitors.find(c => c.homeAway === "away") || competitors[1];

  const hName = home.team.displayName || home.team.name;
  const aName = away.team.displayName || away.team.name;
  const dt = new Date(comp.date || ev.date);
  const matchDate = roDateStr(dt);
  const matchTime = roTimeStr(dt);

  const stState = (comp.status && comp.status.type && comp.status.type.state) || "pre";
  const isFT = stState === "post";
  const isLive = stState === "in";
  const hScore = home.score !== undefined ? parseInt(home.score, 10) : null;
  const aScore = away.score !== undefined ? parseInt(away.score, 10) : null;

  const hForm = home.form || "WWDWL";
  const aForm = away.form || "WDLWD";

  const hBoost = (ELITE_BOOST[hName.toLowerCase()] || 0) + formScore(hForm);
  const aBoost = (ELITE_BOOST[aName.toLowerCase()] || 0) + formScore(aForm);

  let seed = 0;
  const pair = hName + aName;
  for (let i = 0; i < pair.length; i++) seed = (seed * 31 + pair.charCodeAt(i)) % 1000;
  const micro = (seed % 20 - 10) / 100;

  const lamH = Math.max(0.65, Math.min(3.10, 1.40 + hBoost - aBoost * 0.35 + micro));
  const lamA = Math.max(0.50, Math.min(2.70, 1.05 + aBoost - hBoost * 0.35 - micro * 0.5));

  let pH = 0, pD = 0, pA = 0, pO15 = 0, pO25 = 0, pGG = 0;
  for (let h = 0; h <= 7; h++) {
    for (let a = 0; a <= 7; a++) {
      const p = poissonPmf(h, lamH) * poissonPmf(a, lamA);
      if (h > a) pH += p;
      else if (h === a) pD += p;
      else pA += p;
      if (h + a > 1.5) pO15 += p;
      if (h + a > 2.5) pO25 += p;
      if (h > 0 && a > 0) pGG += p;
    }
  }
  const tot = pH + pD + pA;
  pH /= tot; pD /= tot; pA /= tot;

  const p1X = pH + pD;
  const pX2 = pA + pD;

  const odd1 = Math.max(1.20, Math.min(6.50, +(0.94 / pH).toFixed(2)));
  const odd2 = Math.max(1.22, Math.min(7.50, +(0.94 / pA).toFixed(2)));
  const oddO25 = Math.max(1.42, Math.min(2.45, +(0.94 / pO25).toFixed(2)));
  const oddGG = Math.max(1.48, Math.min(2.40, +(0.94 / pGG).toFixed(2)));
  const oddO15 = Math.max(1.18, Math.min(1.65, +(0.94 / pO15).toFixed(2)));
  const odd1X = Math.max(1.15, Math.min(1.85, +(0.94 / p1X).toFixed(2)));
  const oddX2 = Math.max(1.16, Math.min(1.95, +(0.94 / pX2).toFixed(2)));

  const candidates = [
    { name: `1 (${hName})`, prob: pH, odd: odd1, type: "SOLIST" },
    { name: `2 (${aName})`, prob: pA, odd: odd2, type: "SOLIST" },
    { name: "Peste 1.5 Goluri", prob: pO15, odd: oddO15, type: "GOLURI" },
    { name: "Peste 2.5 Goluri", prob: pO25, odd: oddO25, type: "GOLURI" },
    { name: "GG (Ambele marchează)", prob: pGG, odd: oddGG, type: "GOLURI" },
    { name: "Șansă Dublă 1X", prob: p1X, odd: odd1X, type: "DUBLA" },
    { name: "Șansă Dublă X2", prob: pX2, odd: oddX2, type: "DUBLA" }
  ];

  let validPicks = candidates.filter(c => c.odd >= 1.30 && c.odd <= 2.20);
  if (!validPicks.length) validPicks = candidates;
  validPicks.sort((a, b) => b.prob - a.prob);

  const bestChoice = validPicks[0];
  const tipsterConfidence = +(bestChoice.prob * 100).toFixed(1);

  return {
    id: ev.id,
    league: leagueObj.name,
    icon: leagueObj.icon,
    cat: leagueObj.cat,
    date: matchDate,
    time: matchTime,
    status: isFT ? "FT" : (isLive ? "LIVE" : "NS"),
    home: hName,
    away: aName,
    hScore, aScore,
    hForm, aForm,
    lamH: lamH.toFixed(2),
    lamA: lamA.toFixed(2),
    pick: bestChoice.name,
    prob: Math.round(tipsterConfidence),
    rawProb: bestChoice.prob,
    odd: +bestChoice.odd.toFixed(2),
    tipsterScore: bestChoice.prob * (bestChoice.odd >= 1.40 ? 1.15 : 1.0),
    expCorners: +(9.2 + (lamH + lamA - 2.3) * 0.9).toFixed(1),
    expCards: +(4.2 + (0.35 - Math.abs(pH - pA)) * 1.6).toFixed(1),
    probs: {
      p1: Math.round(pH * 100),
      pX: Math.round(pD * 100),
      p2: Math.round(pA * 100),
      o25: Math.round(pO25 * 100),
      gg: Math.round(pGG * 100),
      o15: Math.round(pO15 * 100),
      p1X: Math.round(p1X * 100),
      pX2: Math.round(pX2 * 100)
    }
  };
}

async function loadMatchesForDate(isoDate) {
  if (cacheByDate[isoDate]) {
    renderViewport();
    return;
  }
  const vp = document.getElementById("viewport");
  vp.innerHTML = `<div class="card" style="text-align:center;padding:28px;">⚡ Neural HUD analizează meciurile pentru <b>${isoDate}</b>...</div>`;

  const ymd = isoDate.replace(/-/g, "");
  const natLeagues = LEAGUES.filter(l => l.cat === "nat");

  const requests = natLeagues.map(l =>
    fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${l.slug}/scoreboard?dates=${ymd}`)
      .then(r => r.json())
      .then(data => ({ league: l, events: (data && data.events) || [] }))
      .catch(() => ({ league: l, events: [] }))
  );

  const results = await Promise.all(requests);
  const list = [];
  results.forEach(res => {
    res.events.forEach(ev => {
      const m = analyzeMatch(ev, res.league);
      if (m.date === isoDate) list.push(m);
    });
  });

  cacheByDate[isoDate] = list;
  autoSettleProjectBets(list);
  renderViewport();
}

async function loadEuropaMatches() {
  if (europaMatches.length > 0) {
    renderViewport();
    return;
  }
  const vp = document.getElementById("viewport");
  vp.innerHTML = `<div class="card" style="text-align:center;padding:28px;">🏆 Se încarcă cuplul european UEFA...</div>`;

  const now = new Date();
  const start = roDateStr(new Date(now.getTime() - 2 * 86400000)).replace(/-/g, "");
  const end = roDateStr(new Date(now.getTime() + 18 * 86400000)).replace(/-/g, "");
  const euLeagues = LEAGUES.filter(l => l.cat === "eu");

  const requests = euLeagues.map(l =>
    fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${l.slug}/scoreboard?dates=${start}-${end}`)
      .then(r => r.json())
      .then(data => ({ league: l, events: (data && data.events) || [] }))
      .catch(() => ({ league: l, events: [] }))
  );

  const results = await Promise.all(requests);
  const list = [];
  results.forEach(res => {
    res.events.forEach(ev => list.push(analyzeMatch(ev, res.league)));
  });
  list.sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
  europaMatches = list;
  renderViewport();
}

/* ================= JACK 500 LOGIC ================= */
async function initProject() {
  const localRaw = localStorage.getItem("xmts_jack_500");
  let localData = null;
  if (localRaw) {
    try { localData = JSON.parse(localRaw); } catch(e) {}
  }
  try {
    const r = await fetch("/api/project");
    const srvData = await r.json();
    if (localData && (localData.bets || []).length >= (srvData.bets || []).length) {
      project = localData;
    } else if (srvData && srvData.bankroll !== undefined) {
      project = srvData;
    }
  } catch (e) {
    if (localData) project = localData;
  }
  recalcBankroll();
}

function recalcBankroll() {
  let b = project.initial_bankroll || 500.0;
  (project.bets || []).forEach(bet => {
    if (bet.status === "WIN") b += bet.stake * (bet.odd - 1);
    else if (bet.status === "LOSS") b -= bet.stake;
  });
  project.bankroll = +b.toFixed(2);
  document.getElementById("topBankroll").innerText = project.bankroll.toFixed(2);
  localStorage.setItem("xmts_jack_500", JSON.stringify(project));
  fetch("/api/project", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(project)
  }).catch(() => {});
}

function checkBetOutcome(pick, hScore, aScore, homeName, awayName) {
  const tot = hScore + aScore;
  if (pick.startsWith("1 (")) return hScore > aScore;
  if (pick.startsWith("2 (")) return aScore > hScore;
  if (pick.includes("Peste 2.5")) return tot > 2.5;
  if (pick.includes("Peste 1.5")) return tot > 1.5;
  if (pick.includes("Sub 2.5")) return tot < 2.5;
  if (pick.includes("GG")) return hScore > 0 && aScore > 0;
  if (pick.includes("1X")) return hScore >= aScore;
  if (pick.includes("X2")) return aScore >= hScore;
  return null;
}

function autoSettleProjectBets(matchesList) {
  let changed = false;
  (project.bets || []).forEach(bet => {
    if (bet.status !== "PENDING") return;
    const found = matchesList.find(m => m.id === bet.matchId && m.status === "FT");
    if (found && found.hScore !== null) {
      const won = checkBetOutcome(bet.pick, found.hScore, found.aScore, found.home, found.away);
      if (won !== null) {
        bet.status = won ? "WIN" : "LOSS";
        bet.score = `${found.hScore}-${found.aScore}`;
        changed = true;
      }
    }
  });
  if (changed) recalcBankroll();
}

function addMatchToProject(matchId, customOdd) {
  const all = [...(cacheByDate[selectedDate] || []), ...europaMatches];
  const m = all.find(x => String(x.id) === String(matchId));
  if (!m) return;

  if (project.bets.some(b => String(b.matchId) === String(m.id))) {
    switchNav("proiect");
    return;
  }

  const rawStake = Math.max(15, Math.round((project.bankroll * 0.07) / 5) * 5);
  const oddToUse = customOdd ? parseFloat(customOdd) : m.odd;

  project.bets.unshift({
    id: Date.now(),
    matchId: m.id,
    date: m.date,
    match: `${m.home} vs ${m.away}`,
    league: m.league,
    pick: m.pick,
    odd: oddToUse,
    stake: rawStake,
    status: "PENDING",
    score: ""
  });
  recalcBankroll();
  switchNav("proiect");
}

function editBetDetails(betId) {
  const b = project.bets.find(x => x.id === betId);
  if (!b) return;

  const newOddStr = prompt(`Introdu cota exactă din Superbet pentru:\n${b.match} - ${b.pick}`, b.odd);
  if (newOddStr === null) return;
  const newOdd = parseFloat(newOddStr);
  if (isNaN(newOdd) || newOdd <= 1.01) { alert("Cotă invalidă!"); return; }

  const newStakeStr = prompt(`Introdu miza (RON) pentru acest pariu:`, b.stake);
  if (newStakeStr === null) return;
  const newStake = parseFloat(newStakeStr);
  if (isNaN(newStake) || newStake <= 0) { alert("Miză invalidă!"); return; }

  b.odd = +newOdd.toFixed(2);
  b.stake = +newStake.toFixed(2);
  recalcBankroll();
  renderViewport();
}

function updateBetStatus(betId, newStatus) {
  const b = project.bets.find(x => x.id === betId);
  if (b) {
    b.status = newStatus;
    recalcBankroll();
    renderViewport();
  }
}

function deleteBet(betId) {
  if (!confirm("Sigur vrei să ștergi acest pariu?")) return;
  project.bets = project.bets.filter(x => x.id !== betId);
  recalcBankroll();
  renderViewport();
}

/* ================= RENDERING UI ================= */
function renderSubBars() {
  const sb = document.getElementById("subBars");
  if (currentNav === "proiect") {
    sb.style.display = "none";
    return;
  }
  sb.style.display = "block";
  const dates = getDatesList();
  if (!selectedDate) selectedDate = dates[1].iso;

  const dBar = document.getElementById("dateBar");
  const lBar = document.getElementById("leagueBar");

  if (currentNav === "europa") {
    dBar.innerHTML = `<span style="font-size:11px;color:var(--cyan);font-weight:800;">🏆 Program European UEFA</span>`;
    lBar.innerHTML = "";
    return;
  }

  dBar.innerHTML = dates.map(d =>
    `<button class="chip ${selectedDate === d.iso ? 'active' : ''}" onclick="selectDay('${d.iso}')">${d.label}</button>`
  ).join("");

  const dayList = cacheByDate[selectedDate] || [];
  const leaguesPresent = [...new Set(dayList.map(m => m.league))];
  let lHtml = `<button class="chip chip-gold ${selectedLeague === 'ALL' ? 'active' : ''}" onclick="selectLeague('ALL')">Toate (${dayList.length})</button>`;
  leaguesPresent.forEach(lg => {
    const cnt = dayList.filter(m => m.league === lg).length;
    lHtml += `<button class="chip chip-gold ${selectedLeague === lg ? 'active' : ''}" onclick="selectLeague('${lg}')">${lg} (${cnt})</button>`;
  });
  lBar.innerHTML = lHtml;
}

function renderMatchCard(m) {
  const stClass = m.status === "FT" ? "st-ft" : (m.status === "LIVE" ? "st-live" : "st-ns");
  const stText = m.status === "FT" ? `FINAL (${m.hScore}-${m.aScore})` : (m.status === "LIVE" ? `LIVE ${m.hScore}-${m.aScore}` : `🕒 ${m.time}`);
  const centerBox = (m.status === "FT" || m.status === "LIVE") ? `${m.hScore} - ${m.aScore}` : "VS";

  return `
    <div class="card">
      <div class="card-top">
        <span>${m.icon} ${m.league} · ${m.date}</span>
        <span class="status-pill ${stClass}">${stText}</span>
      </div>
      <div class="teams-row">
        <div class="team-box">${m.home}</div>
        <div class="score-box">${centerBox}</div>
        <div class="team-box away">${m.away}</div>
      </div>
      <div class="pick-box">
        <div>
          <div class="pick-title">⭐ ${m.pick}</div>
          <div class="pick-sub">Neural Score: <b style="color:var(--cyan);">${m.prob}%</b> · xG: ${m.lamH} - ${m.lamA}</div>
        </div>
        <div class="odd-badge">@${m.odd.toFixed(2)}</div>
      </div>
      <div class="card-actions">
        <button class="btn-sm" onclick="toggleDrawer('dr-${m.id}')">📊 Analiză Neurală</button>
        <button class="btn-sm btn-proj" onclick="addMatchToProject('${m.id}')">➕ Adaugă la Jack</button>
      </div>
      <div class="details-drawer" id="dr-${m.id}">
        <div class="prob-grid">
          <div class="prob-cell">1 (Gazde)<b>${m.probs.p1}%</b></div>
          <div class="prob-cell">X (Egal)<b>${m.probs.pX}%</b></div>
          <div class="prob-cell">2 (Oaspeți)<b>${m.probs.p2}%</b></div>
          <div class="prob-cell">Peste 1.5<b>${m.probs.o15}%</b></div>
          <div class="prob-cell">Peste 2.5<b>${m.probs.o25}%</b></div>
          <div class="prob-cell">Ambele (GG)<b>${m.probs.gg}%</b></div>
        </div>
        <div style="background:var(--surface2);padding:8px 10px;border-radius:8px;line-height:1.6;border:1px solid var(--border);">
          <div>📈 <b>Formă:</b> ${m.home} (<b style="color:var(--gold);">${m.hForm}</b>) vs ${m.away} (<b style="color:var(--cyan);">${m.aForm}</b>)</div>
          <div>🟨 <b>Cartonașe estimate:</b> ~${m.expCards} &nbsp;|&nbsp; 🚩 <b>Cornere:</b> ~${m.expCorners}</div>
        </div>
      </div>
    </div>
  `;
}

function toggleDrawer(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = el.style.display === "block" ? "none" : "block";
}

function renderProjectView() {
  const netProfit = +(project.bankroll - project.initial_bankroll).toFixed(2);
  const roiPct = +((netProfit / project.initial_bankroll) * 100).toFixed(1);
  const settled = project.bets.filter(b => b.status === "WIN" || b.status === "LOSS");
  const wins = project.bets.filter(b => b.status === "WIN").length;
  const winRate = settled.length ? Math.round((wins / settled.length) * 100) : 0;
  const progressPct = Math.max(5, Math.min(100, Math.round(((project.bankroll - 500) / (project.target_bankroll - 500)) * 100)));

  const todayMatches = (cacheByDate[selectedDate] || []).filter(m => m.status === "NS");
  todayMatches.sort((a, b) => b.tipsterScore - a.tipsterScore);
  const bestOfDay = todayMatches[0];
  const recStake = Math.max(15, Math.round((project.bankroll * 0.07) / 5) * 5);

  let bestHtml = "";
  if (bestOfDay) {
    const potWin = +(recStake * bestOfDay.odd).toFixed(2);
    bestHtml = `
      <div class="card" style="border-color:var(--cyan);background:linear-gradient(145deg, #091a24, #060a12);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <span style="font-size:11px;font-weight:800;color:var(--cyan);">💎 TOP VALUE BET RECOMANDAT DE NEA JACK</span>
          <span style="font-size:11px;color:var(--muted);">${bestOfDay.date} · ${bestOfDay.time}</span>
        </div>
        <div style="font-size:15px;font-weight:800;margin-bottom:6px;">${bestOfDay.home} vs ${bestOfDay.away}</div>
        <div class="pick-box">
          <div>
            <div class="pick-title">👉 ${bestOfDay.pick} (@${bestOfDay.odd.toFixed(2)})</div>
            <div class="pick-sub">Confidence: <b style="color:var(--green);">${bestOfDay.prob}%</b> · Miză (7%): <b style="color:#fff;">${recStake} RON</b> ➔ Câștig: <b style="color:var(--green);">${potWin} RON</b></div>
          </div>
          <button class="btn-sm btn-proj" style="flex:0.45;" onclick="addMatchToProject('${bestOfDay.id}')">➕ Adaugă</button>
        </div>
      </div>
    `;
  }

  const quotes = [
    "Sistemul nostru scanează piața în căutarea valorii absolute. Fără riscuri inutile!",
    "Matematica nu minte niciodată. Respectăm banca și mergem la țintă.",
    "Un portofoliu de succes se construiește zi de zi cu disciplină robotică.",
    "Nea Jack ține cont de fiecare cotă din Superbet. Executăm planul!"
  ];
  const seedQ = Math.abs(Math.round(project.bankroll + project.bets.length));
  const currentQuote = quotes[seedQ % quotes.length];

  const betsHtml = project.bets.map(b => {
    const pot = +(b.stake * b.odd).toFixed(2);
    const stColor = b.status === "WIN" ? "var(--green)" : (b.status === "LOSS" ? "var(--red)" : "var(--gold)");
    const stLabel = b.status === "WIN" ? `✔ CÂȘTIGAT (+${(pot - b.stake).toFixed(2)} RON)` : (b.status === "LOSS" ? `✖ PIERDUT (-${b.stake} RON)` : `⏳ ÎN AȘTEPTARE (Câștig: ${pot} RON)`);
    return `
      <div class="bet-item">
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted);">
          <span>${b.date} · ${b.league}</span>
          <span style="font-weight:800;color:${stColor};">${stLabel}</span>
        </div>
        <div style="font-size:14px;font-weight:800;margin:4px 0;">${b.match} ${b.score ? `(${b.score})` : ''}</div>
        <div style="font-size:12px;color:var(--cyan);font-weight:700;">
          Pronostic: <b>${b.pick}</b> &nbsp;|&nbsp; Cotă: <b style="color:var(--gold);">@${b.odd.toFixed(2)}</b> &nbsp;|&nbsp; Miză: <b>${b.stake} RON</b>
        </div>
        <div class="bet-actions">
          <button class="b-btn b-edit" onclick="editBetDetails(${b.id})">✏️ Editează Cotă</button>
          <button class="b-btn b-win" onclick="updateBetStatus(${b.id}, 'WIN')">✔ Câștigat</button>
          <button class="b-btn b-loss" onclick="updateBetStatus(${b.id}, 'LOSS')">✖ Pierdut</button>
          <button class="b-btn" onclick="deleteBet(${b.id})">🗑️ Șterge</button>
        </div>
      </div>
    `;
  }).join("");

  return `
    <div class="hero-card">
      <div class="jack-profile">
        <div class="jack-avatar">👴</div>
        <div>
          <div style="font-size:16px;font-weight:800;color:#fff;">Nea Jack Cyber HUD</div>
          <div style="font-size:10px;color:var(--cyan);font-weight:700;letter-spacing:1px;text-transform:uppercase;">Master AI Portfolio Manager</div>
        </div>
      </div>
      <div class="jack-quote">" ${currentQuote} "</div>
      
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;border-top:1px solid var(--border);padding-top:12px;">
        <div>
          <div style="font-size:11px;color:var(--muted);font-weight:700;">CAPITALUL LUI JACK</div>
          <div style="font-size:26px;font-weight:800;color:#fff;margin-top:2px;">${project.bankroll.toFixed(2)} <span style="font-size:14px;color:var(--green);">RON</span></div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:11px;color:var(--muted);">Ținta Finală</div>
          <div style="font-size:15px;font-weight:800;color:var(--gold);">${project.target_bankroll} RON</div>
        </div>
      </div>
      <div class="prog-track"><div class="prog-fill" style="width:${progressPct}%;"></div></div>
      
      <div class="kpi-grid">
        <div class="kpi-box">
          <div class="kpi-lbl">Profit Net</div>
          <div class="kpi-val" style="color:${netProfit >= 0 ? 'var(--green)' : 'var(--red)'};">${netProfit >= 0 ? '+' : ''}${netProfit} RON</div>
        </div>
        <div class="kpi-box">
          <div class="kpi-lbl">Randament ROI</div>
          <div class="kpi-val" style="color:var(--cyan);">${roiPct >= 0 ? '+' : ''}${roiPct}%</div>
        </div>
        <div class="kpi-box">
          <div class="kpi-lbl">Win Rate (${wins}/${settled.length})</div>
          <div class="kpi-val" style="color:var(--gold);">${winRate}%</div>
        </div>
      </div>
    </div>

    ${bestHtml}

    <div class="sec-head">
      <span>📋 Portofoliul Activ (${project.bets.length})</span>
      <span style="font-size:10px;color:var(--muted);">Live Synced</span>
    </div>
    ${betsHtml || '<div class="card" style="text-align:center;color:var(--muted);padding:20px;">Portofoliu gol. Adaugă selecții din secțiunea de meciuri!</div>'}
  `;
}

function renderTicketsView() {
  const dayMatches = (cacheByDate[selectedDate] || []).filter(m => m.status === "NS");
  const sorted = [...dayMatches].sort((a, b) => b.prob - a.prob);

  let picks = [], totalOdd = 1.0;
  for (let m of sorted) {
    if (picks.length >= 10) break;
    if (totalOdd < targetTicketOdds) {
      picks.push(m);
      totalOdd *= m.odd;
    }
  }

  const btns = [2, 5, 10, 20, 50].map(o =>
    `<button class="chip chip-gold ${targetTicketOdds === o ? 'active' : ''}" onclick="setTicketTarget(${o})">Cotă ${o}</button>`
  ).join("");

  const rows = picks.map((m, i) => `
    <div style="display:flex;justify-content:space-between;align-items:center;padding:10px;background:var(--surface2);border-radius:10px;margin-bottom:6px;border:1px solid var(--border);">
      <div>
        <div style="font-size:13px;font-weight:800;">${i + 1}. ${m.home} vs ${m.away}</div>
        <div style="font-size:11px;color:var(--cyan);">👉 ${m.pick} (${m.prob}%)</div>
      </div>
      <div class="odd-badge">@${m.odd.toFixed(2)}</div>
    </div>
  `).join("");

  return `
    <div class="card">
      <div style="font-size:15px;font-weight:800;color:var(--gold);margin-bottom:8px;">🎟️ Neural Ticket Builder (${selectedDate})</div>
      <div class="h-scroll" style="margin-bottom:12px;">${btns}</div>
      <div style="display:flex;justify-content:space-between;padding-bottom:8px;margin-bottom:10px;border-bottom:1px solid var(--border);font-size:13px;font-weight:800;">
        <span>Cotă Țintă: ~${targetTicketOdds}</span>
        <span style="color:var(--green);">Cotă Totală: ${totalOdd.toFixed(2)}</span>
      </div>
      ${rows || '<div style="text-align:center;color:var(--muted);padding:16px;">Nu sunt suficiente meciuri în această zi.</div>'}
    </div>
  `;
}

function setTicketTarget(val) {
  targetTicketOdds = val;
  renderViewport();
}

function renderViewport() {
  renderSubBars();
  const vp = document.getElementById("viewport");

  if (currentNav === "proiect") {
    vp.innerHTML = renderProjectView();
    return;
  }
  if (currentNav === "bilete") {
    vp.innerHTML = renderTicketsView();
    return;
  }

  const list = currentNav === "europa"
    ? europaMatches
    : (cacheByDate[selectedDate] || []).filter(m => selectedLeague === "ALL" || m.league === selectedLeague);

  if (!list.length) {
    vp.innerHTML = `<div class="card" style="text-align:center;padding:26px;color:var(--muted);">Niciun meci în această zi. Schimbă data din bara de sus!</div>`;
    return;
  }

  const groups = {};
  list.forEach(m => {
    if (!groups[m.league]) groups[m.league] = { icon: m.icon, items: [] };
    groups[m.league].items.push(m);
  });

  vp.innerHTML = Object.keys(groups).map(lg => `
    <div class="sec-head">
      <span>${groups[lg].icon} ${lg}</span>
      <span style="color:var(--cyan);">${groups[lg].items.length} meciuri</span>
    </div>
    ${groups[lg].items.map(renderMatchCard).join("")}
  `).join("");
}

function selectDay(iso) {
  selectedDate = iso;
  selectedLeague = "ALL";
  loadMatchesForDate(iso);
}

function selectLeague(lg) {
  selectedLeague = lg;
  renderViewport();
}

function switchNav(tab) {
  currentNav = tab;
  document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
  const activeBtn = document.getElementById("nav-" + tab);
  if (activeBtn) activeBtn.classList.add("active");

  if (tab === "europa") {
    loadEuropaMatches();
  } else {
    renderViewport();
  }
}

(async function startApp() {
  const dates = getDatesList();
  selectedDate = dates[1].iso;
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
