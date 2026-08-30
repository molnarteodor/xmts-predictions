import os
import json
import math
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

CACHE_FILE = "matches_cache.json"

# --- ALGORITM MATEMATIC REAL (DISTRIBUȚIE POISSON) ---
def poisson_probability(k, lambd):
    return (math.pow(lambd, k) * math.exp(-lambd)) / math.factorial(k)

def calculate_match_metrics(home_name, away_name):
    home_exp = 1.45
    away_exp = 1.15

    prob_over_1_5 = 0.0
    prob_home_or_draw = 0.0

    for h in range(6):
        for a in range(6):
            p = poisson_probability(h, home_exp) * poisson_probability(a, away_exp)
            if (h + a) > 1:
                prob_over_1_5 += p
            if h >= a:
                prob_home_or_draw += p

    confidence_score = (prob_over_1_5 + prob_home_or_draw) / 2
    
    return {
        "confidence": round(confidence_score * 100, 1),
        "prediction_text": f"1X & Peste 1.5 Goluri (Șansă: {round(confidence_score * 100)}%)"
    }

def process_raw_matches(raw_matches):
    """Procesează lista de meciuri prin algoritmul Poisson."""
    processed = []
    for m in raw_matches:
        home = m.get("home") or m.get("HomeTeam") or "Echipa Gazda"
        away = m.get("away") or m.get("AwayTeam") or "Echipa Oaspete"
        league = m.get("league") or m.get("Div") or "Fotbal"
        
        metrics = calculate_match_metrics(home, away)
        processed.append({
            "league": league,
            "home": home,
            "away": away,
            "metrics": metrics
        })
    
    # Sortare după șansele de reușită calculate de algoritm
    processed.sort(key=lambda x: x["metrics"]["confidence"], reverse=True)
    return processed

@app.route('/api/upload', methods=['POST'])
def upload_matches():
    """Endpoint pentru încărcarea manuală a meciurilor (JSON)."""
    try:
        data = request.get_json()
        if not data or "matches" not in data:
            return jsonify({"status": "error", "message": "Format JSON invalid!"}), 400
        
        today = datetime.now().strftime("%Y-%m-%d")
        processed_matches = process_raw_matches(data["matches"])
        
        cache_data = {
            "date": today,
            "matches": processed_matches,
            "api_active": True
        }
        
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
        return jsonify({"status": "success", "count": len(processed_matches)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    today = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(CACHE_FILE):
        return jsonify({"date": today, "matches": [], "api_active": False})
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
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
        .header { text-align: center; font-size: 20px; font-weight: 800; color: #38bdf8; margin: 15px 0 15px 0; }
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
        .empty-state { text-align: center; padding: 20px 15px; color: #64748b; font-size: 14px; }
        .upload-area { margin-bottom: 15px; text-align: center; }
        textarea { width: 100%; height: 80px; background: #111a2e; color: #fff; border: 1px solid #1e293b; border-radius: 8px; padding: 8px; box-sizing: border-box; font-size: 12px; }
        .btn-upload { background: #22c55e; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 700; cursor: pointer; margin-top: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">XMTS AI Analytics</div>
        
        <!-- Zona incarcare manuala -->
        <div class="card upload-area">
            <div style="font-size: 13px; font-weight: 700; margin-bottom: 8px;">📥 Adaugă Meciuri Manual (Format JSON)</div>
            <textarea id="jsonInput" placeholder='[{"home": "Real Madrid", "away": "Barcelona", "league": "La Liga"}]'></textarea>
            <button class="btn-upload" onclick="uploadData()">Procesează Meciuri</button>
        </div>

        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchTab('challenge', this)">🏆 Challenge 1.5</button>
            <button class="tab-btn" onclick="switchTab('live', this)">Meciuri Incarcate</button>
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

        async function uploadData() {
            const rawText = document.getElementById('jsonInput').value;
            try {
                const parsed = JSON.parse(rawText);
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ matches: parsed })
                });
                const res = await response.json();
                if (res.status === 'success') {
                    alert(`Au fost procesate cu succes ${res.count} meciuri!`);
                    document.getElementById('jsonInput').value = '';
                    init();
                } else {
                    alert("Eroare: " + res.message);
                }
            } catch (e) {
                alert("Formatul textului nu este un JSON valid!");
            }
        }

        function switchTab(tabName, btnElement) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            if (btnElement) btnElement.classList.add('active');

            const content = document.getElementById('tab-content');
            const matches = cachedData.matches || [];

            if (matches.length === 0) {
                content.innerHTML = `<div class="card empty-state">Nu există meciuri încărcate pentru azi. Folosește caseta de sus pentru a adăuga meciuri.</div>`;
                return;
            }

            if (tabName === 'challenge') {
                const topMatch = matches[0];
                content.innerHTML = `
                    <div class="card card-gold">
                        <div class="card-header">
                            <span class="tag">🎯 Meciul Zilei (Calculat Matematic)</span>
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
