import os
import json
from datetime import datetime
import requests
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
CORS(app)

# Cheia ta API-Sports / API-Football
API_TOKEN = os.getenv("API_TOKEN", "86824b34c73a35048d8031810778337c")
CACHE_FILE = "matches_cache.json"

def fetch_and_cache_matches():
    """Preluare meciuri folosind corect API-Football (v3.football.api-sports.io)."""
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[{datetime.now()}] Se descarcă meciurile pentru {today}...")
    
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {
        "x-apisports-key": API_TOKEN,
        "x-rapidapi-host": "v3.football.api-sports.io"
    }
    params = {"date": today}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            res_json = response.json()
            fixtures = res_json.get("response", [])
            data_to_save = {"date": today, "matches": fixtures}
            
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            print(f"[SUCCESS] S-au salvat {len(fixtures)} meciuri în cache.")
        else:
            print(f"[ERROR API] Status code: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Nu s-au putut prelua meciurile: {e}")

# Scheduler: Rulează o singură dată pe zi la ora 00:05 AM
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(fetch_and_cache_matches, 'cron', hour=0, minute=5)
scheduler.start()

@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    today = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(CACHE_FILE):
        return jsonify({"date": today, "matches": []})
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
        if cache_data.get("date") != today:
            return jsonify({"date": today, "matches": []})
        return jsonify(cache_data)
    except Exception:
        return jsonify({"date": today, "matches": []})

# Interfața vizuală completă XMTS AI Predictive Analytics
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XMTS AI Predictive Analytics</title>
    <style>
        body {
            background-color: #080e1e;
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 15px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            width: 100%;
            max-width: 480px;
        }
        .header {
            text-align: center;
            font-size: 20px;
            font-weight: 800;
            color: #38bdf8;
            margin: 15px 0 20px 0;
        }
        .nav-tabs {
            display: flex;
            gap: 8px;
            overflow-x: auto;
            padding-bottom: 15px;
            scrollbar-width: none;
        }
        .nav-tabs::-webkit-scrollbar {
            display: none;
        }
        .tab-btn {
            background-color: #111a2e;
            color: #94a3b8;
            border: 1px solid #1e293b;
            padding: 10px 14px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            white-space: nowrap;
            cursor: pointer;
        }
        .tab-btn.active {
            background-color: #0284c7;
            color: #ffffff;
            border-color: #38bdf8;
        }
        .card {
            background-color: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .card-gold {
            border: 1px solid #eab308;
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        .tag {
            background-color: #eab308;
            color: #000000;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 700;
        }
        .target-odd {
            color: #eab308;
            font-size: 14px;
            font-weight: 700;
        }
        .league-name {
            color: #38bdf8;
            font-size: 12px;
            margin-bottom: 4px;
        }
        .match-title {
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 10px;
        }
        .prediction-badge {
            background-color: #0284c7;
            color: #ffffff;
            padding: 6px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            display: inline-block;
        }
        .history-title {
            font-size: 16px;
            font-weight: 700;
            margin: 20px 0 10px 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .empty-state {
            text-align: center;
            padding: 30px 15px;
            color: #64748b;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">XMTS AI Predictive Analytics</div>
        
        <!-- Navigation Tabs -->
        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchTab('challenge')">🏆 Challenge 1.5</button>
            <button class="tab-btn" onclick="switchTab('live')">Meciuri Live / Azi</button>
            <button class="tab-btn" onclick="switchTab('top')">🔥 Top Ligi</button>
            <button class="tab-btn" onclick="switchTab('bilete')">⭐ Bilete</button>
        </div>

        <!-- Main Content Area -->
        <div id="tab-content">
            <div class="empty-state">Se încarcă datele...</div>
        </div>
    </div>

    <script>
        let cachedMatches = [];

        async function init() {
            try {
                const response = await fetch('/api/predictions');
                const data = await response.json();
                cachedMatches = data.matches || [];
                switchTab('challenge');
            } catch (err) {
                document.getElementById('tab-content').innerHTML = `
                    <div class="card empty-state">Eroare la conectarea cu serverul.</div>
                `;
            }
        }

        function switchTab(tabName) {
            const buttons = document.querySelectorAll('.tab-btn');
            buttons.forEach(btn => btn.classList.remove('active'));

            const content = document.getElementById('tab-content');

            if (tabName === 'challenge') {
                buttons[0].classList.add('active');
                
                if (cachedMatches.length === 0) {
                    content.innerHTML = `
                        <div class="card empty-state">
                            Nu s-au găsit meciuri valide pentru Challenge astăzi.
                        </div>
                        <div class="history-title">📜 Istoric Challenge Pe Zile</div>
                        <div class="card empty-state">Nu există istoric înregistrat pentru ziua curentă.</div>
                    `;
                } else {
                    const topMatch = cachedMatches[0];
                    content.innerHTML = `
                        <div class="card card-gold">
                            <div class="card-header">
                                <span class="tag">🎯 Ziua 1 (${new Date().toISOString().split('T')[0]})</span>
                                <span class="target-odd">Cotă Totală Target: ~1.55</span>
                            </div>
                            <div class="league-name">${topMatch.league.country}: ${topMatch.league.name}</div>
                            <div class="match-title">${topMatch.teams.home.name} vs ${topMatch.teams.away.name}</div>
                            <div class="prediction-badge">BetBuilder: 1X + Peste 1.5 Goluri</div>
                        </div>
                        
                        <div class="history-title">📜 Istoric Challenge Pe Zile</div>
                        <div class="card">
                            <div style="font-weight: 700; margin-bottom: 5px;">Ziua 1 (${new Date().toISOString().split('T')[0]}) ⏳ ÎN DESFĂȘURARE (Cotă 1.55)</div>
                            <div style="font-size: 13px; color: #94a3b8;">• ${topMatch.teams.home.name} vs ${topMatch.teams.away.name}: BetBuilder: 1X + Peste 1.5 Goluri</div>
                        </div>
                    `;
                }
            } else if (tabName === 'live') {
                buttons[1].classList.add('active');
                if (cachedMatches.length === 0) {
                    content.innerHTML = `<div class="card empty-state">Nu s-au găsit meciuri pentru azi.</div>`;
                } else {
                    content.innerHTML = cachedMatches.map(m => `
                        <div class="card">
                            <div class="league-name">${m.league.name}</div>
                            <div class="match-title">${m.teams.home.name} vs ${m.teams.away.name}</div>
                        </div>
                    `).join('');
                }
            } else {
                event.target.classList.add('active');
                content.innerHTML = `<div class="card empty-state">Secțiune în curs de actualizare.</div>`;
            }
        }

        init();
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    if not os.path.exists(CACHE_FILE):
        fetch_and_cache_matches()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
