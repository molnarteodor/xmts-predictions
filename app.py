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
            {"id": 103, "name": "Inter vs AC Milan", "league": "Italy: Serie A", "status": "NS", "score": "VS", "is_popular": True, "home_team": "Inter", "away_team": "AC Milan"},
            {"id": 104, "name": "Universitatea Craiova vs FCSB", "league": "Romania: SuperLiga", "status": "NS", "score": "VS", "is_popular": True, "home_team": "Universitatea Craiova", "away_team": "FCSB"},
            {"id": 105, "name": "Arsenal vs Chelsea", "league": "England: Premier League", "status": "NS", "score": "VS", "is_popular": True, "home_team": "Arsenal", "away_team": "Chelsea"}
        ]
    return matches

def generate_algorithmic_prediction(match, seed_offset=0):
    seed = sum(ord(c) for c in match["name"]) + match["id"] + seed_offset
    random.seed(seed)
    
    if match["status"] in ["FT", "AET", "PEN"]:
        return {
            "prediction": f"Rezultat Final: {match['score']}", 
            "confidence_val": 0, 
            "confidence": "Finalizat",
            "betbuilder": None
        }

    markets = [
        {"name": "Peste 1.5 Goluri", "weight": 94},
        {"name": "Peste 7.5 Cornere", "weight": 89},
        {"name": "Peste 2.5 Cartonașe", "weight": 91},
        {"name": "GG (Ambele Marchează)", "weight": 83},
        {"name": "Șansă Dublă 1X (Gazdele nu pierd)", "weight": 88},
        {"name": "Șansă Dublă X2 (Oaspeții nu pierd)", "weight": 88},
        {"name": "Pauză sau Final 1 (PsF 1)", "weight": 85},
        {"name": "Pauză sau Final 2 (PsF 2)", "weight": 85}
    ]
    
    selected = random.choice(markets)
    calculated_confidence = selected["weight"] + random.randint(-2, 3)
    
    # Generare opțiuni BetBuilder
    bb_options = [
        {
            "label": "🛡️ BetBuilder Sigur (Cotă ~1.85)",
            "selection": f"Șansă Dublă 1X + Peste 1.5 Goluri + Peste 6.5 Cornere",
            "confidence": "89%"
        },
        {
            "label": "⚡ BetBuilder Moderat (Cotă ~2.60)",
            "selection": f"GG (Ambele marchează) + Peste 2.5 Cartonașe + Peste 7.5 Cornere",
            "confidence": "82%"
        },
        {
            "label": "🔥 BetBuilder Cotă Mare (Cotă ~4.20)",
            "selection": f"Pauză sau Final 1 + Peste 2.5 Goluri + Peste 8.5 Cornere",
            "confidence": "74%"
        }
    ]
    
    return {
        "prediction": selected["name"],
        "confidence_val": calculated_confidence,
        "confidence": f"{calculated_confidence}%",
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
        parts.append({"text": "Analizează detaliat biletele/meciurile din pozele atașate. Identifică meciurile și oferă o recomandare de pariu bazată pe statistici."})
        
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
    <title>XMTS AI Predictions & BetBuilder</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 12px; }
        h1 { text-align: center; color: #38bdf8; font-size: 1.5rem; margin: 10px 0 15px; }
        .container { max-width: 850px; margin: 0 auto; }
        
        .nav-tabs { display: flex; gap: 6px; margin-bottom: 15px; overflow-x: auto; padding-bottom: 5px; }
        .tab-btn { flex: 1; min-width: 110px; background: #1e293b; color: #94a3b8; border: 1px solid #334155; padding: 10px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 0.82rem; text-align: center; white-space: nowrap; }
        .tab-btn.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
        
        .controls-bar { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 15px; background: #1e293b; padding: 12px; border-radius: 8px; border: 1px solid #334155; }
        .search-input, .date-input { background: #0f172a; color: #fff; border: 1px solid #475569; padding: 8px 12px; border-radius: 6px; font-size: 0.9rem; }
        .search-input { flex: 2; min-width: 180px; }
        .date-input { flex: 1; min-width: 130px; }
        
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 14px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 10px; }
        .card-header { display: flex; justify-content: space-between; align-items: flex-start; }
        
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
        .chat-img-preview { max-width: 100px; max-height: 100px; border-radius: 6px; border: 1px solid #38bdf8; }
        .chat-input-area { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
        
        .ticket-box { background: #1e293b; border-left: 4px solid #22c55e; padding: 14px; margin-bottom: 12px; border-radius: 6px; }
        .ticket-header { display: flex; justify-content: space-between; font-weight: bold; border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>XMTS AI Predictions & BetBuilder</h1>
        
        <div class="nav-tabs">
            <button class="tab-btn active" id="btn-matches" onclick="switchTab('matches')">Meciuri Superbet</button>
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
            <h2 style="text-align:center; color:#38bdf8; font-size:1.1rem;">Bilete Generat Automat Din Cele Mai Sigure Meciuri</h2>
            <div id="tickets-list"></div>
        </div>

        <div id="tab-chat" style="display:none;">
            <div class="chat-box" id="chat-messages">
                <div class="chat-msg chat-ai">Salut! Trimite-mi imagini sau poze cu meciuri și bilete pentru a le analiza automat.</div>
            </div>
            <div class="chat-input-area">
                <div style="display:flex; gap:8px;">
                    <input type="file" id="img-input" accept="image/*" multiple style="display:none;" onchange="updateFileNames()">
                    <button class="btn-action" style="background:#475569;" onclick="document.getElementById('img-input').click()">📷 Poze</button>
                    <input type="text" id="chat-text" class="search-input" style="flex:1;" placeholder="Scrie un mesaj..." onkeypress="if(event.key==='Enter') sendChatMessage()">
                    <button class="btn-action" style="background:#16a34a; color:white;" onclick="sendChatMessage()">Trimite</button>
                </div>
                <div id="file-names" style="font-size:0.8rem; color:#38bdf8;"></div>
            </div>
        </div>
    </div>

    <script>
        let allMatches = [];
        let activeTab = 'matches';
        let regenOffsets = {};

        const dateInput = document.getElementById('date-picker');
        const today = new Date();
        const minDate = new Date();
        minDate.setDate(today.getDate() - 7);
        
        dateInput.value = today.toISOString().split('T')[0];
        dateInput.max = today.toISOString().split('T')[0];
        dateInput.min = minDate.toISOString().split('T')[0];

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
            container.innerHTML = '<p style="text-align:center;">Se încarcă meciurile...</p>';

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
                        <div style="margin-top:6px;" id="pred-area-${m.id}">
                            ${m.status === 'FT' ? `<span class="score-badge">Final: ${m.score}</span>` : `<span class="pred-tag">${m.prediction.prediction}</span> <span class="confidence">Încredere: ${m.prediction.confidence}</span>`}
                        </div>
                    </div>
                    ${m.status !== 'FT' ? `
                    <div class="action-bar">
                        <button class="btn-action" onclick="toggleBetBuilder(${m.id})">🛠️ BetBuilder</button>
                        <button class="btn-action btn-regen" onclick="regeneratePrediction(${m.id})">🔄 Regenerază</button>
                    </div>
                    ` : ''}
                    ${bbHtml}
                `;
                container.appendChild(card);
            });
        }

        function toggleBetBuilder(matchId) {
            const box = document.getElementById('bb-box-' + matchId);
            if (box) {
                box.style.display = box.style.display === 'block' ? 'none' : 'block';
            }
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

        function loadTickets() {
            const container = document.getElementById('tickets-list');
            container.innerHTML = '<p style="text-align:center;">Se generează biletele...</p>';

            fetch('/api/tickets?date=' + dateInput.value)
                .then(r => r.json())
                .then(data => {
                    container.innerHTML = '';
                    if (data.length === 0 || data[0].matches.length === 0) {
                        container.innerHTML = '<p style="text-align:center; color:#94a3b8;">Nu există meciuri disponibile.</p>';
                        return;
                    }
                    data.forEach(t => {
                        const box = document.createElement('div');
                        box.className = 'ticket-box';
                        let matchesHtml = '';
                        t.matches.forEach(m => {
                            matchesHtml += `<div style="font-size:0.88rem; margin-top:4px; color:#cbd5e1;">• <strong>${m.match}</strong> (${m.league}): <span style="color:#38bdf8;">${m.prediction}</span> - <span style="color:#22c55e; font-weight:bold;">Încredere: ${m.confidence}</span></div>`;
                        });
                        box.innerHTML = `
                            <div class="ticket-header">
                                <span>${t.name}</span>
                                <span style="color:#22c55e;">Selecție: ${t.matches.length} Meciuri</span>
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

        elif parsed.path == "/api/regenerate":
            match_id = int(query.get("match_id", [0])[0])
            offset = int(query.get("offset", [1])[0])
            date_str = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
            
            raw_matches = fetch_football_data(date_str)
            target = next((m for m in raw_matches if m["id"] == match_id), None)
            
            if target:
                new_pred = generate_algorithmic_prediction(target, seed_offset=offset)
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
            upcoming = [m for m in all_matches if m["status"] in ["NS", "TBD"]]
            if not upcoming:
                upcoming = all_matches
            
            for m in upcoming:
                m["prediction"] = generate_algorithmic_prediction(m)
                
            top_trusted = sorted(upcoming, key=lambda x: x["prediction"]["confidence_val"], reverse=True)
            ticket_types = [
                {"name": "Bilet Top Siguranță (3 Meciuri)", "size": 3},
                {"name": "Bilet Mărime Medie (5 Meciuri)", "size": 5},
                {"name": "Bilet Ansa Zilnică (7 Meciuri)", "size": 7}
            ]
            
            tickets = []
            for tt in ticket_types:
                selected_matches = top_trusted[:tt["size"]]
                ticket_matches = [{
                    "match": m["name"],
                    "league": m["league"],
                    "prediction": m["prediction"]["prediction"],
                    "confidence": m["prediction"]["confidence"]
                } for m in selected_matches]
                tickets.append({"name": tt["name"], "matches": ticket_matches})
                
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
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), SimpleHTTPRequestHandler) as httpd:
        print(f"Server XMTS activ pe portul: {PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Server oprit.")
