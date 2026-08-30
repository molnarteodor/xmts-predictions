import os
import json
import math
import csv
import io
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

CACHE_FILE = "matches_cache.json"

# --- ALGORITM MATEMATIC (POISSON BAZAT PE COTE REALE) ---
def poisson_probability(k, lambd):
    return (math.pow(lambd, k) * math.exp(-lambd)) / math.factorial(k)

def calculate_metrics_from_odds(home, away, odd_h, odd_d, odd_a):
    """Calcul matematic folosind cotele reale din CSV pentru estimarea golurilor."""
    try:
        prob_h = 1 / float(odd_h) if float(odd_h) > 0 else 0.4
        prob_a = 1 / float(odd_a) if float(odd_a) > 0 else 0.3
    except (ValueError, TypeError):
        prob_h, prob_a = 0.45, 0.30

    # Estimare goluri pe baza favoriților
    home_exp = 1.2 + (prob_h * 1.5)
    away_exp = 0.8 + (prob_a * 1.2)

    prob_over_1_5 = 0.0
    prob_home_or_draw = 0.0

    for h in range(6):
        for a in range(6):
            p = poisson_probability(h, home_exp) * poisson_probability(a, away_exp)
            if (h + a) > 1:
                prob_over_1_5 += p
            if h >= a:
                prob_home_or_draw += p

    confidence_score = (prob_over_1_5 * 0.4) + (prob_home_or_draw * 0.6)
    
    return {
        "confidence": round(confidence_score * 100, 1),
        "prediction_text": f"1X & Peste 1.5 Goluri (Șansă: {round(confidence_score * 100)}%)"
    }

def process_csv_content(csv_text):
    """Parsează fișierul fixtures.csv descărcat de pe football-data.co.uk."""
    processed = []
    # Folosim csv.DictReader pentru a citi după capul de tabel
    f = io.StringIO(csv_text)
    reader = csv.DictReader(f)
    
    for row in reader:
        home = row.get("HomeTeam", "").strip()
        away = row.get("AwayTeam", "").strip()
        league = row.get("Div", "").strip()
        date_str = row.get("Date", "").strip()
        
        odd_h = row.get("B365H", 0)
        odd_d = row.get("B365D", 0)
        odd_a = row.get("B365A", 0)

        if home and away:
            metrics = calculate_metrics_from_odds(home, away, odd_h, odd_d, odd_a)
            processed.append({
                "league": league,
                "date": date_str,
                "home": home,
                "away": away,
                "metrics": metrics
            })

    # Sortăm după cel mai sigur meci calculat
    processed.sort(key=lambda x: x["metrics"]["confidence"], reverse=True)
    return processed

@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    """Endpoint pentru încărcarea fișierului fixtures.csv."""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Niciun fișier încărcat!"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Fișier neselectat!"}), 400

    try:
        content = file.read().decode('utf-8', errors='ignore')
        processed_matches = process_csv_content(content)
        
        today = datetime.now().strftime("%Y-%m-%d")
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
        input[type="file"] { display: none; }
        .file-label { background: #0284c7; color: #fff; padding: 10px 15px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 13px; display: inline-block; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">XMTS AI Analytics</div>
        
        <div class="card upload-area">
            <div style="font-size: 13px; font-weight: 700; margin-bottom: 10px;">📂 Încarcă Fișierul fixtures.csv</div>
            <label for="csvFileInput" class="file-label">Alege fișierul CSV</label>
            <input type="file" id="csvFileInput" accept=".csv" onchange="uploadCSV()">
        </div>

        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchTab('challenge', this)">🏆 Challenge 1.5</button>
            <button class="tab-btn" onclick="switchTab('live', this)">Toate Meciurile</button>
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

        async function uploadCSV() {
            const fileInput = document.getElementById('csvFileInput');
            if (fileInput.files.length === 0) return;

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);

            try {
                const response = await fetch('/api/upload-csv', {
                    method: 'POST',
                    body: formData
                });
                const res = await response.json();
                if (res.status === 'success') {
                    alert(`Fișier încărcat cu succes! Au fost procesate ${res.count} meciuri.`);
                    init();
                } else {
                    alert("Eroare: " + res.message);
                }
            } catch (e) {
                alert("Eroare la încărcarea fișierului CSV.");
            }
        }

        function switchTab(tabName, btnElement) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            if (btnElement) btnElement.classList.add('active');

            const content = document.getElementById('tab-content');
            const matches = cachedData.matches || [];

            if (matches.length === 0) {
                content.innerHTML = `<div class="card empty-state">Nu există meciuri. Apasă pe butonul de mai sus și încarcă fișierul <b>fixtures.csv</b> descărcat de pe site.</div>`;
                return;
            }

            if (tabName === 'challenge') {
                const topMatch = matches[0];
                content.innerHTML = `
                    <div class="card card-gold">
                        <div class="card-header">
                            <span class="tag">🎯 Meciul Zilei (Poisson + Cote Bet365)</span>
                        </div>
                        <div class="league-name">Liga: ${topMatch.league} | Data: ${topMatch.date}</div>
                        <div class="match-title">${topMatch.home} vs ${topMatch.away}</div>
                        <div class="prediction-badge">${topMatch.metrics.prediction_text}</div>
                    </div>
                `;
            } else {
                content.innerHTML = matches.map(m => `
                    <div class="card">
                        <div class="league-name">Liga: ${m.league} | Data: ${m.date}</div>
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
