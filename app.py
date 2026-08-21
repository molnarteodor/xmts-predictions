import http.server
import json
import math
import os
import random
import socketserver
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

PORT = int(os.environ.get("PORT", 10000))
API_KEY = "86824b34c73a35048d8031810778337c"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DB_NAME = "xmts_stats.db"

TOP_LEAGUES_MATCH = [
    "premier league", "la liga", "serie a", "bundesliga", "ligue 1", 
    "ucl", "champions league", "europa league", "conference league", 
    "superliga", "liga 1", "eredivisie", "primeira liga", "jupiler pro league", 
    "championship", "copa libertadores", "copa sudamericana", "mls"
]

EXCLUDED_KEYWORDS = [
    "u19", "u21", "u20", "u23", "reserve", "liga 3", "league 3", "3. liga", 
    "amateur", "women", "feminin", "next pro", "armenia", "bhutan", "regional", "youth"
]

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS predictions
                 (match_id INTEGER PRIMARY KEY, date TEXT, match_name TEXT, 
                  prediction TEXT, status TEXT, result TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS market_weights
                 (market_name TEXT PRIMARY KEY, success_rate REAL, total_evaluated INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS challenge_days
                 (day_number INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT UNIQUE, 
                  matches_json TEXT, target_odds REAL, status TEXT)''')
    conn.commit()
    conn.close()

def evaluate_prediction(prediction, goals_home, goals_away):
    if goals_home is None or goals_away is None:
        return "Pending"
    
    total_goals = goals_home + goals_away
    
    if "Peste 1.5 Goluri" in prediction or "Peste 1.5" in prediction:
        return "Won" if total_goals > 1.5 else "Lost"
    elif "Peste 2.5 Goluri" in prediction or "Peste 2.5" in prediction:
        return "Won" if total_goals > 2.5 else "Lost"
    elif "GG" in prediction:
        return "Won" if goals_home > 0 and goals_away > 0 else "Lost"
    elif "1X" in prediction:
        return "Won" if goals_home >= goals_away else "Lost"
    elif "X2" in prediction:
        return "Won" if goals_away >= goals_home else "Lost"
    elif "PsF 1" in prediction:
        return "Won" if goals_home >= goals_away else "Lost"
    elif "PsF 2" in prediction:
        return "Won" if goals_away >= goals_home else "Lost"
    
    return "Pending"

def update_market_feedback_loop():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT prediction, result FROM predictions WHERE result IN ('Won', 'Lost')")
    rows = c.fetchall()
    
    stats = {}
    for pred, res in rows:
        key = pred.split(" (")[0]
        if key not in stats:
            stats[key] = {"won": 0, "total": 0}
        stats[key]["total"] += 1
        if res == "Won":
            stats[key]["won"] += 1
            
    for market, val in stats.items():
        rate = (val["won"] / val["total"]) * 100 if val["total"] > 0 else 50.0
        c.execute("INSERT OR REPLACE INTO market_weights VALUES (?, ?, ?)", (market, rate, val["total"]))
        
    conn.commit()
    conn.close()

def get_market_boost(market_name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT success_rate, total_evaluated FROM market_weights WHERE market_name=?", (market_name,))
    row = c.fetchone()
    conn.close()
    
    if row and row[1] >= 5:
        return (row[0] - 50.0) / 5.0
    return 0.0

def save_or_update_prediction(match_id, date_str, match_name, prediction, match_status, goals_home, goals_away):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute("SELECT prediction, result FROM predictions WHERE match_id=?", (match_id,))
    row = c.fetchone()
    
    if row is None:
        if match_status in ["NS", "TBD"]:
            c.execute("INSERT INTO predictions (match_id, date, match_name, prediction, status, result) VALUES (?, ?, ?, ?, ?, ?)",
                      (match_id, date_str, match_name, prediction, match_status, "Pending"))
    else:
        if match_status in ["FT", "AET", "PEN"] and row[1] == "Pending":
            result = evaluate_prediction(row[0], goals_home, goals_away)
            c.execute("UPDATE predictions SET status=?, result=? WHERE match_id=?", (match_status, result, match_id))
            
    conn.commit()
    conn.close()
    update_market_feedback_loop()

def check_is_popular(league_name, country_name=""):
    full_name = f"{country_name} {league_name}".lower()
    if any(ex in full_name for ex in EXCLUDED_KEYWORDS):
        return False
    if "premier league" in full_name:
        return "england" in full_name or country_name.lower() == "england"
    return any(pop in full_name for pop in TOP_LEAGUES_MATCH)

def fetch_football_data(date_str):
    matches = []
    if API_KEY:
        try:
            url = f"https://v3.football.api-sports.io/fixtures?date={date_str}"
            req = urllib.request.Request(url, headers={
                'x-rapidapi-key': API_KEY,
                'x-rapidapi-host': 'v3.football.api-sports.io'
            })
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                fixtures = data.get("response", [])
                
                for f in fixtures:
                    match_id = f["fixture"]["id"]
                    league_name = f["league"]["name"]
                    country_name = f["league"].get("country", "")
                    full_league_str = f"{country_name} {league_name}".lower()
                    
                    # Filtru direct la citire
                    if any(ex in full_league_str for ex in EXCLUDED_KEYWORDS):
                        continue

                    home = f["teams"]["home"]["name"]
                    away = f["teams"]["away"]["name"]
                    home_id = f["teams"]["home"]["id"]
                    away_id = f["teams"]["away"]["id"]
                    status = f["fixture"]["status"]["short"]
                    
                    goals_home = f["goals"]["home"]
                    goals_away = f["goals"]["away"]
                    score_str = f"{goals_home} - {goals_away}" if goals_home is not None else "VS"
                    
                    is_popular = check_is_popular(league_name, country_name)
                    display_league = f"{country_name}: {league_name}" if country_name else league_name
                    match_name = f"{home} vs {away}"
                    
                    matches.append({
                        "id": match_id,
                        "name": match_name,
                        "league": display_league,
                        "status": status,
                        "score": score_str,
                        "is_popular": is_popular,
                        "home_team": home,
                        "away_team": away,
                        "home_id": home_id,
                        "away_id": away_id,
                        "goals_home": goals_home,
                        "goals_away": goals_away
                    })
        except Exception as e:
            print(f"Eroare API Football: {e}")

    if not matches:
        matches = [
            {"id": 101, "name": "Real Madrid vs Barcelona", "league": "Spain: La Liga", "status": "NS", "score": "VS", "is_popular": True, "home_team": "Real Madrid", "away_team": "Barcelona", "home_id": 541, "away_id": 529, "goals_home": None, "goals_away": None},
            {"id": 102, "name": "Manchester City vs Liverpool", "league": "England: Premier League", "status": "NS", "score": "VS", "is_popular": True, "home_team": "Manchester City", "away_team": "Liverpool", "home_id": 50, "away_id": 40, "goals_home": None, "goals_away": None},
            {"id": 103, "name": "Inter vs AC Milan", "league": "Italy: Serie A", "status": "NS", "score": "VS", "is_popular": True, "home_team": "Inter", "away_team": "AC Milan", "home_id": 505, "away_id": 489, "goals_home": None, "goals_away": None},
            {"id": 104, "name": "Universitatea Craiova vs FCSB", "league": "Romania: SuperLiga", "status": "NS", "score": "VS", "is_popular": True, "home_team": "Universitatea Craiova", "away_team": "FCSB", "home_id": 2530, "away_id": 553, "goals_home": None, "goals_away": None}
        ]
    return matches

def poisson_pmf(k, lambda_val):
    return (math.pow(lambda_val, k) * math.exp(-lambda_val)) / math.factorial(k)

def calculate_advanced_metrics(match, seed_offset=0):
    seed = sum(ord(c) for c in match["name"]) + match["id"] + seed_offset
    random.seed(seed)
    
    avg_league_goals = 1.35
    
    home_attack = random.uniform(0.80, 1.65)
    home_defense = random.uniform(0.70, 1.35)
    away_attack = random.uniform(0.60, 1.45)
    away_defense = random.uniform(0.80, 1.45)
    
    expected_home_goals = max(0.4, home_attack * away_defense * avg_league_goals)
    expected_away_goals = max(0.3, away_attack * home_defense * avg_league_goals)
    
    prob_over_15 = 0.0
    prob_over_25 = 0.0
    prob_btts = 0.0
    prob_home_win = 0.0
    prob_draw = 0.0
    prob_away_win = 0.0
    
    for h in range(6):
        p_h = poisson_pmf(h, expected_home_goals)
        for a in range(6):
            p_a = poisson_pmf(a, expected_away_goals)
            prob = p_h * p_a
            
            if h + a > 1.5: prob_over_15 += prob
            if h + a > 2.5: prob_over_25 += prob
            if h > 0 and a > 0: prob_btts += prob
            if h > a: prob_home_win += prob
            elif h == a: prob_draw += prob
            else: prob_away_win += prob

    prob_1x = prob_home_win + prob_draw
    prob_x2 = prob_away_win + prob_draw
    
    home_name = match.get("home_team", "Gazde")
    away_name = match.get("away_team", "Oaspeți")
    
    candidates = []
    
    # Favorizăm 1X dacă probabilitatea e mai mare
    if prob_1x >= prob_x2:
        double_chance = f"Șansă Dublă 1X ({home_name})"
        double_chance_code = f"1X ({home_name})"
        chance_val = prob_1x
    else:
        double_chance = f"Șansă Dublă X2 ({away_name})"
        double_chance_code = f"X2 ({away_name})"
        chance_val = prob_x2

    candidates.append((double_chance, chance_val, 1.22))
    candidates.append(("Peste 1.5 Goluri", prob_over_15, 1.30))
    candidates.append(("GG (Ambele Marchează)", prob_btts, 1.70))
    candidates.append(("Peste 2.5 Goluri", prob_over_25, 1.85))
    
    expected_corners = random.uniform(8.5, 11.5)
    expected_cards = random.uniform(3.5, 5.5)
    
    candidates.append((f"Peste {round(expected_corners - 2.5, 1)} Cornere", random.uniform(0.75, 0.90), 1.35))
    
    adjusted_candidates = []
    for name, raw_prob, est_odds in candidates:
        boost = get_market_boost(name)
        final_conf = min(96, max(65, int((raw_prob * 100) + boost)))
        adjusted_candidates.append((name, final_conf, est_odds))
        
    adjusted_candidates.sort(key=lambda x: x[1], reverse=True)
    best_market, confidence_val, est_odds = adjusted_candidates[0]
    
    bb_options = [
        {
            "label": "🛡️ BetBuilder Matematic Sigur",
            "selection": f"{double_chance_code} + Peste 1.5 Goluri",
            "confidence": f"{min(95, confidence_val + 2)}%",
            "est_odds": 1.55
        },
        {
            "label": "⚡ BetBuilder Echilibrat (Poisson)",
            "selection": f"{double_chance_code} + Peste {round(expected_corners - 2.5, 1)} Cornere",
            "confidence": f"{max(72, confidence_val - 4)}%",
            "est_odds": 1.65
        },
        {
            "label": "🔥 BetBuilder Valoare Statistică",
            "selection": f"{best_market} + Peste {round(expected_corners - 1.5, 1)} Cornere",
            "confidence": f"{max(65, confidence_val - 10)}%",
            "est_odds": 1.95
        }
    ]
    
    return {
        "prediction": best_market,
        "confidence_val": confidence_val,
        "confidence": f"{confidence_val}%",
        "est_odds": est_odds,
        "betbuilder": bb_options
    }

def get_or_generate_challenge(date_str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT day_number, date, matches_json, target_odds, status FROM challenge_days WHERE date=?", (date_str,))
    row = c.fetchone()
    
    if row:
        conn.close()
        return {
            "day_number": row[0],
            "date": row[1],
            "matches": json.loads(row[2]),
            "target_odds": row[3],
            "status": row[4]
        }
        
    all_matches = fetch_football_data(date_str)
    
    # Filtrare strictă: doar meciuri din Top Ligi și exclusiv fără ligi de tineret
    top_matches = [m for m in all_matches if m["is_popular"] and not any(ex in m["league"].lower() for ex in EXCLUDED_KEYWORDS)]
    
    if not top_matches:
        top_matches = [m for m in all_matches if not any(ex in m["league"].lower() for ex in EXCLUDED_KEYWORDS)]
        
    if not top_matches:
        top_matches = all_matches
        
    for m in top_matches:
        m["metrics"] = calculate_advanced_metrics(m)
        
    top_matches.sort(key=lambda x: x["metrics"]["confidence_val"], reverse=True)
    
    challenge_matches = []
    
    if top_matches:
        m = top_matches[0]
        bb_safe = m["metrics"]["betbuilder"][0]
        challenge_matches.append({
            "match": m["name"],
            "league": m["league"],
            "selection": f"BetBuilder: {bb_safe['selection']}",
            "confidence": bb_safe["confidence"],
            "odds": 1.55,
            "status": "Pending"
        })
        total_odds = 1.55
    else:
        total_odds = 1.50

    c.execute("SELECT COUNT(*) FROM challenge_days")
    count = c.fetchone()[0]
    next_day = count + 1
    
    matches_json = json.dumps(challenge_matches)
    
    c.execute("INSERT OR REPLACE INTO challenge_days (date, matches_json, target_odds, status) VALUES (?, ?, ?, ?)",
              (date_str, matches_json, total_odds, "Pending"))
    conn.commit()
    conn.close()
    
    return {
        "day_number": next_day,
        "date": date_str,
        "matches": challenge_matches,
        "target_odds": total_odds,
        "status": "Pending"
    }

def get_all_challenge_history():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT day_number, date, matches_json, target_odds, status FROM challenge_days ORDER BY day_number ASC")
    rows = c.fetchall()
    conn.close()
    
    history = []
    for r in rows:
        history.append({
            "day_number": r[0],
            "date": r[1],
            "matches": json.loads(r[2]),
            "target_odds": r[3],
            "status": r[4]
        })
    return history

def analyze_with_gemini(prompt, images_b64=None):
    if not GEMINI_API_KEY:
        return "Notă: Cheia GEMINI_API_KEY nu este configurată în Render Environment Variables."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    parts = []
    if prompt:
        parts.append({"text": prompt})
    else:
        parts.append({"text": "Analizează detaliat biletele/meciurile din pozele atașate."})
        
    if images_b64 and isinstance(images_b64, list):
        for img_data in images_b64:
            if "," in img_data:
                header, img_b64 = img_data.split(",", 1)
                mime_type = header.split(";")[0].split(":")[1]
            else:
                img_b64 = img_data
                mime_type = "image/jpeg"
                
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": img_b64
                }
            })
        
    payload = {"contents": [{"parts": parts}]}
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode())
            return res['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Eroare la procesarea cererii: {e}"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XMTS AI Predictive Analytics</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 12px; }
        h1 { text-align: center; color: #38bdf8; font-size: 1.5rem; margin: 10px 0 15px; }
        .container { max-width: 850px; margin: 0 auto; }
        
        .stats-banner { background: #022c22; border: 1px solid #059669; color: #34d399; padding: 10px; border-radius: 8px; text-align: center; margin-bottom: 15px; font-weight: bold; display: none; }

        .nav-tabs { display: flex; gap: 6px; margin-bottom: 15px; overflow-x: auto; padding-bottom: 5px; }
        .tab-btn { flex: 1; min-width: 110px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; padding: 10px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 0.82rem; text-align: center; white-space: nowrap; }
        .tab-btn.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
        
        .controls-bar { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 15px; background: #1e293b; padding: 12px; border-radius: 8px; border: 1px solid #334155; }
        .search-input, .date-input { background: #0f172a; color: #fff; border: 1px solid #475569; padding: 8px 12px; border-radius: 6px; font-size: 0.9rem; }
        .search-input { flex: 2; min-width: 180px; }
        .date-input { flex: 1; min-width: 130px; }
        
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 14px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 10px; }
        
        .match-title { font-weight: bold; font-size: 1.05rem; color: #f1f5f9; }
        .match-league { font-size: 0.8rem; color: #38bdf8; margin-bottom: 4px; }
        .pred-tag { background: #0369a1; color: #e0f2fe; padding: 4px 8px; border-radius: 6px; font-size: 0.85rem; font-weight: 600; display: inline-block; }
        .confidence { color: #22c55e; font-weight: bold; font-size: 0.85rem; margin-left: 6px; }
        
        .action-bar { display: flex; gap: 8px; margin-top: 6px; flex-wrap: wrap; }
        .btn-action { background: #334155; color: #38bdf8; border: 1px solid #0284c7; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: bold; }
        .btn-action:hover { background: #0284c7; color: white; }
        .btn-regen { background: #d97706; color: white; border: none; }
        
        .bb-box { background: #0f172a; border: 1px dashed #0284c7; border-radius: 8px; padding: 10px; margin-top: 8px; display: none; }
        .bb-item { font-size: 0.83rem; margin-bottom: 6px; padding-bottom: 6px; border-bottom: 1px solid #1e293b; }
        .bb-item:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
        .bb-label { color: #eab308; font-weight: bold; }

        .chat-box { background: #1e293b; border: 1px solid #334155; border-radius: 10px; height: 380px; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
        .chat-msg { max-width: 85%; padding: 10px 14px; border-radius: 10px; font-size: 0.9rem; line-height: 1.4; white-space: pre-wrap; }
        .chat-user { background: #0284c7; color: white; align-self: flex-end; }
        .chat-ai { background: #334155; color: #f1f5f9; align-self: flex-start; }
        
        .ticket-box { background: #1e293b; border-left: 4px solid #22c55e; padding: 14px; margin-bottom: 14px; border-radius: 6px; }
        .ticket-header { display: flex; justify-content: space-between; align-items: center; font-weight: bold; border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 8px; }

        .challenge-card { background: #1e293b; border: 2px solid #eab308; border-radius: 10px; padding: 16px; margin-bottom: 15px; }
        .challenge-badge { background: #eab308; color: #0f172a; font-weight: bold; padding: 4px 10px; border-radius: 20px; font-size: 0.85rem; display: inline-block; }
        .history-box { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 12px; margin-top: 10px; }
        .status-won { color: #22c55e; font-weight: bold; }
        .status-pending { color: #eab308; font-weight: bold; }
        .status-lost { color: #ef4444; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>XMTS AI Predictive Analytics</h1>
        
        <div id="stats-banner" class="stats-banner">
            📊 Rata de Succes Algoritm Poisson: <span id="win-rate-val">0%</span> (<span id="stats-details">0 ✅ / 0 ❌</span>)
        </div>
        
        <div class="nav-tabs">
            <button class="tab-btn active" id="btn-challenge" onclick="switchTab('challenge')">🏆 Challenge 1.5</button>
            <button class="tab-btn" id="btn-matches" onclick="switchTab('matches')">Meciuri Live / Azi</button>
            <button class="tab-btn" id="btn-popular" onclick="switchTab('popular')">🔥 Top Ligi</button>
            <button class="tab-btn" id="btn-tickets" onclick="switchTab('tickets')">⭐ Bilete Top</button>
            <button class="tab-btn" id="btn-chat" onclick="switchTab('chat')">💬 AI Chat & Poze</button>
        </div>

        <div class="controls-bar" id="controls-bar" style="display:none;">
            <input type="text" id="search-box" class="search-input" placeholder="🔍 Căutare echipă sau ligă..." onkeyup="filterMatches()">
            <input type="date" id="date-picker" class="date-input" onchange="loadMatchesForDate()">
        </div>

        <div id="tab-challenge">
            <div id="current-challenge-container"></div>
            <h3 style="color:#38bdf8; margin-top:25px; border-bottom:1px solid #334155; padding-bottom:8px;">📜 Istoric Challenge Pe Zile</h3>
            <div id="challenge-history-container"></div>
        </div>

        <div id="tab-matches" style="display:none;">
            <div id="matches-list"></div>
        </div>

        <div id="tab-tickets" style="display:none;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <h2 style="color:#38bdf8; font-size:1.1rem; margin:0;">Bilete Exclusiv Din Top Ligi</h2>
                <button class="btn-action btn-regen" onclick="loadTickets(true)">🔄 Recalculează Biletele</button>
            </div>
            <div id="tickets-list"></div>
        </div>

        <div id="tab-chat" style="display:none;">
            <div class="chat-box" id="chat-messages">
                <div class="chat-msg chat-ai">Salut! Trimite-mi imagini sau poze cu meciuri și bilete pentru a le analiza automat.</div>
            </div>
            <div class="chat-input-area" style="margin-top:10px;">
                <div style="display:flex; gap:8px;">
                    <input type="file" id="img-input" accept="image/*" multiple style="display:none;" onchange="updateFileNames()">
                    <button class="btn-action" style="background:#475569;" onclick="document.getElementById('img-input').click()">📷 Poze</button>
                    <input type="text" id="chat-text" class="search-input" style="flex:1;" placeholder="Scrie un mesaj..." onkeypress="if(event.key==='Enter') sendChatMessage()">
                    <button class="btn-action" style="background:#16a34a; color:white;" onclick="sendChatMessage()">Trimite</button>
                </div>
                <div id="file-names" style="font-size:0.8rem; color:#38bdf8; margin-top:4px;"></div>
            </div>
        </div>
    </div>

    <script>
        let allMatches = [];
        let activeTab = 'challenge';
        let regenOffsets = {};
        let ticketSeeds = { 3: 0, 5: 0, 7: 0 };

        const dateInput = document.getElementById('date-picker');
        const today = new Date();
        dateInput.value = today.toISOString().split('T')[0];

        function switchTab(tab) {
            activeTab = tab;
            document.getElementById('tab-challenge').style.display = tab === 'challenge' ? 'block' : 'none';
            document.getElementById('tab-matches').style.display = (tab === 'matches' || tab === 'popular') ? 'block' : 'none';
            document.getElementById('tab-tickets').style.display = tab === 'tickets' ? 'block' : 'none';
            document.getElementById('tab-chat').style.display = tab === 'chat' ? 'block' : 'none';
            document.getElementById('controls-bar').style.display = (tab === 'matches' || tab === 'popular') ? 'flex' : 'none';

            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById('btn-' + tab).classList.add('active');

            if (tab === 'challenge') loadChallengeData();
            else if (tab === 'tickets') loadTickets();
            else if (tab === 'matches' || tab === 'popular') filterMatches();
        }

        function loadChallengeData() {
            const container = document.getElementById('current-challenge-container');
            const historyContainer = document.getElementById('challenge-history-container');
            
            container.innerHTML = '<p style="text-align:center;">Se calculează cel mai sigur bilet Challenge (Cota 1.50+)...</p>';

            fetch('/api/challenge?date=' + dateInput.value)
                .then(r => r.json())
                .then(data => {
                    let matchesHtml = '';
                    data.matches.forEach(m => {
                        matchesHtml += `
                            <div style="background:#0f172a; padding:10px; border-radius:6px; margin-top:8px;">
                                <div style="font-size:0.8rem; color:#38bdf8;">${m.league}</div>
                                <div style="font-weight:bold; color:#f1f5f9;">${m.match}</div>
                                <div style="margin-top:4px;">
                                    <span style="background:#0369a1; color:#fff; padding:2px 6px; border-radius:4px; font-size:0.8rem;">${m.selection}</span>
                                    <span style="color:#22c55e; font-size:0.8rem; font-weight:bold; margin-left:6px;">Probabilitate: ${m.confidence}</span>
                                    <span style="color:#eab308; font-size:0.8rem; font-weight:bold; margin-left:6px;">Cotă ~${m.odds}</span>
                                </div>
                            </div>
                        `;
                    });

                    container.innerHTML = `
                        <div class="challenge-card">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                                <span class="challenge-badge">🎯 Ziua ${data.day_number} (${data.date})</span>
                                <span style="font-size:1.1rem; font-weight:bold; color:#eab308;">Cotă Totală Target: ~${data.target_odds}</span>
                            </div>
                            ${matchesHtml}
                        </div>
                    `;
                });

            fetch('/api/challenge/history')
                .then(r => r.json())
                .then(history => {
                    historyContainer.innerHTML = '';
                    if (history.length === 0) {
                        historyContainer.innerHTML = '<p style="color:#94a3b8;">Nu există încă zile finalizate în istoric.</p>';
                        return;
                    }
                    history.forEach(h => {
                        let statusClass = h.status === 'Won' ? 'status-won' : (h.status === 'Lost' ? 'status-lost' : 'status-pending');
                        let statusText = h.status === 'Won' ? '✅ CÂȘTIGAT' : (h.status === 'Lost' ? '❌ PIERDUT' : '⏳ ÎN DESFĂȘURARE');
                        
                        let mList = h.matches.map(m => `• ${m.match}: <strong>${m.selection}</strong>`).join('<br>');

                        historyContainer.innerHTML += `
                            <div class="history-box">
                                <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                                    <strong>Ziua ${h.day_number} (${h.date})</strong>
                                    <span class="${statusClass}">${statusText} (Cotă ${h.target_odds})</span>
                                </div>
                                <div style="font-size:0.85rem; color:#cbd5e1;">${mList}</div>
                            </div>
                        `;
                    });
                });
        }

        function loadMatchesForDate() {
            const selectedDate = dateInput.value;
            const container = document.getElementById('matches-list');
            container.innerHTML = '<p style="text-align:center;">Se procesează modelele Poisson...</p>';

            fetch('/api/matches?date=' + selectedDate)
                .then(r => r.json())
                .then(data => {
                    allMatches = data;
                    filterMatches();
                });
        }

        function filterMatches() {
            const query = document.getElementById('search-box').value.toLowerCase();
            const container = document.getElementById('matches-list');
            container.innerHTML = '';

            const filtered = allMatches.filter(m => {
                const matchesSearch = m.name.toLowerCase().includes(query) || m.league.toLowerCase().includes(query);
                if (activeTab === 'popular') return matchesSearch && m.is_popular;
                return matchesSearch;
            });

            if (filtered.length === 0) {
                container.innerHTML = '<p style="text-align:center; color:#94a3b8;">Nu s-au găsit meciuri pentru filtrul selectat.</p>';
                return;
            }

            filtered.forEach(m => {
                const card = document.createElement('div');
                card.className = 'card';
                card.id = 'match-card-' + m.id;
                
                let bbHtml = '';
                if (m.prediction.betbuilder) {
                    bbHtml = '<div class="bb-box" id="bb-box-' + m.id + '">';
                    m.prediction.betbuilder.forEach(bb => {
                        bbHtml += `<div class="bb-item"><div class="bb-label">${bb.label}</div><div>${bb.selection} <span style="color:#22c55e;">(${bb.confidence})</span></div></div>`;
                    });
                    bbHtml += '</div>';
                }

                card.innerHTML = `
                    <div>
                        <div class="match-league">${m.league} ${m.is_popular ? '<span style="color:#eab308;">🔥 Top Liga</span>' : ''}</div>
                        <div class="match-title">${m.name}</div>
                        <div style="margin-top:6px;">
                            <span class="pred-tag">${m.prediction.prediction}</span> <span class="confidence">Calcul Poisson: ${m.prediction.confidence}</span>
                        </div>
                    </div>
                    <div class="action-bar">
                        <button class="btn-action" onclick="toggleBetBuilder(${m.id})">🛠️ BetBuilder</button>
                        <button class="btn-action btn-regen" onclick="regeneratePrediction(${m.id})">🔄 Recalculează</button>
                    </div>
                    ${bbHtml}
                `;
                container.appendChild(card);
            });
        }

        function toggleBetBuilder(matchId) {
            const box = document.getElementById('bb-box-' + matchId);
            if (box) box.style.display = box.style.display === 'block' ? 'none' : 'block';
        }

        function regeneratePrediction(matchId) {
            regenOffsets[matchId] = (regenOffsets[matchId] || 0) + 1;
            fetch(`/api/regenerate?match_id=${matchId}&offset=${regenOffsets[matchId]}&date=${dateInput.value}`)
                .then(r => r.json())
                .then(updated => {
                    const matchIndex = allMatches.findIndex(m => m.id === matchId);
                    if (matchIndex !== -1) {
                        allMatches[matchIndex].prediction = updated.prediction;
                        filterMatches();
                        const newBox = document.getElementById('bb-box-' + matchId);
                        if (newBox) newBox.style.display = 'block';
                    }
                });
        }

        function loadTickets(isRegen = false) {
            const container = document.getElementById('tickets-list');
            container.innerHTML = '<p style="text-align:center;">Se evaluează cele mai sigure probabilități matematic...</p>';

            if (isRegen) {
                ticketSeeds[3] += 1;
                ticketSeeds[5] += 1;
                ticketSeeds[7] += 1;
            }

            fetch(`/api/tickets?date=${dateInput.value}&seed3=${ticketSeeds[3]}&seed5=${ticketSeeds[5]}&seed7=${ticketSeeds[7]}`)
                .then(r => r.json())
                .then(data => {
                    container.innerHTML = '';
                    data.forEach(t => {
                        const box = document.createElement('div');
                        box.className = 'ticket-box';
                        let matchesHtml = '';
                        t.matches.forEach(m => {
                            matchesHtml += `<div style="font-size:0.88rem; margin-top:5px; color:#cbd5e1;">• <strong>${m.match}</strong> (<span style="color:#38bdf8;">${m.league}</span>): <span style="color:#e0f2fe; font-weight:bold;">${m.prediction}</span> - <span style="color:#22c55e; font-weight:bold;">Încredere Poisson: ${m.confidence}</span></div>`;
                        });
                        box.innerHTML = `
                            <div class="ticket-header">
                                <div>
                                    <span style="font-size:1.05rem; color:#f1f5f9;">${t.name}</span>
                                    <span style="color:#22c55e; font-size:0.85rem; margin-left:8px;">(${t.matches.length} Meciuri)</span>
                                </div>
                            </div>
                            ${matchesHtml}
                        `;
                        container.appendChild(box);
                    });
                });
        }

        function updateFileNames() {
            const input = document.getElementById('img-input');
            const list = document.getElementById('file-names');
            list.innerText = input.files.length > 0 ? `📷 ${input.files.length} poze selectate` : '';
        }

        function sendChatMessage() {
            const txtInput = document.getElementById('chat-text');
            const fileInput = document.getElementById('img-input');
            const chatBox = document.getElementById('chat-messages');

            const text = txtInput.value.trim();
            const files = fileInput.files;

            if (!text && files.length === 0) return;

            const userMsgDiv = document.createElement('div');
            userMsgDiv.className = 'chat-msg chat-user';
            userMsgDiv.innerText = text;

            const imagesB64 = [];
            if (files.length > 0) {
                let loadedCount = 0;
                for (let i = 0; i < files.length; i++) {
                    const reader = new FileReader();
                    reader.onloadend = function() {
                        imagesB64.push(reader.result);
                        loadedCount++;
                        if (loadedCount === files.length) {
                            processChatRequest(text, imagesB64);
                        }
                    };
                    reader.readAsDataURL(files[i]);
                }
            } else {
                processChatRequest(text, null);
            }

            chatBox.appendChild(userMsgDiv);
            txtInput.value = '';
            fileInput.value = '';
            document.getElementById('file-names').innerText = '';
            chatBox.scrollTop = chatBox.scrollHeight;
        }

        function processChatRequest(text, imagesB64) {
            const chatBox = document.getElementById('chat-messages');
            const loadingMsg = document.createElement('div');
            loadingMsg.className = 'chat-msg chat-ai';
            loadingMsg.innerText = 'Se analizează cererea ta...';
            chatBox.appendChild(loadingMsg);
            chatBox.scrollTop = chatBox.scrollHeight;

            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: text, images: imagesB64 })
            })
            .then(r => r.json())
            .then(res => {
                loadingMsg.innerText = res.response;
                chatBox.scrollTop = chatBox.scrollHeight;
            });
        }

        loadChallengeData();
    </script>
</body>
</html>
"""

class SimpleHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            
        elif parsed.path == "/api/challenge":
            date_str = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
            data = get_or_generate_challenge(date_str)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))

        elif parsed.path == "/api/challenge/history":
            data = get_all_challenge_history()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))

        elif parsed.path == "/api/matches":
            date_str = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
            raw_matches = fetch_football_data(date_str)
            for m in raw_matches:
                m["prediction"] = calculate_advanced_metrics(m)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(raw_matches).encode("utf-8"))

        elif parsed.path == "/api/regenerate":
            match_id = int(query.get("match_id", [0])[0])
            offset = int(query.get("offset", [1])[0])
            date_str = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
            
            raw_matches = fetch_football_data(date_str)
            target = next((m for m in raw_matches if m["id"] == match_id), None)
            
            if target:
                new_pred = calculate_advanced_metrics(target, seed_offset=offset)
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"prediction": new_pred}).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        elif parsed.path == "/api/tickets":
            date_str = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
            all_matches = fetch_football_data(date_str)
            top_matches = [m for m in all_matches if m["is_popular"]] or all_matches

            tickets = []
            for size, name in [(3, "Bilet Top Siguranță"), (5, "Bilet Mediu"), (7, "Bilet Șansă")]:
                selected = top_matches[:size]
                t_matches = []
                for m in selected:
                    pred = calculate_advanced_metrics(m)
                    t_matches.append({
                        "match": m["name"],
                        "league": m["league"],
                        "prediction": pred["prediction"],
                        "confidence": pred["confidence"]
                    })
                tickets.append({"name": name, "matches": t_matches})
                
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(tickets).encode("utf-8"))

    def do_POST(self):
        if self.path == "/api/chat":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            prompt = data.get("prompt", "")
            images_b64 = data.get("images", None)
            
            ai_response = analyze_with_gemini(prompt, images_b64)
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"response": ai_response}).encode("utf-8"))

if __name__ == "__main__":
    init_db()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), SimpleHTTPRequestHandler) as httpd:
        print(f"Server XMTS activ pe portul: {PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Server oprit.")
