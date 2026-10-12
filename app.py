import os
import json
import math
import csv
import io
import requests
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS

# 1. Configurare Timezone si Date
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bucharest")
except Exception:
    TZ = None

def today_str():
    if TZ:
        return datetime.now(TZ).strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")

# 2. Configurare Flask
app = Flask(__name__)
CORS(app)

CACHE_FILE = "matches_cache.json"
MAX_ROWS = 600
FIXTURES_CSV_URL = os.environ.get("FIXTURES_CSV_URL", "")

CONFIDENCE_THRESHOLD = 0.65
LOW_RISK_THRESHOLD = 0.75
FALLBACK_MIN_CONFIDENCE = 0.55
CHALLENGE_TARGET_ODD = 1.50

# 3. Ligi si Cote
TOP_LEAGUES = {"E0", "E1", "E2", "SP1", "SP2", "I1", "I2", "D1", "D2", "F1", "F2", "N1", "B1", "P1", "SC0", "T1", "G1"}

PINNACLE_1X2 = ("PSH", "PSD", "PSA")
BOOKMAKER_1X2_COLUMNS = [
    ("B365H", "B365D", "B365A", "Bet365"),
    ("BWH", "BWD", "BWA", "Bwin"),
    ("IWH", "IWD", "IWA", "Interwetten"),
    ("WHH", "WHD", "WHA", "William Hill"),
    ("VCH", "VCD", "VCA", "BetVictor"),
]
OU25_PRIORITY = [("B365>2.5", "B365<2.5"), ("Avg>2.5", "Avg<2.5"), ("BbAv>2.5", "BbAv<2.5")]

LEAGUE_NAMES = {
    "E0": "Premier League (Anglia)", "E1": "Championship (Anglia)",
    "E2": "League One (Anglia)", "E3": "League Two (Anglia)", "EC": "National League (Anglia)",
    "SC0": "Premiership (Scoția)", "SC1": "Championship (Scoția)",
    "SP1": "La Liga (Spania)", "SP2": "La Liga 2 (Spania)",
    "D1": "Bundesliga (Germania)", "D2": "Bundesliga 2 (Germania)",
    "I1": "Serie A (Italia)", "I2": "Serie B (Italia)",
    "F1": "Ligue 1 (Franța)", "F2": "Ligue 2 (Franța)",
    "N1": "Eredivisie (Olanda)", "B1": "Jupiler Pro League (Belgia)",
    "P1": "Primeira Liga (Portugalia)", "T1": "Super Lig (Turcia)", "G1": "Super League (Grecia)",
}

# 4. Utilities File System
def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[WARN] Eroare la citirea {path}: {e}")
    return default

def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[EROARE] Cache scriere eșuată la {path}: {e}")

def parse_uk_date(date_str):
    date_str = (date_str or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str

def _valid_odds_triplet(row, h_key, d_key, a_key):
    try:
        oh = float(row.get(h_key) or 0)
        od = float(row.get(d_key) or 0)
        oa = float(row.get(a_key) or 0)
        if oh > 1.01 and od > 1.01 and oa > 1.01:
            return oh, od, oa
    except (ValueError, TypeError):
        pass
    return None

def implied_probs_square_root(oh, od, oa):
    raw_h = math.sqrt(1.0 / oh)
    raw_d = math.sqrt(1.0 / od)
    raw_a = math.sqrt(1.0 / oa)
    total = raw_h + raw_d + raw_a
    return raw_h / total, raw_d / total, raw_a / total

# CORECTAT: Aici aparea SyntaxError din cauza parantezelor in versiunea anterioara.
def extract_1x2_odds(row):
    pinnacle = _valid_odds_triplet(row, *PINNACLE_1X2)
    if pinnacle:
        ph, pd, pa = implied_probs_square_root(*pinnacle)
        return ph, pd, pa, "Pinnacle (High Accuracy)"

    probs = []
    for h_key, d_key, a_key, _label in BOOKMAKER_1X2_COLUMNS:
        triplet = _valid_odds_triplet(row, h_key, d_key, a_key)
        if triplet:
            probs.append(implied_probs_square_root(*triplet))

    if probs:
        n = len(probs)
        sum_h = sum([p[0] for p in probs])
        sum_d = sum([p[1] for p in probs])
        sum_a = sum([p[2] for p in probs])
        return (sum_h / n), (sum_d / n), (sum_a / n), "Medie Case"

    avg = _valid_odds_triplet(row, "AvgH", "AvgD", "AvgA")
    if avg:
        ph, pd, pa = implied_probs_square_root(*avg)
        return ph, pd, pa, "Medie Globală"

    return None

def extract_ou25_odds(row):
    for over_key, under_key in OU25_PRIORITY:
        try:
            o_over = float(row.get(over_key) or 0)
            o_under = float(row.get(under_key) or 0)
            if o_over > 1.01 and o_under > 1.01:
                return o_over, o_under
        except (ValueError, TypeError):
            continue
    return None

# 5. Model Poisson & Shin
def poisson_pmf(k, lam):
    lam = max(lam, 0.01)
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

DIXON_COLES_RHO = -0.08

def dixon_coles_tau(x, y, lam, mu, rho):
    if x == 0 and y == 0:
        return 1.0 - (lam * mu * rho)
    elif x == 0 and y == 1:
        return 1.0 + (lam * rho)
    elif x == 1 and y == 0:
        return 1.0 + (mu * rho)
    elif x == 1 and y == 1:
        return 1.0 - rho
    return 1.0

def _match_probs_from_lambdas(lam_h, lam_a, max_g, rho=DIXON_COLES_RHO, over_line=None):
    p_h = p_d = p_a = p_over = 0.0
    ph_list = [poisson_pmf(h, lam_h) for h in range(max_g)]
    pa_list = [poisson_pmf(a, lam_a) for a in range(max_g)]
    
    for h in range(max_g):
        for a in range(max_g):
            p = ph_list[h] * pa_list[a] * dixon_coles_tau(h, a, lam_h, lam_a, rho)
            if h > a:
                p_h += p
            elif h == a:
                p_d += p
            else:
                p_a += p
            if over_line is not None and (h + a) > over_line:
                p_over += p
            
    return p_h, p_d, p_a, p_over

def calibrate_lambdas(target_h, target_d, target_a, target_over25=None):
    best = (1.4, 1.1)
    best_err = 999.0
    
    for i in range(10):
        lh = round(0.4 + i * 0.4, 2)
        for j in range(8):
            la = round(0.4 + j * 0.4, 2)
            ph, pd, pa, p_over25 = _match_probs_from_lambdas(lh, la, max_g=7, over_line=2.5)
            err = (ph - target_h)**2 + (pd - target_d)**2 + (pa - target_a)**2
            if target_over25 is not None:
                err += ((p_over25 - target_over25)**2) * 1.5
            if err < best_err:
                best_err = err
                best = (lh, la)

    lh0, la0 = best
    
    for lh_delta in [-0.2, -0.1, 0.0, 0.1, 0.2]:
        for la_delta in [-0.2, -0.1, 0.0, 0.1, 0.2]:
            lh = max(0.05, lh0 + lh_delta)
            la = max(0.05, la0 + la_delta)
            ph, pd, pa, p_over25 = _match_probs_from_lambdas(lh, la, max_g=9, over_line=2.5)
            err = (ph - target_h)**2 + (pd - target_d)**2 + (pa - target_a)**2
            if target_over25 is not None:
                err += ((p_over25 - target_over25)**2) * 1.5
            if err < best_err:
                best_err = err
                best = (lh, la)
            
    return round(best[0], 2), round(best[1], 2)

def predict_from_odds(row):
    odds_1x2 = extract_1x2_odds(row)
    if not odds_1x2:
        return None
    p_h, p_d, p_a, bookmaker = odds_1x2

    ou = extract_ou25_odds(row)
    target_over25 = None
    if ou:
        o_over, o_under = ou
        target_over25 = (math.sqrt(1.0/o_over)) / (math.sqrt(1.0/o_over) + math.sqrt(1.0/o_under))

    lam_h, lam_a = calibrate_lambdas(p_h, p_d, p_a, target_over25)

    max_g = 10
    p_home = p_draw = p_away = p_btts = 0.0
    p_over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}

    for h in range(max_g):
        for a in range(max_g):
            p = poisson_pmf(h, lam_h) * poisson_pmf(a, lam_a) * dixon_coles_tau(h, a, lam_h, lam_a, DIXON_COLES_RHO)
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
            
            tot = h + a
            if tot > 1.5: p_over[1.5] += p
            if tot > 2.5: p_over[2.5] += p
            if tot > 3.5: p_over[3.5] += p
            if h > 0 and a > 0: p_btts += p

    total_prob = p_home + p_draw + p_away
    p_home /= total_prob
    p_draw /= total_prob
    p_away /= total_prob

    if target_over25 is not None:
        p_over[2.5] = target_over25
    p_over[1.5] = max(p_over[1.5], p_over[2.5])
    
    # Calcul Probabilitati HT / ST pentru grafica
    lam_h_ht, lam_a_ht = lam_h * 0.45, lam_a * 0.45
    p_over05_ht = 1.0 - (math.exp(-lam_h_ht) * math.exp(-lam_a_ht))
    
    lam_h_st, lam_a_st = lam_h * 0.55, lam_a * 0.55
    p_over05_st = 1.0 - (math.exp(-lam_h_st) * math.exp(-lam_a_st))

    markets = {
        "1 (Gazde)": p_home,
        "X (Egal)": p_draw,
        "2 (Oaspeți)": p_away,
        "Peste 2.5 goluri": p_over[2.5],
        "Sub 2.5 goluri": max(0.01, 1.0 - p_over[2.5]),
        "GG - Da": p_btts
    }
    
    fallback = [
        ("Șansă Dublă 1X", p_home + p_draw),
        ("Șansă Dublă X2", p_draw + p_away)
    ]

    best_market = max(markets, key=markets.get)
    best_p = markets[best_market]

    result = {
        "principal": best_market,
        "principal_pct": round(best_p * 100, 1),
        "exp_goals_home": round(lam_h, 2),
        "exp_goals_away": round(lam_a, 2),
        "bookmaker": bookmaker,
        "pick_for_ticket": best_market if best_p >= CONFIDENCE_THRESHOLD else None,
        "pick_pct": round(best_p * 100, 1) if best_p >= CONFIDENCE_THRESHOLD else None,
        "fair_odd": round(1.0 / best_p, 2) if best_p >= CONFIDENCE_THRESHOLD else None,
        "probs": {
            "over15": round(p_over[1.5] * 100, 1),
            "over25": round(p_over[2.5] * 100, 1),
            "btts": round(p_btts * 100, 1),
            "over05_ht": round(p_over05_ht * 100, 1),
            "over05_st": round(p_over05_st * 100, 1)
        }
    }

    if best_p >= CONFIDENCE_THRESHOLD:
        result["risc"] = "Scăzut" if best_p >= LOW_RISK_THRESHOLD else "Mediu"
        return result

    alt_market = max(fallback, key=lambda kv: kv[1])
    alt_p = alt_market[1]
    
    if alt_p >= FALLBACK_MIN_CONFIDENCE:
        result["alternativ"] = alt_market[0]
        result["alternativ_pct"] = round(alt_p * 100, 1)
        result["risc"] = "Mediu" if alt_p >= 0.65 else "Ridicat"
        return result

    result["risc"] = "Ridicat"
    result["fara_pronostic"] = True
    return result

def process_csv_content(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    processed = []
    skipped_no_odds = 0

    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            break
            
        home = (row.get("HomeTeam") or "").strip()
        away = (row.get("AwayTeam") or "").strip()
        if not home or not away:
            continue

        pred = predict_from_odds(row)
        if pred is None:
            skipped_no_odds += 1
            continue

        league_code = (row.get("Div") or "").strip()
        
        processed.append({
            "league": LEAGUE_NAMES.get(league_code, league_code),
            "date": parse_uk_date(row.get("Date")),
            "time": (row.get("Time") or "").strip(),
            "home": home,
            "away": away,
            **pred
        })

    # Sortare dupa incredere (procentaj descrescator)
    processed.sort(key=lambda m: -(m.get("pick_pct") or 0))
    # Apoi ordonare cronologica (zi curenta prima)
    processed.sort(key=lambda m: m["date"])
    
    return processed, skipped_no_odds

def _build_fixtures_cache(content, source):
    matches, skipped = process_csv_content(content)
    cache_data = {
        "uploaded_at": datetime.now().isoformat(),
        "upload_date": today_str(),
        "matches": matches,
        "skipped_no_odds": skipped,
        "api_active": True,
        "source": source,
    }
    _save_json(CACHE_FILE, cache_data)
    return cache_data

# 6. Rute API
@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files or request.files['file'].filename == '':
        return jsonify({"status": "error", "message": "Fișier invalid!"}), 400
    try:
        content = request.files['file'].read().decode('utf-8', errors='ignore')
        c = _build_fixtures_cache(content, "upload_manual")
        return jsonify({
            "status": "success",
            "count": len(c["matches"]),
            "skipped": c["skipped_no_odds"]
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/refresh-from-github', methods=['POST'])
def refresh_from_github():
    if not FIXTURES_CSV_URL:
        return jsonify({"status": "error", "message": "Setează variabila de mediu FIXTURES_CSV_URL"}), 400
    try:
        r = requests.get(FIXTURES_CSV_URL, timeout=10)
        r.raise_for_status()
        c = _build_fixtures_cache(r.text, "github_manual")
        return jsonify({"status": "success", "count": len(c["matches"])})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    data = _load_json(CACHE_FILE, None)
    if not data or not data.get("matches"):
        if FIXTURES_CSV_URL:
            try:
                r = requests.get(FIXTURES_CSV_URL, timeout=10)
                if r.status_code == 200:
                    data = _build_fixtures_cache(r.text, "github_auto")
            except:
                pass
    return jsonify(data or {"matches": [], "api_active": False})

# ==========================================
# INTERFAȚĂ FRONTEND (HTML, CSS, JS)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XMTS AI · Precision Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-dark: #0a0a0a; --card-bg: #161616; --card-border: #2a2a2a;
    --accent-cyan: #06b6d4; --accent-gold: #eab308; --text-main: #f8fafc; --text-muted: #94a3b8;
    --bar-green: #22c55e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
  body { background: var(--bg-dark); color: var(--text-main); padding: 10px; }
  .container { max-width: 580px; margin: 0 auto; }
  
  .glass-card {
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 16px; padding: 16px; margin-bottom: 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  }
  
  .tabs-wrapper { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 10px; margin-bottom: 10px; scrollbar-width: none; }
  .tabs-wrapper::-webkit-scrollbar { display: none; }
  .tab-btn { background: #1f1f1f; border: 1px solid var(--card-border); color: var(--text-muted); padding: 10px 14px; border-radius: 10px; font-weight: 600; white-space: nowrap; cursor: pointer; }
  .tab-btn.active { background: rgba(234, 179, 8, 0.15); border-color: var(--accent-gold); color: #fff; }

  .match-basic { display:flex; flex-direction:column; gap:8px; }
  .pred-row { display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.4); border-radius: 10px; padding: 10px; }
  .risk-tag { font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; text-transform: uppercase; }
  .risk-Scăzut { background: rgba(16,185,129,0.2); color: #34d399; }
  .risk-Mediu { background: rgba(245,158,11,0.2); color: #fbbf24; }
  .risk-Ridicat { background: rgba(239,68,68,0.2); color: #fca5a5; }
  
  .btn-expand {
    width: 100%; background: #1f1f1f; border: 1px solid #eab308; color: #fff;
    padding: 10px; border-radius: 10px; font-weight: bold; cursor: pointer; margin-top: 10px;
    transition: 0.2s;
  }
  .btn-expand:active { transform: scale(0.98); }

  .golden-panel { display: none; margin-top: 15px; padding-top: 15px; border-top: 1px dashed var(--card-border); }
  .golden-header { text-align: center; color: var(--accent-gold); font-size: 18px; font-weight: 800; letter-spacing: 2px; margin-bottom: 15px; text-transform: uppercase; }
  
  .team-logos { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
  .t-badge { text-align: center; width: 45%; }
  .t-badge-circle { width: 50px; height: 50px; border: 2px solid var(--accent-gold); border-radius: 12px; margin: 0 auto 8px; display: flex; align-items: center; justify-content: center; background: #000; font-weight: bold; font-size: 18px; color: var(--accent-gold); }
  
  .h2h-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 12px; }
  .h2h-val { width: 65px; text-align: center; font-weight: 800; padding: 6px 4px; border-radius: 6px; }
  .h2h-val.gold { background: linear-gradient(to right, #d97706, #eab308); color: #000; }
  .h2h-label { flex: 1; text-align: center; color: #cbd5e1; font-weight: bold; }
  
  .bars-section { margin-top: 20px; }
  .bar-row { display: flex; align-items: center; margin-bottom: 8px; font-size: 12px; font-weight: bold; }
  .bar-label { width: 100px; color: #fff; }
  .bar-track { flex: 1; background: rgba(255,255,255,0.05); border-radius: 12px; height: 18px; overflow: hidden; position: relative; }
  .bar-fill { height: 100%; background: var(--bar-green); border-radius: 12px; display: flex; justify-content: flex-end; align-items: center; padding-right: 8px; color: #fff; font-size: 10px; }
  
  .acc-item { background: #1a1a1a; border: 1px solid var(--accent-gold); border-radius: 10px; margin-bottom: 10px; overflow: hidden; }
  .acc-header { padding: 12px 15px; display: flex; justify-content: space-between; cursor: pointer; color: #fff; font-weight: bold; }
  .acc-body { padding: 10px 15px; border-top: 1px solid #333; font-size: 12px; color: var(--text-muted); display: none; }
</style>
</head>
<body>
<div class="container">
  <div style="text-align:center; margin-bottom:15px; font-size:22px; font-weight:800; color:var(--accent-gold);">
    XMTS PREDICTIONS
  </div>

  <div class="tabs-wrapper">
    <button class="tab-btn active" onclick="switchTab('azi', this)">🗓️ Azi</button>
    <button class="tab-btn" onclick="switchTab('toate', this)">📋 Toate Zilele</button>
  </div>

  <div id="content"><div class="glass-card" style="text-align:center;">Se încarcă...</div></div>
</div>

<script>
let state = { matches: [] };
let currentTab = 'azi';

function getTodayStr() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
}

function toggleGoldenPanel(btn) {
  const panel = btn.nextElementSibling;
  const isHidden = panel.style.display === 'none' || panel.style.display === '';
  panel.style.display = isHidden ? 'block' : 'none';
  btn.innerText = isHidden ? 'Ascunde Analiza' : 'Deschide Analiză Detaliată';
}

function toggleAccordion(header) {
  const body = header.nextElementSibling;
  body.style.display = body.style.display === 'block' ? 'none' : 'block';
}

function renderMatchCard(m) {
  const p = m.probs;
  
  const avgH = m.exp_goals_home;
  const avgA = m.exp_goals_away;
  const cndH = m.exp_goals_away; 
  const cndA = m.exp_goals_home; 

  const htH = Math.min(100, Math.round(p.over05_ht * (avgH / (avgH + avgA + 0.1)) * 1.5)).toFixed(2);
  const htA = Math.min(100, Math.round(p.over05_ht * (avgA / (avgH + avgA + 0.1)) * 1.5)).toFixed(2);
  const stH = Math.min(100, Math.round(p.over05_st * (avgH / (avgH + avgA + 0.1)) * 1.5)).toFixed(2);
  const stA = Math.min(100, Math.round(p.over05_st * (avgA / (avgH + avgA + 0.1)) * 1.5)).toFixed(2);
  const o15H = Math.min(100, Math.round((avgH / 2) * 100)).toFixed(2);
  const o15A = Math.min(100, Math.round((avgA / 2) * 100)).toFixed(2);
  
  return `
    <div class="glass-card">
      <div class="match-basic">
        <div style="font-size:11px;color:var(--text-muted);display:flex;justify-content:space-between;">
          <span>${m.league} · ${m.date} ${m.time || ''}</span>
          <span>${m.bookmaker.split(' ')[0]}</span>
        </div>
        <div style="font-size:16px;font-weight:800;text-align:center;">${m.home} VS ${m.away}</div>
        
        <div class="pred-row">
          <span style="font-size:13px;font-weight:700;color:#fff;">
            ⭐ ${m.principal || m.alternativ || "Meci Echilibrat"} <span style="color:var(--accent-gold);">(${m.principal_pct || m.alternativ_pct || "-"}%)</span>
          </span>
          <span class="risk-tag risk-${m.risc}">${m.risc}</span>
        </div>
      </div>

      <button class="btn-expand" onclick="toggleGoldenPanel(this)">Deschide Analiză Detaliată</button>
      
      <div class="golden-panel">
        <div class="team-logos">
          <div class="t-badge">
            <div class="t-badge-circle">${m.home.substring(0,3).toUpperCase()}</div>
            <div style="font-size:11px;font-weight:bold;">${m.home.toUpperCase()}</div>
          </div>
          <div style="font-size:12px;font-weight:bold;color:var(--text-muted);">VS</div>
          <div class="t-badge">
            <div class="t-badge-circle">${m.away.substring(0,3).toUpperCase()}</div>
            <div style="font-size:11px;font-weight:bold;">${m.away.toUpperCase()}</div>
          </div>
        </div>

        <div class="golden-header">STATISTICS</div>

        <div class="h2h-row"><div class="h2h-val">${avgH}</div><div class="h2h-label">Expected Goals (xG)</div><div class="h2h-val">${avgA}</div></div>
        <div class="h2h-row"><div class="h2h-val">${cndH}</div><div class="h2h-label">Goals Conceded (xG)</div><div class="h2h-val">${cndA}</div></div>
        <div class="h2h-row"><div class="h2h-val gold">${htH}%</div><div class="h2h-label">Team Over 0.5 HT</div><div class="h2h-val gold">${htA}%</div></div>
        <div class="h2h-row"><div class="h2h-val gold">${stH}%</div><div class="h2h-label">Team Over 0.5 ST</div><div class="h2h-val gold">${stA}%</div></div>
        <div class="h2h-row"><div class="h2h-val gold">${o15H}%</div><div class="h2h-label">Team Over 1.5 Goals</div><div class="h2h-val gold">${o15A}%</div></div>

        <div class="bars-section">
          <div class="bar-row"><div class="bar-label">Over 1.5:</div><div class="bar-track"><div class="bar-fill" style="width: ${p.over15}%;">${p.over15}%</div></div></div>
          <div class="bar-row"><div class="bar-label">Over 2.5:</div><div class="bar-track"><div class="bar-fill" style="width: ${p.over25}%;">${p.over25}%</div></div></div>
          <div class="bar-row"><div class="bar-label">Over 0.5 HT:</div><div class="bar-track"><div class="bar-fill" style="width: ${p.over05_ht}%;">${p.over05_ht}%</div></div></div>
          <div class="bar-row"><div class="bar-label">Over 0.5 ST:</div><div class="bar-track"><div class="bar-fill" style="width: ${p.over05_st}%;">${p.over05_st}%</div></div></div>
          <div class="bar-row"><div class="bar-label">Both Score:</div><div class="bar-track"><div class="bar-fill" style="width: ${p.btts}%;">${p.btts}%</div></div></div>
        </div>

        <div style="margin-top: 20px;">
          <div class="acc-item">
            <div class="acc-header" onclick="toggleAccordion(this)">
              <div>🟨 Cartonașe<br><span style="font-size:10px;color:#94a3b8;font-weight:normal;">Linii estimate Poisson</span></div>
              <div>▼</div>
            </div>
            <div class="acc-body">Estimat meci: ~4.5 cartonașe în total.<br><i>Datele exacte necesită fișier istoric separat.</i></div>
          </div>
          <div class="acc-item">
            <div class="acc-header" onclick="toggleAccordion(this)">
              <div>🚩 Cornere<br><span style="font-size:10px;color:#94a3b8;font-weight:normal;">Linii estimate Poisson</span></div>
              <div>▼</div>
            </div>
            <div class="acc-body">Estimat meci: ~9.5 cornere în total.<br><i>Datele exacte necesită fișier istoric separat.</i></div>
          </div>
        </div>
      </div>
    </div>`;
}

function render() {
  const c = document.getElementById('content');
  if(!state.matches || !state.matches.length) { c.innerHTML = '<div class="glass-card" style="text-align:center;">Niciun meci procesat.</div>'; return; }
  
  const today = getTodayStr();
  const todayMatches = state.matches.filter(m => m.date === today);
  
  if(currentTab === 'azi') {
    c.innerHTML = todayMatches.length ? todayMatches.map(renderMatchCard).join('') : `<div class="glass-card" style="text-align:center;">Nu sunt meciuri programate pentru azi (${today}).</div>`;
  } else if(currentTab === 'toate') {
    c.innerHTML = state.matches.map(renderMatchCard).join('');
  }
}

function switchTab(t, btn) { currentTab = t; document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); render(); }

async function fetchAPI() {
  try {
    const res = await fetch('/api/predictions');
    if(!res.ok) throw new Error('Nu sunt date.');
    state = await res.json(); 
    render();
  } catch(e) { 
    document.getElementById('content').innerHTML = '<div class="glass-card" style="text-align:center;">Eroare conexiune server.</div>';
  }
}

fetchAPI();
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
