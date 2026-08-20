import http.server
import json
import os
import random
import socketserver
import urllib.parse

PORT = int(os.environ.get("PORT", 10000))

# Listă extinsă de meciuri reale
MATCHES_LIST = [
    "Anderlecht vs Gent",
    "Bologna vs Atalanta",
    "Bodø/Glimt vs Brann",
    "Fenerbahçe vs Ferencváros",
    "Universitatea Craiova vs FCSB",
    "Lech Poznań vs Thun",
    "Fiorentina vs Rapid Viena",
    "CSKA Sofia vs Basel",
    "AEL Limassol vs Omonia",
    "St. Gallen vs Lugano",
    "Sporting CP vs Porto",
    "AZ Alkmaar vs Twente",
    "Panathinaikos vs AEK Atena",
    "Celtic vs Rangers",
    "Club Brugge vs Genk"
]

MARKETS_POOL = [
    {"name": "Peste 1.5 Goluri", "min_odd": 1.25, "max_odd": 1.45},
    {"name": "Peste 2.5 Goluri", "min_odd": 1.65, "max_odd": 2.10},
    {"name": "GG (Ambele Marchează)", "min_odd": 1.60, "max_odd": 2.05},
    {"name": "Șansă Dublă 1X", "min_odd": 1.25, "max_odd": 1.55},
    {"name": "Șansă Dublă X2", "min_odd": 1.28, "max_odd": 1.60},
    {"name": "Pauză sau Final (PsF 1)", "min_odd": 1.35, "max_odd": 1.80},
    {"name": "Pauză sau Final (PsF X)", "min_odd": 1.65, "max_odd": 1.95},
    {"name": "Peste 3.5 Cartonașe", "min_odd": 1.40, "max_odd": 1.85},
    {"name": "Peste 7.5 Cornere", "min_odd": 1.30, "max_odd": 1.60},
    {"name": "Peste 8.5 Cornere", "min_odd": 1.55, "max_odd": 1.90},
    {"name": "Peste 20.5 Faulturi", "min_odd": 1.45, "max_odd": 1.85}
]

def generate_betbuilder_combo(match_name, seed):
    random.seed(seed)
    sel1 = random.choice(["Peste 1.5 Goluri", "GG", "Peste 0.5 Goluri Pauză"])
    sel2 = random.choice(["Peste 3.5 Cartonașe", "Peste 7.5 Cornere", "Peste 20.5 Faulturi"])
    sel3 = random.choice(["Șansă Dublă 1X", "Șansă Dublă X2", "PsF 1", "PsF X"])
    
    combined_odd = round(random.uniform(2.10, 4.80), 2)
    return {
        "match": match_name,
        "selections": [sel1, sel2, sel3],
        "combined_odd": combined_odd,
        "confidence": f"{random.randint(65, 82)}%"
    }

def build_multi_ticket(target_odd):
    random.seed(int(target_odd * 100))
    available_matches = list(MATCHES_LIST)
    random.shuffle(available_matches)
    
    ticket_matches = []
    current_odd = 1.0
    
    for match_name in available_matches:
        if current_odd >= target_odd:
            break
            
        market = random.choice(MARKETS_POOL)
        m_odd = round(random.uniform(market["min_odd"], market["max_odd"]), 2)
        
        if current_odd * m_odd > target_odd * 1.2:
            m_odd = round(target_odd / current_odd, 2)
            if m_odd < 1.20:
                continue
                
        current_odd *= m_odd
        ticket_matches.append({
            "match": match_name,
            "prediction": market["name"],
            "odd": m_odd
        })
        
    return {
        "target": target_odd,
        "final_odd": round(current_odd, 2),
        "matches": ticket_matches
    }

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XMTS AI Predictions</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 12px; }
        h1 { text-align: center; color: #38bdf8; font-size: 1.5rem; margin: 10px 0 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        
        .nav-tabs { display: flex; gap: 8px; margin-bottom: 20px; }
        .tab-btn { flex: 1; background: #1e293b; color: #94a3b8; border: 1px solid #334155; padding: 12px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 0.9rem; text-align: center; }
        .tab-btn.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
        
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 14px; margin-bottom: 12px; display: flex; flex-direction: column; gap: 10px; }
        @media(min-width: 600px) { .card { flex-direction: row; justify-content: space-between; align-items: center; } }
        
        .match-title { font-weight: bold; font-size: 1.1rem; color: #f1f5f9; margin-bottom: 6px; }
        .pred-info { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
        .pred-tag { background: #0369a1; color: #e0f2fe; padding: 4px 8px; border-radius: 6px; font-size: 0.85rem; font-weight: 600; }
        .confidence { color: #22c55e; font-weight: bold; font-size: 0.85rem; }
        
        .btn-bb { background: #d97706; color: white; border: none; padding: 10px 14px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 0.85rem; text-align: center; width: 100%; }
        @media(min-width: 600px) { .btn-bb { width: auto; } }
        
        .bb-box { background: #1e293b; border: 2px dashed #f59e0b; border-radius: 12px; padding: 18px; text-align: center; margin-top: 10px; }
        .bb-list { text-align: left; background: #0f172a; padding: 12px; border-radius: 8px; margin: 15px 0; }
        .bb-list li { margin-bottom: 8px; color: #cbd5e1; font-size: 0.95rem; }
        
        .ticket-box { background: #1e293b; border-left: 4px solid #38bdf8; padding: 14px; margin-bottom: 15px; border-radius: 6px; }
        .ticket-header { display: flex; justify-content: space-between; font-weight: bold; border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 10px; font-size: 0.95rem; }
        .ticket-row { font-size: 0.88rem; margin-top: 6px; color: #cbd5e1; line-height: 1.4; }
    </style>
</head>
<body>
    <div class="container">
        <h1>XMTS AI Predictions</h1>
        
        <div class="nav-tabs">
            <button class="tab-btn active" id="btn-tab-matches" onclick="showTab('matches')">Meciuri & Pronosticuri</button>
            <button class="tab-btn" id="btn-tab-tickets" onclick="showTab('tickets')">Bilete Cotă Mare (2 - 50)</button>
        </div>

        <div id="tab-matches">
            <h2 style="text-align:center; color:#38bdf8; font-size:1.2rem;">Meciurile Zilei</h2>
            <div id="matches-list"></div>
        </div>

        <div id="tab-bb" style="display:none;">
            <button class="tab-btn" style="margin-bottom:15px;" onclick="showTab('matches')">← Înapoi la Meciuri</button>
            <div class="bb-box">
                <h2 id="bb-title" style="color:#f59e0b; font-size:1.2rem; margin:0;">BetBuilder AI</h2>
                <div class="bb-list">
                    <ul id="bb-items" style="margin:0; padding-left:20px;"></ul>
                </div>
                <p style="font-size:0.95rem;">Cotă Combinată Estimată: <strong id="bb-odd" style="color:#f59e0b;">-</strong><br>Încredere AI: <strong id="bb-conf" style="color:#22c55e;">-</strong></p>
                <button class="btn-bb" style="background:#16a34a; width:100%; margin-top:10px;" onclick="regenerateBB()">🔄 Regenerare BetBuilder</button>
            </div>
        </div>

        <div id="tab-tickets" style="display:none;">
            <h2 style="text-align:center; color:#38bdf8; font-size:1.2rem;">Bilete Multi-Cota Recalculate</h2>
            <div id="tickets-container"></div>
        </div>
    </div>

    <script>
        let currentBBSeed = 0;
        let currentBBMatch = "";

        function showTab(tab) {
            document.getElementById('tab-matches').style.display = tab === 'matches' ? 'block' : 'none';
            document.getElementById('tab-bb').style.display = tab === 'bb' ? 'block' : 'none';
            document.getElementById('tab-tickets').style.display = tab === 'tickets' ? 'block' : 'none';
            
            document.getElementById('btn-tab-matches').classList.toggle('active', tab === 'matches');
            document.getElementById('btn-tab-tickets').classList.toggle('active', tab === 'tickets');
            
            if(tab === 'tickets') loadTickets();
        }

        function loadMatches() {
            fetch('/api/matches')
                .then(r => r.json())
                .then(data => {
                    const container = document.getElementById('matches-list');
                    container.innerHTML = '';
                    
                    data.forEach((m, idx) => {
                        const card = document.createElement('div');
                        card.className = 'card';
                        card.innerHTML = `
                            <div>
                                <div class="match-title">${m.name}</div>
                                <div class="pred-info">
                                    <span class="pred-tag">${m.prediction}</span>
                                    <span class="confidence">Încredere: ${m.confidence}</span>
                                </div>
                            </div>
                            <div>
                                <button class="btn-bb" onclick="openBetBuilder('${m.name}', ${m.seed})">⚡ Generați BetBuilder</button>
                            </div>
                        `;
                        container.appendChild(card);
                    });
                });
        }

        function openBetBuilder(matchName, seed) {
            currentBBMatch = matchName;
            currentBBSeed = seed;
            document.getElementById('bb-title').innerText = "BetBuilder AI: " + matchName;
            generateBBData();
            showTab('bb');
        }

        function regenerateBB() {
            currentBBSeed += Math.floor(Math.random() * 500) + 1;
            generateBBData();
        }

        function generateBBData() {
            const list = document.getElementById('bb-items');
            list.innerHTML = 'Se calculează varianta optimă...';
            
            fetch('/api/betbuilder?match=' + encodeURIComponent(currentBBMatch) + '&seed=' + currentBBSeed)
                .then(r => r.json())
                .then(data => {
                    list.innerHTML = '';
                    data.selections.forEach(sel => {
                        const li = document.createElement('li');
                        li.innerText = '✔ ' + sel;
                        list.appendChild(li);
                    });
                    document.getElementById('bb-odd').innerText = '@' + data.combined_odd;
                    document.getElementById('bb-conf').innerText = data.confidence;
                });
        }

        function loadTickets() {
            const container = document.getElementById('tickets-container');
            container.innerHTML = '<p style="text-align:center;">Se generează biletele cu meciuri reale...</p>';
            
            fetch('/api/tickets')
                .then(r => r.json())
                .then(data => {
                    container.innerHTML = '';
                    data.forEach(t => {
                        const box = document.createElement('div');
                        box.className = 'ticket-box';
                        let matchesHtml = '';
                        t.matches.forEach(m => {
                            matchesHtml += `<div class="ticket-row">• <strong>${m.match}</strong>: <span style="color:#38bdf8;">${m.prediction}</span> (Cotă ${m.odd})</div>`;
                        });
                        
                        box.innerHTML = `
                            <div class="ticket-header">
                                <span>Bilet Țintă Cotă ${t.target}</span>
                                <span style="color:#22c55e;">Cotă Finală: @${t.final_odd}</span>
                            </div>
                            ${matchesHtml}
                        `;
                        container.appendChild(box);
                    });
                });
        }

        loadMatches();
    </script>
</body>
</html>
"""

class SimpleHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            
        elif parsed.path == "/api/matches":
            matches_data = []
            for idx, match_name in enumerate(MATCHES_LIST):
                random.seed((idx + 1) * 33)
                market = random.choice(MARKETS_POOL)
                matches_data.append({
                    "name": match_name,
                    "prediction": market["name"],
                    "confidence": f"{random.randint(72, 91)}%",
                    "seed": (idx + 1) * 105
                })
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(matches_data).encode("utf-8"))
            
        elif parsed.path == "/api/betbuilder":
            query = urllib.parse.parse_qs(parsed.query)
            match_name = query.get("match", ["Meci"])[0]
            seed = int(query.get("seed", [100])[0])
            bb_data = generate_betbuilder_combo(match_name, seed)
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(bb_data).encode("utf-8"))
            
        elif parsed.path == "/api/tickets":
            targets = [2.0, 5.0, 10.0, 15.0, 50.0]
            tickets = [build_multi_ticket(t) for t in targets]
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(tickets).encode("utf-8"))
            
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), SimpleHTTPRequestHandler) as httpd:
        print(f"Serverul XMTS rulează pe portul: {PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("Server oprit.")
