import os
import json
import math
from datetime import datetime
import requests
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
CORS(app)

# Cheia se ia strict din variabila de mediu setată în Render (sau fallback pentru test local)
API_TOKEN = os.getenv("API_TOKEN", "")
CACHE_FILE = "matches_cache.json"

# --- ALGORITM MATEMATIC REAL (DISTRIBUȚIE POISSON) ---
def poisson_probability(k, lambd):
    """Calculează probabilitatea ca o echipă să marcheze k goluri dacă are o medie de 'lambd' goluri."""
    return (math.pow(lambd, k) * math.exp(-lambd)) / math.factorial(k)

def calculate_match_metrics(home_name, away_name):
    """
    Algoritm simplificat de estimare bazat pe Poisson:
    Calculează matricea de scoruri posibile (0-5 goluri per echipă).
    """
    # Medii statistice generale (până la conectarea la endpoint-ul istoric)
    home_exp = 1.45  # medie goluri gazde
    away_exp = 1.15  # medie goluri oaspeți

    prob_over_1_5 = 0.0
    prob_home_or_draw = 0.0

    for h in range(6):
        for a in range(6):
            p = poisson_probability(h, home_exp) * poisson_probability(a, away_exp)
            
            # Peste 1.5 goluri în meci
            if (h + a) > 1:
                prob_over_1_5 += p
            
            # Victorie Gazde sau Egal (1X)
            if h >= a:
                prob_home_or_draw += p

    confidence_score = (prob_over_1_5 + prob_home_or_draw) / 2
    
    return {
        "over_1_5_prob": round(prob_over_1_5 * 100, 1),
        "home_draw_prob": round(prob_home_or_draw * 100, 1),
        "confidence": round(confidence_score * 100, 1),
        "prediction_text": f"1X & Peste 1.5 Goluri (Șansă: {round(confidence_score * 100)}%)"
    }

def fetch_and_cache_matches():
    """Preluare meciuri reale din API și procesarea lor prin algoritm."""
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[{datetime.now()}] Rulare algoritm pentru meciurile din {today}...")
    
    if not API_TOKEN:
        print("[WARNING] API_TOKEN nu este setat în mediul de executare!")
    
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {
        "x-apisports-key": API_TOKEN,
        "x-rapidapi-host": "v3.football.api-sports.io"
    }
    params = {"date": today}
    
    processed_matches = []
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            res_json = response.json()
            raw_fixtures = res_json.get("response", [])
            
            for item in raw_fixtures:
                home_team = item["teams"]["home"]["name"]
                away_team = item["teams"]["away"]["name"]
                league_name = item["league"]["name"]
                country = item["league"].get("country", "")
                
                # Rulăm algoritmul pe meciul real
                metrics = calculate_match_metrics(home_team, away_team)
                
                processed_matches.append({
                    "league": f"{country}: {league_name}" if country else league_name,
                    "home": home_team,
                    "away": away_team,
                    "metrics": metrics
                })
                
            # Sortăm meciurile în funcție de scorul de încredere oferit de algoritm
            processed_matches.sort(key=lambda x: x["metrics"]["confidence"], reverse=True)
            
    except Exception as e:
        print(f"[ERROR] Eroare la preluarea datelor din API: {e}")

    # Salvăm datele reale (sau listă goală dacă API-ul este epuizat/fără meciuri)
    data_to_save = {
        "date": today,
        "matches": processed_matches,
        "api_active": len(processed_matches) > 0
    }
    
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    print(f"[SUCCESS] Procesare completă. {len(processed_matches)} meciuri calculate.")

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(fetch_and_cache_matches, 'cron', hour=0, minute=5)
scheduler.start()

@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    today = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(CACHE_FILE):
        return jsonify({"date": today, "matches": [], "api_active": False})
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
        return jsonify(cache_data)
    except Exception:
        return jsonify({"date": today, "matches": [], "api_active": False})

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XMTS AI Predictive Analytics</title>
    <style>
        body { background-color: #080e1e; color: #ffffff; font-family: -apple-system, sans-serif; margin: 0; padding: 15px; display: flex; flex-direction: column; align-items: center; }
        .container { width: 100%; max-width: 480px; }
        .header { text-align: center; font-size: 20px; font-weight: 800; color: #38bdf8; margin: 15px 0 20px 0; }
        .nav-tabs { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 15px; }
        .tab-btn { background-color: #111a2e; color: #94a3b8; border: 1px solid #1e293b; padding: 10px 14px; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; }
        .tab-btn.active { background-color: #0284c7; color: #ffffff; border-color: #38bdf8; }
        .card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 12px; padding: 15px; margin-bottom: 15px; }
        .card-gold { border: 1px solid #eab308; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .tag { background-color: #eab308; color: #000; padding: 4px 8px; border-radius: 12px; font-size: 12px; font-weight: 700; }
        .league-name { color: #38bdf8; font-size: 12px; margin-bottom: 4px; }
        .match-title { font-size: 16px; font-weight: 700; margin-bottom: 10px; }
        .prediction-badge { background-color: #0284c7; color: #fff; padding: 6px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; display: inline-block; }
        .empty-state { text-align: center; padding: 30px 15px; color: #64748b; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">XMTS AI Analytics</div>
        
        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchTab('challenge', this)">🏆 Challenge 1.5</button>
            <button class="tab-btn" onclick="switchTab('live', this)">Meciuri Azi</button>
        </div>

        <div id="tab-content">
            <div class="empty-state">Se încarcă datele...</div>
        </div>
    </div>

    <script>
        let cachedData = { matches: [], api_active: false };

        async function init() {
            try {
                const response = await fetch('/api/predictions');
                cachedData = await response.json();
                switchTab('challenge', document.querySelectorAll('.tab-btn')[0]);
            } catch (err) {
                document.getElementById('tab-content').innerHTML = `<div class="card empty-state">Eroare conectare server.</div>`;
            }
        }

        function switchTab(tabName, btnElement) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            if (btnElement) btnElement.classList.add('active');

            const content = document.getElementById('tab-content');
            const matches = cachedData.matches || [];

            if (!cachedData.api_active && matches.length === 0) {
                content.innerHTML = `
                    <div class="card empty-state">
                        ⚠️ Limită API atinsă sau date indisponibile pentru ziua de azi.<br>
                        Încearcă din nou după resetarea cotei zilnice.
                    </div>
                `;
                return;
            }

            if (tabName === 'challenge') {
                const topMatch = matches[0];
                content.innerHTML = `
                    <div class="card card-gold">
                        <div class="card-header">
                            <span class="tag">🎯 Meciul Zilei (Algoritm Poisson)</span>
                        </div>
                        <div class="league-name">${topMatch.league}</div>
                        <div class="match-title">${topMatch.home} vs ${topMatch.away}</div>
                        <div class="prediction-badge">${topMatch.metrics.prediction_text}</div>
                    </div>
                `;
            } else {
                content.innerHTML = matches.map(m => `
                    <div class="card">
                        <div class="league-name">${m.league}</div>
                        <div class="match-title">${m.home} vs ${m.away}</div>
                        <div class="prediction-badge">Pronostic: ${m.metrics.prediction_text}</div>
                    </div>
                `).join('');
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
    fetch_and_cache_matches()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
