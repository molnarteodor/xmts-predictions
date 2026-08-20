import http.server
import json
import os
import random
import socketserver
import urllib.parse
import urllib.request

# Port alocat dinamic pentru Render
PORT = int(os.environ.get("PORT", 10000))

# Mpiețe extinse și variate (minimum cota 1.20)
MARKETS_POOL = [
    {"type": "Goluri", "name": "Peste 1.5 Goluri", "min_odd": 1.22, "max_odd": 1.45},
    {"type": "Goluri", "name": "Peste 2.5 Goluri", "min_odd": 1.65, "max_odd": 2.10},
    {"type": "Goluri", "name": "GG (Ambele Marchează)", "min_odd": 1.60, "max_odd": 2.05},
    {"type": "Rezultat", "name": "Șansă Dublă 1X", "min_odd": 1.25, "max_odd": 1.55},
    {"type": "Rezultat", "name": "Șansă Dublă X2", "min_odd": 1.28, "max_odd": 1.60},
    {"type": "Rezultat", "name": "Pauză sau Final (PsF 1)", "min_odd": 1.35, "max_odd": 1.80},
    {"type": "Rezultat", "name": "Pauză sau Final (PsF X)", "min_odd": 1.65, "max_odd": 1.95},
    {"type": "Cartonașe", "name": "Peste 3.5 Cartonașe", "min_odd": 1.40, "max_odd": 1.85},
    {"type": "Cartonașe", "name": "Peste 4.5 Cartonașe", "min_odd": 1.80, "max_odd": 2.30},
    {"type": "Cornere", "name": "Peste 7.5 Cornere", "min_odd": 1.30, "max_odd": 1.60},
    {"type": "Cornere", "name": "Peste 8.5 Cornere", "min_odd": 1.55, "max_odd": 1.90},
    {"type": "Faulturi", "name": "Peste 21.5 Faulturi", "min_odd": 1.45, "max_odd": 1.85}
]

def generate_safe_prediction(match_seed):
    random.seed(match_seed)
    market = random.choice(MARKETS_POOL)
    odd = round(random.uniform(market["min_odd"], market["max_odd"]), 2)
    confidence = random.randint(72, 91)
    return {
        "prediction": market["name"],
        "confidence": f"{confidence}%",
        "type": market["type"],
        "odd": odd
    }

def generate_betbuilder_combo(match_seed):
    random.seed(match_seed + random.randint(1, 9999))
    sel1 = random.choice(["Peste 1.5 Goluri", "GG", "Peste 0.5 Goluri Pauză"])
    sel2 = random.choice(["Peste 3.5 Cartonașe", "Peste 7.5 Cornere", "Peste 20.5 Faulturi"])
    sel3 = random.choice(["Șansă Dublă 1X", "Șansă Dublă X2", "PsF 1", "PsF X"])
    
    combined_odd = round(random.uniform(2.10, 4.80), 2)
    
    return {
        "selections": [sel1, sel2, sel3],
        "combined_odd": combined_odd,
        "confidence": f"{random.randint(60, 78)}%"
    }

def build_multi_ticket(target_odd):
    # Logică de selectare și multiplicare reală a cotelor până la atingerea țintei (2, 5, 10, 15, 50)
    ticket_matches = []
    current_odd = 1.0
    counter = 1
    
    while current_odd < target_odd and len(ticket_matches) < 12:
        m_odd = round(random.uniform(1.30, 1.85), 2)
        m_type = random.choice(["Peste 1.5 Goluri", "PsF 1", "1X", "Peste 8.5 Cornere", "Peste 3.5 Cartonașe"])
        
        if current_odd * m_odd > target_odd * 1.25:
            m_odd = round(target_odd / current_odd, 2)
            if m_odd < 1.20:
                break
        
        current_odd *= m_odd
        ticket_matches.append({
            "match": f"Meciul #{counter}",
            "prediction": m_type,
            "odd": m_odd
        })
        counter += 1
        
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
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 15px; }
        h1, h2 { text-align: center; color: #38bdf8; }
        .container { max-width: 900px; margin: 0 auto; }
        .nav-tabs { display: flex; gap: 10px; margin-bottom: 20px; justify-content: center; }
        .tab-btn { background: #1e293b; color: #94a3b8; border: 1px solid #334155; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-weight: bold; }
        .tab-btn.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
        
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 15px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
        .match-title { font-weight: bold; font-size: 1.05em; color: #f1f5f9; }
        .pred-tag { background: #0369a1; color: #e0f2fe; padding: 5px 10px; border-radius: 6px; font-size: 0.9em; display: inline-block; margin-top: 4px; }
        .confidence { color: #22c55e; font-weight: bold; }
        .btn-bb { background: #d97706; color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; text-decoration: none; font-weight: bold; font-size: 0.85em; }
        .btn-bb:hover { background: #b45309; }
        
        .bb-box { background: #1e293b; border: 2px dashed #f59e0b; border-radius: 12px; padding: 20px; text-align: center; margin-top: 20px; }
        .bb-list { text-align: left; background: #0f172a; padding: 15px; border-radius: 8px; margin: 15px 0; }
        .bb-list li { margin-bottom: 8px; color: #cbd5e1; }
        .btn-regen { background: #16a34a; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: bold; }
        
        .ticket-box { background: #1e293b; border-left: 4px solid #38bdf8; padding: 15px; margin-bottom: 15px; border-radius: 6px; }
        .ticket-header { display: flex; justify-content: space-between; font-weight: bold; border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>XMTS AI Predictions</h1>
        
        <div class="nav-tabs">
            <button class="tab-btn active" onclick="showTab('matches')">Meciuri & Pronosticuri</button>
            <button class="tab-btn" onclick="showTab('tickets')">Bilete Cotă Mare (2 - 50)</button>
        </div>

        <!-- SECTIUNE MECIURI -->
        <div id="tab-matches">
            <h2>Meciurile Zilei</h2>
            <div id="matches-list"></div>
        </div>

        <!-- SECTIUNE BETBUILDER SEPARAT -->
        <div id="tab-bb" style="display:none;">
            <button class="tab-btn" onclick="showTab('matches')">← Înapoi la Meciuri</button>
            <div class="bb-box">
                <h2 id="bb-title">BetBuilder AI</h2>
                <div class="bb-list">
                    <ul id="bb-items"></ul>
                </div>
                <p>Cotă Combinată Estimată: <strong id="bb-odd" style="color:#f59e0b;">-</strong> | Încredere: <strong id="bb-conf" style="color:#22c55e;">-</strong></p>
                <button class="btn-regen" onclick="regenerateBB()">🔄 Regenerare BetBuilder</button>
            </div>
        </div>

        <!-- SECTIUNE BILETE COTA MARE -->
        <div id="tab-tickets" style="display:none;">
            <h2>Bilete Multi-Cota Recalculate</h2>
            <div id="tickets-container"></div>
        </div>
    </div>

    <script>
        const sampleMatches = [
            "Anderlecht vs Gent", "Bologna vs Atalanta", "Bodø/Glimt vs Brann",
            "Fenerbahçe vs Ferencváros", "Universitatea Craiova vs FCSB",
            "Lech Poznań vs Thun", "Fiorentina vs Rapid Viena", "CSKA Sofia vs Basel",
            "AEL Limassol vs Omonia", "St. Gallen vs Lugano"
        ];

        let currentBBSeed = 0;
        let currentBBMatch = "";

        function showTab(tab) {
            document.getElementById('tab-matches').style.styleDisplay = 'none';
            document.getElementById('tab-matches').style.display = tab === 'matches' ? 'block' : 'none';
            document.getElementById('tab-bb').style.display = tab === 'bb' ? 'block' : 'none';
            document.getElementById('tab-tickets').style.display = tab === 'tickets' ? 'block' : 'none';
            
            if(tab === 'tickets') loadTickets();
        }

        function loadMatches() {
            const container = document.getElementById('matches-list');
            container.innerHTML = '';
            
            sampleMatches.forEach((m, idx) => {
                // Simulăm calculul prin seed-ul meciului
                const seed = (idx + 1) * 105;
                const types = [
                    { name: "Peste 8.5 Cornere", conf: "84%" },
                    { name: "PsF 1", conf: "76%" },
                    { name: "Peste 3.5 Cartonașe", conf: "81%" },
                    { name: "Șansă Dublă 1X", conf: "88%" },
                    { name: "Peste 1.5 Goluri", conf: "89%" },
                    { name: "Peste 20.5 Faulturi", conf: "79%" }
                ];
                const pred = types[idx % types.length];

                const card = document.createElement('div');
                card.className = 'card';
                card.innerHTML = `
                    <div>
                        <div class="match-title">${m}</div>
                        <span class="pred-tag">${pred.name}</span>
                        <span class="confidence"> | Încredere: ${pred.conf}</span>
                    </div>
                    <div>
                        <button class="btn-bb" onclick="openBetBuilder('${m}', ${seed})">⚡ Generați BetBuilder</button>
                    </div>
                `;
                container.appendChild(card);
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
            list.innerHTML = 'Încărcare selecții AI...';
            
            fetch('/api/betbuilder?seed=' + currentBBSeed)
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
            container.innerHTML = 'Generare bilete cota 2, 5, 10, 15, 50...';
            
            fetch('/api/tickets')
                .then(r => r.json())
                .then(data => {
                    container.innerHTML = '';
                    data.forEach(t => {
                        const box = document.createElement('div');
                        box.className = 'ticket-box';
                        let matchesHtml = '';
                        t.matches.forEach(m => {
                            matchesHtml += `<div style="font-size:0.9em; margin-top:4px; color:#94a3b8;">• ${m.match}: <strong>${m.prediction}</strong> (Cotă ${m.odd})</div>`;
                        });
                        
                        box.innerHTML = `
                            <div class="ticket-header">
                                <span>Bilet Țintă Cotă ${t.target}</span>
                                <span style="color:#38bdf8;">Cotă Finală Obținută: @${t.final_odd}</span>
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
            
        elif parsed.path == "/api/betbuilder":
            query = urllib.parse.parse_qs(parsed.query)
            seed = int(query.get("seed", [100])[0])
            bb_data = generate_betbuilder_combo(seed)
            
            self.send_response(200)
            self.send_header("Content-type", "json/application")
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
