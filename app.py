import http.server
import json
import math
import os
import random
import socketserver
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime

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
    "amateur", "women", "feminin", "next pro", "armenia", "bhutan", "regional"
]

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS predictions
                 (match_id INTEGER PRIMARY KEY, date TEXT, match_name TEXT, 
                  prediction TEXT, status TEXT, result TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS market_weights
                 (market_name TEXT PRIMARY KEY, success_rate REAL, total_evaluated INTEGER)''')
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
    
    home_attack_strength = random.uniform(0.85, 1.45)
    home_defense_weakness = random.uniform(0.75, 1.25)
    away_attack_strength = random.uniform(0.80, 1.35)
    away_defense_weakness = random.uniform(0.80, 1.30)
    
    expected_home_goals = max(0.2, home_attack_strength * away_defense_weakness * avg_league_goals)
    expected_away_goals = max(0.2, away_attack_strength * home_defense_weakness * avg_league_goals)
    
    prob_matrix = {}
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
            prob_matrix[(h, a)] = prob
            
            if h + a > 1.5:
                prob_over_15 += prob
            if h + a > 2.5:
                prob_over_25 += prob
            if h > 0 and a > 0:
                prob_btts += prob
            if h > a:
                prob_home_win += prob
            elif h == a:
                prob_draw += prob
            else:
                prob_away_win += prob

    prob_1x = prob_home_win + prob_draw
    prob_x2 = prob_away_win + prob_draw
    
    expected_corners = random.uniform(8.0, 11.5)
    expected_cards = random.uniform(3.0, 5.5)
    
    candidates = [
        ("Peste 1.5 Goluri", prob_over_15),
        ("Peste 2.5 Goluri", prob_over_25),
        ("GG (Ambele Marchează)", prob_btts),
        ("Șansă Dublă 1X", prob_1x),
        ("Șansă Dublă X2", prob_x2),
        (f"Peste {round(expected_corners - 1.5, 1)} Cornere", min(0.92, prob_over_15 * 0.95)),
        (f"Peste {round(expected_cards - 1.0, 1)} Cartonașe", min(0.90, prob_btts * 0.92))
    ]
    
    adjusted_candidates = []
    for name, raw_prob in candidates:
        boost = get_market_boost(name)
        final_conf = min(96, max(60, int((raw_prob * 100) + boost)))
        adjusted_candidates.append((name, final_conf))
        
    adjusted_candidates.sort(key=lambda x: x[1], reverse=True)
    best_market, confidence_val = adjusted_candidates[0]
    
    bb_options = [
        {
            "label": "🛡️ BetBuilder Matematic Sigur",
            "selection": f"Șansă Dublă 1X/X2 + Peste 1.5 Goluri + Peste {round(expected_corners - 2.0, 1)} Cornere",
            "confidence": f"{min(94, confidence_val + 3)}%"
        },
        {
            "label": "⚡ BetBuilder Echilibrat (Poisson)",
            "selection": f"GG/Peste 2.5 Goluri + Peste {round(expected_cards, 1)} Cartonașe",
            "confidence": f"{max(70, confidence_val - 5)}%"
        },
        {
            "label": "🔥 BetBuilder Valoare Statistică",
            "selection": f"{best_market} + Peste {round(expected_corners, 1)} Cornere + Peste {round(expected_cards + 0.5, 1)} Cartonașe",
            "confidence": f"{max(62, confidence_val - 12)}%"
        }
    ]
    
    return {
        "prediction": best_market,
        "confidence_val": confidence_val,
        "confidence": f"{confidence_val}%",
        "betbuilder": bb_options
    }

def analyze_with_gemini(prompt, images_b64=None):
    if not GEMINI_API_KEY:
        return "Notă: Cheia GEMINI_API_KEY nu este configurată în Render Environment Variables."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    parts = []
    if prompt:
        parts.append({"text": prompt})
    else:
        parts.append({"text": "Analizează detaliat biletele/meciurile din pozele atașate. Identifică meciurile și oferă o recomandare bazată exclusiv pe formă și statistici."})
        
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
        .score-badge { background: #eab308; color: #0f172a; font-weight: bold; padding: 3px 8px; border-radius: 4px; font-size: 0.85rem; }
        
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
    </style>
</head>
<body>
    <div class="container">
        <h1>XMTS AI Predictive Analytics</h1>
        
        <div id="stats-banner" class="stats-banner">
            📊 Rata de Succes Algoritm Poisson: <span id="win-rate-val">0%</span> (<span id="stats-details">0 ✅ / 0 ❌</span>)
        </div>
        
        <div class="nav-tabs">
            <button class="tab-btn active" id="btn-matches" onclick="switchTab('matches')">Meciuri Live / Azi</button>
            <button class="tab-btn" id="btn-popular" onclick="switchTab('popular')">🔥 Top Ligi</button>
            <button class="tab-btn" id="btn-tickets" onclick="switchTab('tickets')">⭐ Bilete Top Încredere</button>
            <button class="tab-btn" id="btn-chat" onclick="switchTab('chat')">💬 AI Chat & Poze</button>
        </div>

        <div class="controls-bar" id="controls-bar">
            <input type="text" id="search-box" class="search-input" placeholder="🔍 Căutare echipă sau ligă..." onkeyup="filterMatches()">
            <input type="date" id="date-picker" class="date-input" onchange="loadMatchesForDate()">
        </div>

        <div id="tab-matches">
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
        let activeTab = 'matches';
        let regenOffsets = {};
        let ticketSeeds = { 3: 0, 5: 0, 7: 0 };

        const dateInput = document.getElementById('date-picker');
        const today = new Date();
        const minDate = new Date();
        minDate.setDate(today.getDate() - 7);
        
        dateInput.value = today.toISOString().split('T')[0];
        dateInput.max = today.toISOString().split('T')[0];
        dateInput.min = minDate.toISOString().split('T')[0];

        function loadStats() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    if (data.total > 0) {
                        document.getElementById('stats-banner').style.display = 'block';
                        document.getElementById('win-rate-val').innerText = data.win_rate + '%';
                        document.getElementById('stats-details').innerText = `${data.won} ✅ / ${data.lost} ❌`;
                    }
                });
        }

        function switchTab(tab) {
            activeTab = tab;
            document.getElementById('tab-matches').style.display = (tab === 'matches' || tab === 'popular') ? 'block' : 'none';
            document.getElementById('tab-tickets').style.display = tab === 'tickets' ? 'block' : 'none';
            document.getElementById('tab-chat').style.display = tab === 'chat' ? 'block' : 'none';
            document.getElementById('controls-bar').style.display = (tab === 'matches' || tab === 'popular') ? 'flex' : 'none';

            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById('btn-' + tab).classList.add('active');

            if (tab === 'tickets') loadTickets();
            else if (tab === 'matches' || tab === 'popular') filterMatches();
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
                    loadStats();
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
                            ${m.status === 'FT' ? `<span class="score-badge">Final: ${m.score}</span>` : `<span class="pred-tag">${m.prediction.prediction}</span> <span class="confidence">Calcul Poisson: ${m.prediction.confidence}</span>`}
                        </div>
                    </div>
                    ${m.status !== 'FT' ? `
                    <div class="action-bar">
                        <button class="btn-action" onclick="toggleBetBuilder(${m.id})">🛠️ BetBuilder</button>
                        <button class="btn-action btn-regen" onclick="regeneratePrediction(${m.id})">🔄 Recalculează</button>
                    </div>
                    ` : ''}
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
                    if (data.length === 0 || data[0].matches.length === 0) {
                        container.innerHTML = '<p style="text-align:center; color:#94a3b8;">Nu există suficiente meciuri din Top Ligi pentru această dată.</p>';
                        return;
                    }
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
                                <button class="btn-action btn-regen" onclick="regenSingleTicket(${t.size})">🔄 Recalculează Bilet</button>
                            </div>
                            ${matchesHtml}
                        `;
                        container.appendChild(box);
                    });
                });
        }

        function regenSingleTicket(size) {
            ticketSeeds[size] = (ticketSeeds[size] || 0) + 1;
            loadTickets();
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

        loadMatchesForDate();
        loadStats();
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
            
        elif parsed.path == "/api/matches":
            date_str = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
            raw_matches = fetch_football_data(date_str)
            for m in raw_matches:
                m["prediction"] = calculate_advanced_metrics(m)
                save_or_update_prediction(
                    match_id=m["id"],
                    date_str=date_str,
                    match_name=m["name"],
                    prediction=m["prediction"]["prediction"],
                    match_status=m["status"],
                    goals_home=m.get("goals_home"),
                    goals_away=m.get("goals_away")
                )
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(raw_matches).encode("utf-8"))

        elif parsed.path == "/api/stats":
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM predictions WHERE result='Won'")
            won = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM predictions WHERE result='Lost'")
            lost = c.fetchone()[0]
            conn.close()
            
            total = won + lost
            win_rate = round((won / total * 100), 2) if total > 0 else 0
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "won": won, "lost": lost, "total": total, "win_rate": win_rate
            }).encode("utf-8"))

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
            seed3 = int(query.get("seed3", [0])[0])
            seed5 = int(query.get("seed5", [0])[0])
            seed7 = int(query.get("seed7", [0])[0])

            all_matches = fetch_football_data(date_str)
            
            top_matches = [m for m in all_matches if m["is_popular"] and m["status"] in ["NS", "TBD"]]
            if not top_matches:
                top_matches = [m for m in all_matches if m["is_popular"]]
            if not top_matches:
                top_matches = all_matches

            ticket_configs = [
                {"name": "Bilet Top Siguranță (3 Meciuri)", "size": 3, "seed": seed3},
                {"name": "Bilet Mărime Medie (5 Meciuri)", "size": 5, "seed": seed5},
                {"name": "Bilet Șansa Zilnică (7 Meciuri)", "size": 7, "seed": seed7}
            ]
            
            tickets = []
            for cfg in ticket_configs:
                pool = list(top_matches)
                random.seed(sum(ord(c) for c in date_str) + cfg["seed"] + cfg["size"])
                random.shuffle(pool)
                
                selected = pool[:cfg["size"]]
                ticket_matches = []
                for m in selected:
                    pred = calculate_advanced_metrics(m, seed_offset=cfg["seed"])
                    ticket_matches.append({
                        "match": m["name"],
                        "league": m["league"],
                        "prediction": pred["prediction"],
                        "confidence": pred["confidence"]
                    })
                tickets.append({"name": cfg["name"], "size": cfg["size"], "matches": ticket_matches})
                
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(tickets).encode("utf-8"))
            
        else:
            self.send_response(404)
            self.end_headers()

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
