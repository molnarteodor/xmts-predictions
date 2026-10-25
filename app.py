import os
import json
import psycopg2
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    return None

def init_db():
    conn = get_db_connection()
    if conn:
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
                print("Baza de date a fost inițializată cu datele default.")
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print("Eroare la init_db:", e)

try:
    init_db()
except Exception as e:
    print("Nu s-a putut initializa baza de date:", e)

@app.route("/api/project", methods=["GET", "POST"])
def api_project():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No database connection"}), 500

    try:
        cur = conn.cursor()
        if request.method == "POST":
            body = request.get_json(silent=True)
            if body and "bankroll" in body and "bets" in body:
                cur.execute("DELETE FROM jack_project;")
                cur.execute("INSERT INTO jack_project (data) VALUES (%s);", [json.dumps(body)])
                conn.commit()
                print(f"Salvat în DB cu succes! Pariuri: {len(body.get('bets', []))}")
                cur.close()
                conn.close()
                return jsonify(body)
        
        cur.execute("SELECT data FROM jack_project ORDER BY id DESC LIMIT 1;")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return jsonify(json.loads(row[0]))
    except Exception as e:
        print("Eroare în rutele API:", e)
        if conn:
            conn.close()

    return jsonify({
        "initial_bankroll": 500.0,
        "target_bankroll": 800.0,
        "bankroll": 500.0,
        "bets": []
    })

HTML_PAGE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>XMTS · Neural HUD</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #020408;
    --card-bg: rgba(10, 15, 28, 0.7);
    --card-border: rgba(0, 243, 255, 0.2);
    --card-border-hover: rgba(0, 243, 255, 0.6);
    --neon-cyan: #00f3ff;
    --neon-gold: #ffb703;
    --neon-green: #06d6a0;
    --neon-red: #ef476f;
    --text-main: #f8fafc;
    --text-muted: #64748b;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; -webkit-tap-highlight-color: transparent; }
  html, body { height: 100%; width: 100%; background: var(--bg); color: var(--text-main); overflow: hidden; }
  body::before {
    content: ""; position: fixed; top: -50%; left: -50%; width: 200%; height: 200%;
    background: radial-gradient(circle at 50% 30%, rgba(0,243,255,0.04) 0%, transparent 60%),
                radial-gradient(circle at 80% 80%, rgba(255,183,3,0.03) 0%, transparent 50%);
    z-index: -2; pointer-events: none;
  }
  .app-shell { display: flex; flex-direction: column; height: 100dvh; max-width: 520px; margin: 0 auto; position: relative; }
  .top-hud {
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px 18px; background: rgba(2, 4, 8, 0.85);
    backdrop-filter: blur(20px); border-bottom: 1px solid var(--card-border); z-index: 20;
  }
  .hud-brand { display: flex; align-items: center; gap: 10px; }
  .hud-logo {
    width: 38px; height: 38px; border-radius: 12px;
    background: linear-gradient(135deg, var(--neon-cyan), var(--neon-gold));
    display: flex; align-items: center; justify-content: center;
    font-family: 'Orbitron', sans-serif; font-weight: 900; color: #020408; font-size: 16px;
    box-shadow: 0 0 15px rgba(0,243,255,0.4);
  }
  .hud-title { font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: 900; letter-spacing: 1px; color: #fff; }
  .hud-status { font-size: 10px; color: var(--neon-green); font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
  .hud-bank {
    background: rgba(6, 214, 160, 0.1); border: 1px solid rgba(6, 214, 160, 0.4);
    color: var(--neon-green); padding: 8px 14px; border-radius: 14px; font-family: 'Orbitron', sans-serif;
    font-size: 13px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 6px;
    box-shadow: 0 0 15px rgba(6, 214, 160, 0.15); transition: 0.2s;
  }
  .sub-bars { background: rgba(5, 9, 18, 0.6); border-bottom: 1px solid var(--card-border); padding: 10px 14px 8px; backdrop-filter: blur(10px); }
  .h-scroll { display: flex; gap: 8px; overflow-x: auto; scrollbar-width: none; padding-bottom: 2px; }
  .h-scroll::-webkit-scrollbar { display: none; }
  .cyber-chip {
    background: rgba(15, 23, 42, 0.8); border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 7px 14px; border-radius: 10px; font-size: 11px; font-weight: 700;
    white-space: nowrap; cursor: pointer; transition: 0.2s;
  }
  .cyber-chip.active { background: var(--neon-cyan); color: #020408; border-color: var(--neon-cyan); font-weight: 800; box-shadow: 0 0 12px rgba(0, 243, 255, 0.4); }
  .cyber-chip-gold.active { background: var(--neon-gold); color: #020408; border-color: var(--neon-gold); box-shadow: 0 0 12px rgba(255, 183, 3, 0.4); }
  .viewport { flex: 1; overflow-y: auto; padding: 14px; padding-bottom: 90px; -webkit-overflow-scrolling: touch; }
  .cyber-sec-head {
    display: flex; justify-content: space-between; align-items: center;
    background: linear-gradient(90deg, rgba(0,243,255,0.1), rgba(10,15,28,0.6));
    border-left: 3px solid var(--neon-cyan); border-radius: 8px;
    padding: 9px 14px; margin: 14px 0 10px; font-family: 'Orbitron', sans-serif;
    font-size: 11px; font-weight: 700; letter-spacing: 0.5px; color: var(--neon-cyan);
  }
  .cyber-card {
    background: var(--card-bg); border: 1px solid var(--card-border);
    backdrop-filter: blur(16px); border-radius: 18px; padding: 16px; margin-bottom: 12px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.6); transition: 0.25s; position: relative; overflow: hidden;
  }
  .card-top { display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--text-muted); margin-bottom: 10px; }
  .status-badge { padding: 3px 9px; border-radius: 6px; font-weight: 800; font-size: 9px; font-family: 'Orbitron', sans-serif; letter-spacing: 0.5px; }
  .st-live { background: rgba(239,71,111,0.2); color: var(--neon-red); border: 1px solid var(--neon-red); }
  .st-ft { background: rgba(6,214,160,0.2); color: var(--neon-green); border: 1px solid var(--neon-green); }
  .st-ns { background: rgba(255,255,255,0.05); color: #cbd5e1; border: 1px solid rgba(255,255,255,0.1); }
  .teams-container { display: flex; justify-content: space-between; align-items: center; margin: 8px 0 12px; }
  .team-name { width: 40%; font-size: 14px; font-weight: 800; line-height: 1.3; }
  .team-name.away { text-align: right; }
  .score-display {
    background: rgba(15, 23, 42, 0.9); border: 1px solid var(--card-border);
    padding: 6px 14px; border-radius: 12px; font-family: 'Orbitron', sans-serif;
    font-weight: 900; font-size: 13px; color: var(--neon-gold);
    box-shadow: 0 0 12px rgba(255,183,3,0.25);
  }
  .prediction-panel {
    background: rgba(2, 4, 8, 0.8); border: 1px solid var(--card-border);
    border-radius: 14px; padding: 12px 14px; display: flex; justify-content: space-between; align-items: center;
  }
  .pred-main { font-size: 12px; font-weight: 800; color: #fff; }
  .pred-sub { font-size: 10px; color: var(--text-muted); margin-top: 3px; }
  .odd-chip {
    background: rgba(255,183,3,0.12); border: 1px solid var(--neon-gold); color: var(--neon-gold);
    padding: 5px 11px; border-radius: 10px; font-family: 'Orbitron', sans-serif; font-weight: 800; font-size: 12px;
  }
  .action-bar { display: flex; gap: 8px; margin-top: 10px; }
  .cyber-btn {
    flex: 1; background: rgba(15, 23, 42, 0.9); border: 1px solid var(--card-border); color: var(--text-main);
    padding: 9px; border-radius: 12px; font-size: 11px; font-weight: 700; cursor: pointer; transition: 0.2s;
  }
  .cyber-btn.accent { background: rgba(6, 214, 160, 0.15); border-color: rgba(6, 214, 160, 0.5); color: var(--neon-green); flex: 0.7; }
  .analytics-drawer { display: none; margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--card-border); font-size: 11px; }
  .matrix-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 10px; }
  .matrix-cell { background: rgba(15, 23, 42, 0.8); padding: 8px; border-radius: 10px; text-align: center; border: 1px solid var(--card-border); }
  .matrix-cell b { display: block; color: var(--neon-gold); font-family: 'Orbitron', sans-serif; font-size: 12px; margin-top: 3px; }
  .vault-hero {
    background: linear-gradient(135deg, #091526, #020408);
    border: 1px solid rgba(0, 243, 255, 0.4); border-radius: 22px; padding: 20px; margin-bottom: 16px;
    position: relative; overflow: hidden; box-shadow: 0 0 35px rgba(0,243,255,0.15);
  }
  .vault-profile { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; position: relative; z-index: 2; }
  .vault-avatar {
    width: 64px; height: 64px; border-radius: 50%; border: 2.5px solid var(--neon-cyan);
    background: #020408 url('/jack_avatar.png') center/cover no-repeat;
    display: flex; align-items: center; justify-content: center; font-size: 28px;
    box-shadow: 0 0 20px rgba(0,243,255,0.5); flex-shrink: 0;
  }
  .vault-quote { font-style: italic; font-size: 11px; color: var(--neon-cyan); background: rgba(0,243,255,0.06); padding: 9px 13px; border-radius: 12px; border-left: 2.5px solid var(--neon-cyan); margin-top: 4px; line-height: 1.4; }
  .vault-kpi-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 14px; }
  .vault-kpi { background: rgba(2, 4, 8, 0.6); border: 1px solid var(--card-border); border-radius: 12px; padding: 10px; text-align: center; }
  .v-lbl { font-size: 9px; color: var(--text-muted); text-transform: uppercase; font-family: 'Orbitron', sans-serif; }
  .v-val { font-size: 13px; font-family: 'Orbitron', sans-serif; font-weight: 900; margin-top: 4px; }
  .cyber-progress { width: 100%; height: 10px; background: rgba(255,255,255,0.04); border-radius: 99px; margin-top: 14px; overflow: hidden; border: 1px solid var(--card-border); }
  .cyber-progress-fill { height: 100%; background: linear-gradient(90deg, var(--neon-green), var(--neon-cyan)); border-radius: 99px; box-shadow: 0 0 15px rgba(0,243,255,0.5); transition: 0.4s; }
  .bet-ticket {
    background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 16px;
    padding: 14px; margin-bottom: 10px; backdrop-filter: blur(12px);
  }
  .bet-ticket-actions { display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }
  .t-btn { flex: 1; padding: 7px; border-radius: 10px; border: 1px solid var(--card-border); font-size: 11px; font-weight: 800; cursor: pointer; background: rgba(15, 23, 42, 0.9); color: #fff; min-width: 65px; }
  .t-win { background: rgba(6,214,160,0.15); border-color: var(--neon-green); color: var(--neon-green); }
  .t-loss { background: rgba(239,71,111,0.15); border-color: var(--neon-red); color: var(--neon-red); }
  .t-edit { background: rgba(0,243,255,0.15); border-color: var(--neon-cyan); color: var(--neon-cyan); }
  .bottom-hud-nav {
    position: fixed; bottom: 0; left: 50%; transform: translateX(-50%);
    width: 100%; max-width: 520px; height: 72px;
    background: rgba(2, 4, 8, 0.92); backdrop-filter: blur(22px);
    border-top: 1px solid var(--card-border); display: flex; justify-content: space-around; align-items: center;
    padding-bottom: env(safe-area-inset-bottom); z-index: 30;
  }
  .hud-nav-item {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    color: var(--text-muted); font-size: 9px; font-family: 'Orbitron', sans-serif; font-weight: 700; gap: 4px; cursor: pointer;
    background: none; border: none; width: 25%; height: 100%; transition: 0.2s; text-transform: uppercase;
  }
  .hud-nav-item .ico { font-size: 20px; }
  .hud-nav-item.active { color: var(--neon-cyan); text-shadow: 0 0 12px rgba(0,243,255,0.6); }
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
    <div class="hud-bank" onclick="switchNav('proiect')">
      💰 <span id="topBankroll">500.00</span> RON
    </div>
  </div>

  <div class="sub-bars" id="subBars">
    <div class="h-scroll" id="dateBar"></div>
    <div class="h-scroll" id="leagueBar" style="margin-top:6px;"></div>
  </div>

  <div class="viewport" id="viewport"></div>

  <nav class="bottom-hud-nav">
    <button class="hud-nav-item active" id="nav-meciuri" onclick="switchNav('meciuri')">
      <span class="ico">⚽</span><span>Meciuri</span>
    </button>
    <button class="hud-nav-item" id="nav-europa" onclick="switchNav('europa')">
      <span class="ico">🏆</span><span>Europa</span>
    </button>
    <button class="hud-nav-item" id="nav-proiect" onclick="switchNav('proiect')">
      <span class="ico">⚡</span><span>Jack Vault</span>
    </button>
    <button class="hud-nav-item" id="nav-bilete" onclick="switchNav('bilete')">
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
  const labels = {"-
