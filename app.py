import os
import json
from datetime import datetime
import requests
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
CORS(app)

# Cheia ta API integrată direct
API_TOKEN = os.getenv("API_TOKEN", "86824b34c73a35048d8031810778337c")
CACHE_FILE = "matches_cache.json"

def fetch_and_cache_matches():
    """Descarcă meciurile zilei o singură dată și le salvează local."""
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[{datetime.now()}] Se descarcă meciurile pentru {today}...")
    
    url = "https://api.football-data.org/v4/matches"
    headers = {"X-Auth-Token": API_TOKEN}
    params = {"dateFrom": today, "dateTo": today}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            matches = response.json().get("matches", [])
            data_to_save = {"date": today, "matches": matches}
            
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            print(f"[SUCCESS] S-au salvat {len(matches)} meciuri în cache.")
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
    """Endpoint API pentru preluare meciuri."""
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

# Template-ul HTML/CSS/JS integrat direct
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XMTS AI Predictive Analytics</title>
    <style>
        body {
            background-color: #0b132b;
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
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
            font-weight: bold;
            color: #38bdf8;
            margin-bottom: 20px;
        }
        .empty-state {
            background-color: #1c2541;
            border-radius: 12px;
            padding: 40px 20px;
            text-align: center;
            border: 1px solid #2a385b;
            margin-top: 20px;
        }
        .empty-state p {
            color: #8c9ba5;
            font-size: 15px;
            margin: 0;
        }
        .match-card {
            background-color: #1c2541;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 12px;
            border: 1px solid #2a385b;
        }
        .league-title {
            font-size: 12px;
            color: #38bdf8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .teams {
            font-size: 16px;
            font-weight: 600;
            margin: 8px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">XMTS AI Predictive Analytics</div>
        <div id="matches-list">Se încarcă meciurile...</div>
    </div>

    <script>
        async function loadMatches() {
            const container = document.getElementById('matches-list');
            try {
                const response = await fetch('/api/predictions');
                const data = await response.json();
                
                if (!data.matches || data.matches.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <p>Nu s-au găsit meciuri pentru filtrul selectat.</p>
                        </div>
                    `;
                    return;
                }

                container.innerHTML = data.matches.map(m => `
                    <div class="match-card">
                        <div class="league-title">\${m.competition ? m.competition.name : 'Fotbal'}</div>
                        <div class="teams">\${m.homeTeam.name} vs \${m.awayTeam.name}</div>
                    </div>
                `).join('');
            } catch (err) {
                container.innerHTML = `
                    <div class="empty-state">
                        <p>Eroare la încărcarea datelor.</p>
                    </div>
                `;
            }
        }

        loadMatches();
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
