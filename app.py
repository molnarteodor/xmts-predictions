import http.server
import json
import os
import random
import socketserver
import urllib.parse
import urllib.request
from datetime import datetime

PORT = int(os.environ.get("PORT", 10000))
API_KEY = "86824b34c73a35048d8031810778337c"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

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
                    league_name = f["league"]["name"]
                    country_name = f["league"].get("country", "")
                    home = f["teams"]["home"]["name"]
                    away = f["teams"]["away"]["name"]
                    status = f["fixture"]["status"]["short"]
                    
                    goals_home = f["goals"]["home"]
                    goals_away = f["goals"]["away"]
                    score_str = f"{goals_home} - {goals_away}" if goals_home is not None else "VS"
                    
                    is_popular = check_is_popular(league_name, country_name)
                    display_league = f"{country_name}: {league_name}" if country_name else league_name
                    
                    matches.append({
                        "id": f["fixture"]["id"],
                        "name": f"{home} vs {away}",
                        "league": display_league,
                        "status": status,
                        "score": score_str,
                        "is_popular": is_popular,
                        "home_team": home,
                        "away_team": away
                    })
        except Exception as e:
            print(f"Eroare API Football: {e}")

    if not matches:
        matches = [
            {"id": 101, "name": "Real Madrid vs Barcelona", "league": "Spain: La Liga", "status": "NS", "score": "VS", "is_popular": True, "home_team": "Real Madrid", "away_team": "Barcelona"},
            {"id": 102, "name": "Manchester City vs Liverpool", "league": "England: Premier League", "status": "NS", "score": "VS", "is_popular": True, "home_team": "Manchester City", "away_team": "Liverpool"},
            {"id": 103, "name": "Nacional Potosí vs Real Tomayapo", "league": "Bolivia: Copa de la División Profesional", "status": "NS", "score": "VS", "is_popular": False, "home_team": "Nacional Potosí", "away_team": "Real Tomayapo"},
            {"id": 104, "name": "Once Caldas vs Alianza Valledupar", "league": "Colombia: Copa Colombia", "status": "NS", "score": "VS", "is_popular": False, "home_team": "Once Caldas", "away_team": "Alianza Valledupar"}
        ]
    return matches

def generate_algorithmic_prediction(match, seed_offset=0):
    if match["status"] in ["FT", "AET", "PEN"]:
        return {
            "prediction": f"Scor Final: {match['score']}", 
            "confidence_val": 0, 
            "confidence": "Finalizat",
            "betbuilder": None
        }

    hash_home = sum(ord(c) * (idx + 1) for idx, c in enumerate(match["home_team"]))
    hash_away = sum(ord(c) * (idx + 1) for idx, c in enumerate(match["away_team"]))
    match_hash = (hash_home * 31 + hash_away * 17 + match["id"] + seed_offset) % 1000

    is_high_scoring = (match_hash % 2 == 0)
    home_bias = (match_hash % 3 == 0)
    
    if is_high_scoring:
        main_pred = "Peste 2.5 Goluri" if match_hash % 4 == 0 else "GG (Ambele Marchează)"
        conf = 81 + (match_hash % 12)
    elif home_bias:
        main_pred = "Șansă Dublă 1X"
        conf = 84 + (match_hash % 10)
    else:
        main_pred = "Peste 7.5 Cornere"
        conf = 86 + (match_hash % 8)

    bb_options = [
        {
            "label": "🛡️ BetBuilder Sigur (Cotă ~1.85)",
            "selection": f"{match['home_team']} 1X + Peste 1.5 Goluri + Peste 6.5 Cornere",
            "confidence": f"{min(conf + 3, 95)}%"
        },
        {
            "label": "⚡ BetBuilder Moderat (Cotă ~2.65)",
            "selection": f"GG + Peste 2.5 Cartonașe + Peste 7.5 Cornere",
            "confidence": f"{conf - 4}%"
        }
    ]
    
    return {
        "prediction": main_pred,
        "confidence_val": conf,
        "confidence": f"{conf}%",
        "betbuilder": bb_options
    }

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XMTS VIP Portal</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b1329; color: #f8fafc; margin: 0; padding: 12px; }
        .container { max-width: 850px; margin: 0 auto; }
        
        .header-bar { display: flex; justify-content: space-between; align-items: center; background: #131d38; padding: 12px 16px; border-radius: 10px; border: 1px solid #1e2d54; margin-bottom: 12px; }
        .brand { font-size: 1.3rem; font-weight: bold; color: #38bdf8; }
        .user-badge { background: #0284c7; color: #fff; padding: 4px 10px; border-radius: 6px; font-size: 0.8rem; font-weight: bold; }

        .controls-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
        .search-input, .date-input { background: #131d38; color: #fff; border: 1px solid #1e2d54; padding: 10px; border-radius: 8px; font-size: 0.88rem; }
        .search-input { flex: 2; min-width: 180px; }
        .date-input { flex: 1; min-width: 120px; }

        .nav-tabs { display: flex; gap: 6px; margin-bottom: 12px; overflow-x: auto; }
        .tab-btn { flex: 1; min-width: 100px; background: #131d38; color: #94a3b8; border: 1px solid #1e2d54; padding: 10px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 0.82rem; text-align: center; white-space: nowrap; }
        .tab-btn.active { background: #0284c7; color: #fff; border-color: #38bdf8; }

        .card { background: #131d38; border: 1px solid #1e2d54; border-radius: 10px; padding: 14px; margin-bottom: 10px; }
        .match-league { font-size: 0.78rem; color: #38bdf8; margin-bottom: 4px; }
        .match-title { font-weight: bold; font-size: 1.05rem; }
        .pred-tag { background: #0369a1; color: #e0f2fe; padding: 4px 8px; border-radius: 6px; font-size: 0.85rem; font-weight: bold; display: inline-block; margin-top: 6px; }
        .confidence { color: #22c55e; font-weight: bold; font-size: 0.85rem; margin-left: 6px; }

        .bb-box { background: #0b1329; border: 1px dashed #0284c7; border-radius: 8px; padding: 10px; margin-top: 10px; }
        .bb-item { font-size: 0.82rem; margin-bottom: 4px; color: #cbd5e1; }
        .bb-label { color: #eab308; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header-bar">
            <div class="brand">XMTS PREDICTIONS</div>
            <div class="user-badge">⚡ Acces Gratuit</div>
        </div>

        <div class="controls-bar">
            <input type="text" id="search-box" class="search-input" placeholder="🔍 Căutare echipă sau ligă..." onkeyup="filterMatches()">
            <input type="date" id="date-picker" class="date-input" onchange="loadMatchesForDate()">
        </div>

        <div class="nav-tabs">
            <button class="tab-btn active" id="btn-matches" onclick="switchTab('matches')">Meciuri</button>
            <button class="tab-btn" id="btn-popular" onclick="switchTab('popular')">🔥 Top Ligi</button>
            <button class="tab-btn" id="btn-tickets" onclick="switchTab('tickets')">⭐ Bilete Top</button>
        </div>

        <div id="tab-matches">
            <div id="matches-list"></div>
        </div>

        <div id="tab-tickets" style="display:none;">
            <div id="tickets-list"></div>
        </div>
    </div>

    <script>
        let allMatches = [];
        let activeTab = 'matches';

        const dateInput = document.getElementById('date-picker');
        dateInput.value = new Date().toISOString().split('T')[0];

        function switchTab(tab) {
            activeTab = tab;
            document.getElementById('tab-matches').style.display = (tab === 'matches' || tab === 'popular') ? 'block' : 'none';
            document.getElementById('tab-tickets').style.display = tab === 'tickets' ? 'block' : 'none';

            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById('btn-' + tab).classList.add('active');

            if (tab === 'tickets') loadTickets();
            else filterMatches();
        }

        function loadMatchesForDate() {
            const container = document.getElementById('matches-list');
            container.innerHTML = '<p style="text-align:center;">Se încarcă meciurile...</p>';

            fetch('/api/matches?date=' + dateInput.value)
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
                const matchSearch = m.name.toLowerCase().includes(query) || m.league.toLowerCase().includes(query);
                if (activeTab === 'popular') return matchSearch && m.is_popular;
                return matchSearch;
            });

            if (filtered.length === 0) {
                container.innerHTML = '<p style="text-align:center; color:#94a3b8;">Niciun meci găsit.</p>';
                return;
            }

            filtered.forEach(m => {
                const card = document.createElement('div');
                card.className = 'card';
                
                let bbHtml = '';
                if (m.prediction.betbuilder) {
                    bbHtml = '<div class="bb-box">';
                    m.prediction.betbuilder.forEach(bb => {
                        bbHtml += `<div class="bb-item"><span class="bb-label">${bb.label}</span>: ${bb.selection} <span style="color:#22c55e;">(${bb.confidence})</span></div>`;
                    });
                    bbHtml += '</div>';
                }

                card.innerHTML = `
                    <div class="match-league">${m.league} ${m.is_popular ? '<span style="color:#eab308;">🔥 Top Liga</span>' : ''}</div>
                    <div class="match-title">${m.name}</div>
                    <div>
                        <span class="pred-tag">${m.prediction.prediction}</span>
                        <span class="confidence">Încredere: ${m.prediction.confidence}</span>
                    </div>
                    ${bbHtml}
                `;
                container.appendChild(card);
            });
        }

        function loadTickets() {
            const container = document.getElementById('tickets-list');
            container.innerHTML = '<p style="text-align:center;">Se generează biletele...</p>';

            fetch('/api/tickets?date=' + dateInput.value)
                .then(r => r.json())
                .then(tickets => {
                    container.innerHTML = '';
                    tickets.forEach(t => {
                        const box = document.createElement('div');
                        box.className = 'card';
                        box.style.borderLeft = '4px solid #0284c7';
                        
                        let matchesListHtml = '';
                        t.matches.forEach(m => {
                            matchesListHtml += `<div style="font-size:0.85rem; margin-top:4px;">• <strong>${m.match}</strong>: <span style="color:#38bdf8;">${m.prediction}</span> (${m.confidence})</div>`;
                        });

                        box.innerHTML = `
                            <div style="font-weight:bold; color:#eab308; margin-bottom:6px;">🎯 ${t.name}</div>
                            ${matchesListHtml}
                        `;
                        container.appendChild(box);
                    });
                });
        }

        loadMatchesForDate();
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
                m["prediction"] = generate_algorithmic_prediction(m)
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(raw_matches).encode("utf-8"))

        elif parsed.path == "/api/tickets":
            date_str = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
            all_matches = fetch_football_data(date_str)
            top_matches = [m for m in all_matches if m["is_popular"]] or all_matches

            tickets = [
                {"name": "Bilet Safe (Cotă 2+)", "size": 2},
                {"name": "Bilet Cota 5+", "size": 4}
            ]

            res_tickets = []
            for t in tickets:
                selected = top_matches[:t["size"]]
                t_matches = []
                for m in selected:
                    pred = generate_algorithmic_prediction(m)
                    t_matches.append({
                        "match": m["name"],
                        "prediction": pred["prediction"],
                        "confidence": pred["confidence"]
                    })
                res_tickets.append({"name": t["name"], "matches": t_matches})

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res_tickets).encode("utf-8"))

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), SimpleHTTPRequestHandler) as httpd:
        print(f"Server XMTS activ pe portul: {PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Server oprit.")
