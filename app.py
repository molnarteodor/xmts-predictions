import os
import json
import math
import csv
import io
import requests
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bucharest")
except Exception:
    TZ = None

def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d") if TZ else datetime.now().strftime("%Y-%m-%d")

app = Flask(__name__)
CORS(app)

CACHE_FILE = "matches_cache.json"
MAX_ROWS = 600

FIXTURES_CSV_URL = os.environ.get("FIXTURES_CSV_URL", "")

CONFIDENCE_THRESHOLD = 0.65
LOW_RISK_THRESHOLD = 0.75
FALLBACK_MIN_CONFIDENCE = 0.55

CHALLENGE_TARGET_ODD = 1.50
MIN_PICK_CONFIDENCE_FOR_TICKET = 0.55

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

# Aici este dicționarul care lipsea!
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

BETBUILDER_COMBOS = [
    ("1 & Peste 1.5 goluri", lambda h, a: h > a and (h + a) > 1.5),
    ("1 & Peste 2.5 goluri", lambda h, a: h > a and (h + a) > 2.5),
    ("1 & GG Da", lambda h, a: h > a and h > 0 and a > 0),
    ("2 & Peste 1.5 goluri", lambda h, a: h < a and (h + a) > 1.5),
    ("2 & Peste 2.5 goluri", lambda h, a: h < a and (h + a) > 2.5),
    ("2 & GG Da", lambda h, a: h < a and h > 0 and a > 0),
    ("X & Sub 2.5 goluri", lambda h, a: h == a and (h + a) < 2.5),
    ("GG Da & Peste 2.5 goluri", lambda h, a: h > 0 and a > 0 and (h + a) > 2.5),
    ("Șansă Dublă 1X & Sub 3.5 goluri", lambda h, a: h >= a and (h + a) < 3.5),
    ("Șansă Dublă X2 & Sub 3.5 goluri", lambda h, a: h <= a and (h + a) < 3.5),
    ("Șansă Dublă 1X & GG Da", lambda h, a: h >= a and h > 0 and a > 0),
    ("Șansă Dublă X2 & GG Da", lambda h, a: h <= a and h > 0 and a > 0),
    ("1 & GG Nu & Sub 3.5 goluri", lambda h, a: h > a and not (h > 0 and a > 0) and (h + a) < 3.5),
]

def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[EROARE] Cache scriere esuata: {e}")

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
        oh, od, oa = float(row.get(h_key) or 0), float(row.get(d_key) or 0), float(row.get(a_key) or 0)
        if oh > 1.01 and od > 1.01 and oa > 1.01:
            return oh, od, oa
    except (ValueError, TypeError):
        pass
    return None

def implied_probs_square_root(oh, od, oa):
    raw_h, raw_d, raw_a = math.sqrt(1 / oh), math.sqrt(1 / od), math.sqrt(1 / oa)
    total = raw_h + raw_d + raw_a
    return raw_h / total, raw_d / total, raw_a / total

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
        return sum(p[0] for p in probs)/n, sum(p[1] for p in probs)/n, sum(p[2] for p in probs)/n, "Medie Case"

    avg = _valid_odds_triplet(row, "AvgH", "AvgD", "AvgA")
    if avg:
        ph, pd, pa = implied_probs_square_root(*avg)
        return ph, pd, pa, "Medie Globala"

    return None

def extract_ou25_odds(row):
    for over_key, under_key in OU25_PRIORITY:
        try:
            o_over, o_under = float(row.get(over_key) or 0), float(row.get(under_key) or 0)
            if o_over > 1.01 and o_under > 1.01:
                return o_over, o_under
        except (ValueError, TypeError):
            continue
    return None

def poisson_pmf(k, lam):
    lam = max(lam, 0.01)
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

DIXON_COLES_RHO = -0.08

def dixon_coles_tau(x, y, lam, mu, rho):
    if x == 0 and y == 0: return 1.0 - (lam * mu * rho)
    elif x == 0 and y == 1: return 1.0 + (lam * rho)
    elif x == 1 and y == 0: return 1.0 + (mu * rho)
    elif x == 1 and y == 1: return 1.0 - rho
    return 1.0

def _match_probs_from_lambdas(lam_h, lam_a, max_g, rho=DIXON_COLES_RHO, over_line=None):
    p_h = p_d = p_a = p_over = 0.0
    ph_list = [poisson_pmf(h, lam_h) for h in range(max_g)]
    pa_list = [poisson_pmf(a, lam_a) for a in range(max_g)]
    
    for h in range(max_g):
        for a in range(max_g):
            p = ph_list[h] * pa_list[a] * dixon_coles_tau(h, a, lam_h, lam_a, rho)
            if h > a: p_h += p
            elif h == a: p_d += p
            else: p_a += p
            if over_line is not None and (h + a) > over_line: p_over += p
            
    return p_h, p_d, p_a, p_over

def calibrate_lambdas(target_h, target_d, target_a, target_over25=None):
    best, best_err = (1.4, 1.1), 999.0
    
    for lh in [round(0.4 + i * 0.4, 2) for i in range(10)]:
        for la in [round(0.4 + i * 0.4, 2) for i in range(8)]:
            ph, pd, pa, p_over25 = _match_probs_from_lambdas(lh, la, max_g=7, over_line=2.5)
            err = (ph - target_h) ** 2 + (pd - target_d) ** 2 + (pa - target_a) ** 2
            if target_over25: err += ((p_over25 - target_over25) ** 2) * 1.5
            if err < best_err: best_err, best = err, (lh, la)

    lh0, la0 = best
    
    for lh_delta in [-0.2, -0.1, 0.0, 0.1, 0.2]:
        for la_delta in [-0.2, -0.1, 0.0, 0.1, 0.2]:
            lh = max(0.05, lh0 + lh_delta)
            la = max(0.05, la0 + la_delta)
            ph, pd, pa, p_over25 = _match_probs_from_lambdas(lh, la, max_g=9, over_line=2.5)
            err = (ph - target_h) ** 2 + (pd - target_d) ** 2 + (pa - target_a) ** 2
            if target_over25: err += ((p_over25 - target_over25) ** 2) * 1.5
            if err < best_err: best_err, best = err, (lh, la)
            
    return round(best[0], 2), round(best[1], 2)

def predict_from_odds(row):
    odds_1x2 = extract_1x2_odds(row)
    if not odds_1x2: return None
    p_h, p_d, p_a, bookmaker = odds_1x2

    ou = extract_ou25_odds(row)
    target_over25 = None
    if ou:
        o_over, o_under = ou
        target_over25 = (math.sqrt(1/o_over)) / (math.sqrt(1/o_over) + math.sqrt(1/o_under))

    lam_h, lam_a = calibrate_lambdas(p_h, p_d, p_a, target_over25)

    max_g = 10
    ph_list = [poisson_pmf(h, lam_h) for h in range(max_g)]
    pa_list = [poisson_pmf(a, lam_a) for a in range(max_g)]
    p_home = p_draw = p_away = p_btts = 0.0
    p_over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}

    for h in range(max_g):
        for a in range(max_g):
            p = ph_list[h] * pa_list[a] * dixon_coles_tau(h, a, lam_h, lam_a, DIXON_COLES_RHO)
            if h > a: p_home += p
            elif h == a: p_draw += p
            else: p_away += p
            
            tot = h + a
            for line in p_over:
                if tot > line: p_over[line] += p
            if h > 0 and a > 0: p_btts += p

    total_prob = p_home + p_draw + p_away
    p_home /= total_prob
    p_draw /= total_prob
    p_away /= total_prob

    if target_over25 is not None:
        p_over[2.5] = target_over25
    p_over[1.5] = max(p_over[1.5], p_over[2.5])
    p_over[3.5] = min(p_over[3.5], p_over[2.5])

    markets = {
        "1 (Gazde)": p_home, "X (Egal)": p_draw, "2 (Oaspeti)": p_away,
        "Peste 2.5 goluri": p_over[2.5], "Peste 3.5 goluri": p_over[3.5],
        "Sub 2.5 goluri": max(0.01, 1 - p_over[2.5]),
        "GG - Da": p_btts, "GG - Nu": max(0.01, 1 - p_btts),
    }
    
    fallback = [
        ("Sansa Dubla 1X", p_home + p_draw), ("Sansa Dubla X2", p_draw + p_away),
        ("Peste 1.5 goluri", p_over[1.5]), ("Sub 3.5 goluri", max(0.01, 1 - p_over[3.5])),
    ]

    best_market, best_p = max(markets.items(), key=lambda kv: kv[1])
    
    scored = [(l, p, 1/p) for l, p in {**markets, **dict(fallback)}.items() if p > 0.05]
    in_range = [c for c in scored if 1.30 <= c[2] <= 1.40]
    target_pick = max(in_range, key=lambda c: c[1]) if in_range else min(scored, key=lambda c: abs(c[2] - 1.35))

    result = {
        "principal": best_market, "principal_pct": round(best_p * 100, 1),
        "alternativ": None, "alternativ_pct": None,
        "exp_goals_home": round(lam_h, 2), "exp_goals_away": round(lam_a, 2),
        "bookmaker": bookmaker,
        "pick_for_ticket": None, "pick_pct": None, "fair_odd": None,
        "target_odd_pick": {"pick": target_pick[0], "pct": round(target_pick[1]*100, 1), "odd": round(target_pick[2], 2)}
    }

    if best_p >= CONFIDENCE_THRESHOLD:
        result["risc"] = "Scazut" if best_p >= LOW_RISK_THRESHOLD else "Mediu"
        result["pick_for_ticket"] = best_market
        result["pick_pct"] = result["principal_pct"]
        result["fair_odd"] = round(1 / best_p, 2)
        return result

    alt_market, alt_p = max(fallback, key=lambda kv: kv[1])
    if alt_p >= FALLBACK_MIN_CONFIDENCE:
        result["alternativ"] = alt_market
        result["alternativ_pct"] = round(alt_p * 100, 1)
        result["risc"] = "Mediu" if alt_p >= 0.65 else "Ridicat"
        result["pick_for_ticket"] = alt_market
        result["pick_pct"] = result["alternativ_pct"]
        result["fair_odd"] = round(1 / alt_p, 2)
        return result

    result["risc"] = "Ridicat"
    result["fara_pronostic"] = True
    return result

def compute_betbuilder(lam_h, lam_a, max_g=10, top_n=4, min_pct=0.35):
    ph_list = [poisson_pmf(h, lam_h) for h in range(max_g)]
    pa_list = [poisson_pmf(a, lam_a) for a in range(max_g)]
    scored = []
    for label, cond in BETBUILDER_COMBOS:
        p = sum(ph_list[h] * pa_list[a] * dixon_coles_tau(h, a, lam_h, lam_a, DIXON_COLES_RHO)
                for h in range(max_g) for a in range(max_g) if cond(h, a))
        scored.append((label, p))
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return [{"combo": lbl, "pct": round(p * 100, 1)} for lbl, p in scored[:top_n] if p >= min_pct]

def build_ticket_for_target(candidates, target):
    selection, cum_odd, cum_prob = [], 1.0, 1.0
    for m in candidates:
        if cum_odd >= target: break
        selection.append(m)
        cum_odd *= m["fair_odd"]
        cum_prob *= m["pick_pct"] / 100
    if not selection: return None
    return {
        "target_odd": target,
        "combined_odd": round(cum_odd, 2),
        "combined_probability_pct": round(cum_prob * 100, 2),
        "selections": [{"league": s["league"], "home": s["home"], "away": s["away"], "pick": s["pick_for_ticket"], "pct": s["pick_pct"]} for s in selection]
    }

def process_csv_content(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    processed, skipped_no_odds = [], 0

    for i, row in enumerate(reader):
        if i >= MAX_ROWS: break
        home, away = (row.get("HomeTeam") or "").strip(), (row.get("AwayTeam") or "").strip()
        if not home or not away: continue

        pred = predict_from_odds(row)
        if pred is None:
            skipped_no_odds += 1
            continue

        league_code = (row.get("Div") or "").strip()
        bb = compute_betbuilder(pred["exp_goals_home"], pred["exp_goals_away"]) if league_code in TOP_LEAGUES else []

        processed.append({
            "league": LEAGUE_NAMES.get(league_code, league_code), "league_code": league_code,
            "date": parse_uk_date(row.get("Date")), "time": (row.get("Time") or "").strip(),
            "home": home, "away": away,
            "betbuilder": bb, **pred
        })

    processed.sort(key=lambda m: -(m.get("pick_pct") or 0))
    processed.sort(key=lambda m: m["date"])

    cands = [m for m in processed if m.get("pick_pct", 0)/100 >= MIN_PICK_CONFIDENCE_FOR_TICKET]
    challenge = build_ticket_for_target(cands, CHALLENGE_TARGET_ODD)
    
    return processed, challenge, skipped_no_odds

def _build_fixtures_cache(content, source):
    matches, challenge, skipped = process_csv_content(content)
    cache_data = {
        "uploaded_at": datetime.now().isoformat(),
        "upload_date": today_str(),
        "matches": matches,
        "challenge": challenge,
        "skipped_no_odds": skipped,
        "api_active": True,
        "source": source,
    }
    _save_json(CACHE_FILE, cache_data)
    return cache_data

@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files or request.files['file'].filename == '':
        return jsonify({"status": "error", "message": "Fisier invalid!"}), 400
    try:
        content = request.files['file'].read().decode('utf-8', errors='ignore')
        c = _build_fixtures_cache(content, "upload_manual")
        return jsonify({"status": "success", "count": len(c["matches"]), "skipped": c["skipped_no_odds"], "challenge": bool(c["challenge"])})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/refresh-from-github', methods=['POST'])
def refresh_from_github():
    if not FIXTURES_CSV_URL: return jsonify({"status": "error", "message": "Seteaza FIXTURES_CSV_URL"}), 400
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
            except: pass
    return jsonify(data or {"matches": [], "api_active": False})

# --- FRONTEND (HTML + JS) ---
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
    --bg-dark: #020617; --card-bg: rgba(15, 23, 42, 0.85); --card-border: rgba(255, 255, 255, 0.05);
    --accent-cyan: #06b6d4; --accent-gold: #f59e0b; --text-main: #f8fafc; --text-muted: #94a3b8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
  body { background: var(--bg-dark); color: var(--text-main); padding: 15px; }
  .container { max-width: 580px; margin: 0 auto; }
  .header-box { text-align: center; margin-bottom: 20px; }
  .title-main { font-size: 24px; font-weight: 800; background: linear-gradient(135deg, #fff, var(--accent-cyan)); -webkit-background-clip: text; color: transparent; }
  
  .glass-card {
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 16px; padding: 16px; margin-bottom: 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  }
  .upload-area { border: 1px dashed rgba(6, 182, 212, 0.4); text-align: center; }
  .btn {
    background: linear-gradient(135deg, var(--accent-cyan), #3b82f6); color: #fff;
    border: none; padding: 10px 16px; border-radius: 10px; font-weight: 800; cursor: pointer;
  }
  .btn-gold { background: linear-gradient(135deg, var(--accent-gold), #d97706); color: #000; }
  
  .tabs-wrapper { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 10px; margin-bottom: 10px; scrollbar-width: none; }
  .tabs-wrapper::-webkit-scrollbar { display: none; }
  .tab-btn { background: rgba(255,255,255,0.05); border: 1px solid var(--card-border); color: var(--text-muted); padding: 10px 14px; border-radius: 10px; font-weight: 600; white-space: nowrap; cursor: pointer; }
  .tab-btn.active { background: rgba(6,182,212,0.15); border-color: var(--accent-cyan); color: #fff; }

  .pred-row { display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.3); border-radius: 10px; padding: 10px; margin: 8px 0; }
  .risk-tag { font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; text-transform: uppercase; }
  .risk-Scazut { background: rgba(16,185,129,0.2); color: #34d399; }
  .risk-Mediu { background: rgba(245,158,11,0.2); color: #fbbf24; }
  .risk-Ridicat { background: rgba(239,68,68,0.2); color: #fca5a5; }
</style>
</head>
<body>
<div class="container">
  <div class="header-box">
    <div class="title-main">XMTS Precision Engine</div>
    <div style="font-size:12px; color:var(--text-muted); margin-top:5px;">Acuratețe ridicată prin algoritm Shin & Dixon-Coles</div>
  </div>

  <div class="glass-card upload-area">
    <div style="margin-bottom:10px; font-weight:700;">📂 Încarcă CSV (Football-Data)</div>
    <input type="file" id="csvFile" style="display:none;" onchange="uploadCSV()">
    <label for="csvFile" class="btn">Încarcă Local</label>
    <button class="btn btn-gold" onclick="syncGithub()" style="margin-left:8px;">Sync Automat</button>
    <div id="status" style="font-size:11px; margin-top:8px; color:var(--text-muted);">Așteptare date...</div>
  </div>

  <div class="tabs-wrapper">
    <button class="tab-btn active" onclick="switchTab('toate', this)">📋 Meciuri</button>
    <button class="tab-btn" onclick="switchTab('challenge', this)">🎯 Challenge 1.50</button>
    <button class="tab-btn" onclick="switchTab('betbuilder', this)">🧩 BetBuilder</button>
  </div>

  <div id="content"><div class="glass-card" style="text-align:center;">Se încarcă...</div></div>
</div>

<script>
let state = { matches: [], challenge: null };
let currentTab = 'toate';

const DIXON_COLES_RHO = -0.08;
function poissonPmf(k, lam){ return Math.exp(-lam) * Math.pow(lam, k) / (Array.from({length: k}, (_, i) => i + 1).reduce((a, b) => a * b, 1) || 1); }
function dixonColesTau(x, y, lam, mu){
  if(x===0 && y===0) return 1 - (lam*mu*DIXON_COLES_RHO);
  if(x===0 && y===1) return 1 + (lam*DIXON_COLES_RHO);
  if(x===1 && y===0) return 1 + (mu*DIXON_COLES_RHO);
  if(x===1 && y===1) return 1 - DIXON_COLES_RHO;
  return 1.0;
}
const BB_COMBOS = [
  ["1 & Peste 1.5 gol", (h,a)=>h>a && (h+a)>1.5], ["1 & Peste 2.5 gol", (h,a)=>h>a && (h+a)>2.5], ["1 & GG Da", (h,a)=>h>a && h>0 && a>0],
  ["2 & Peste 1.5 gol", (h,a)=>h<a && (h+a)>1.5], ["X & Sub 3.5 gol", (h,a)=>h===a && (h+a)<3.5], ["GG Da & Peste 2.5 gol", (h,a)=>h>0 && a>0 && (h+a)>2.5],
  ["Sansa Dubla 1X & GG", (h,a)=>h>=a && h>0 && a>0], ["1 & GG Nu & Sub 3.5", (h,a)=>h>a && a===0 && (h+a)<3.5]
];
function getBB(lamH, lamA){
  const ph = [], pa = [];
  for(let i=0;i<10;i++){ ph.push(poissonPmf(i, lamH)); pa.push(poissonPmf(i, lamA)); }
  let scored = BB_COMBOS.map(([lbl, cond]) => {
    let p = 0;
    for(let h=0;h<10;h++) for(let a=0;a<10;a++) if(cond(h,a)) p += ph[h]*pa[a]*dixonColesTau(h,a,lamH,lamA);
    return {combo: lbl, pct: (p*100).toFixed(1)};
  }).filter(c => c.pct >= 35.0).sort((a,b) => b.pct - a.pct).slice(0,3);
  return scored;
}

function renderCard(m) {
  return `
    <div class="glass-card">
      <div style="font-size:11px;color:var(--text-muted);display:flex;justify-content:space-between;margin-bottom:6px;">
        <span>${m.league} · ${m.date}</span><span>${m.bookmaker.split(' ')[0]}</span>
      </div>
      <div style="font-size:15px;font-weight:800;margin-bottom:8px;">${m.home} vs ${m.away}</div>
      <div class="pred-row">
        <span style="font-size:13px;font-weight:700;color:var(--accent-cyan);">${m.principal} (${m.principal_pct}%)</span>
        <span class="risk-tag risk-${m.risc}">${m.risc}</span>
      </div>
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">xG Evaluat: Gazde <b>${m.exp_goals_home}</b> | Oaspeți <b>${m.exp_goals_away}</b></div>
      <button class="btn" style="width:100%;font-size:11px;padding:6px;background:rgba(6,182,212,0.15);" onclick="this.nextElementSibling.style.display='block';this.style.display='none';">Vezi BetBuilder Interactiv</button>
      <div style="display:none;margin-top:8px;border-top:1px dashed var(--card-border);padding-top:8px;">
        ${getBB(m.exp_goals_home, m.exp_goals_away).map(b => `<div style="display:flex;justify-content:space-between;font-size:12px;padding:4px 0;"><span>${b.combo}</span><span style="color:var(--accent-cyan);font-weight:700;">${b.pct}%</span></div>`).join('') || '<div style="font-size:11px;color:var(--text-muted);">Fără combinații sigure.</div>'}
      </div>
    </div>`;
}

function render() {
  const c = document.getElementById('content');
  if(!state.matches.length) { c.innerHTML = '<div class="glass-card" style="text-align:center;">Niciun meci procesat azi.</div>'; return; }
  
  if(currentTab === 'toate') {
    c.innerHTML = state.matches.map(renderCard).join('');
  } else if(currentTab === 'challenge') {
    if(!state.challenge) { c.innerHTML = '<div class="glass-card">Nu s-a putut forma un bilet sigur de 1.50.</div>'; return; }
    let legs = state.challenge.selections.map(s => `<div style="display:flex;justify-content:space-between;font-size:12px;padding:8px 0;border-bottom:1px solid var(--card-border);"><span><b>${s.home} vs ${s.away}</b><br><span style="color:var(--accent-cyan);">${s.pick}</span></span><span style="font-weight:700;">${s.pct}%</span></div>`).join('');
    c.innerHTML = `<div class="glass-card" style="border-color:var(--accent-gold);"><div style="font-size:20px;font-weight:800;color:var(--accent-gold);text-align:center;margin-bottom:10px;">COTA ${state.challenge.target_odd}</div>${legs}</div>`;
  } else if(currentTab === 'betbuilder') {
    const bbMatches = state.matches.filter(m => m.betbuilder && m.betbuilder.length > 0);
    c.innerHTML = bbMatches.length ? bbMatches.map(m => `
      <div class="glass-card">
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;">${m.league} · ${m.date}</div>
        <div style="font-size:14px;font-weight:800;margin-bottom:8px;">${m.home} vs ${m.away}</div>
        ${m.betbuilder.map(b => `<div style="display:flex;justify-content:space-between;font-size:12px;padding:4px 0;"><span>${b.combo}</span><span style="color:var(--accent-cyan);font-weight:700;">${b.pct}%</span></div>`).join('')}
      </div>`).join('') : '<div class="glass-card" style="text-align:center;">Nu există date pentru BetBuilder.</div>';
  }
}

function switchTab(t, btn) { currentTab = t; document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); render(); }

async function fetchAPI(url, options) {
  try {
    document.getElementById('status').innerText = 'Se procesează algoritmul...';
    const res = await fetch(url, options);
    if(url === '/api/predictions' && !res.ok) throw new Error('Nu sunt date.');
    const data = await res.json();
    if(data.status === 'success' || url === '/api/predictions') {
      if(url !== '/api/predictions') return fetchAPI('/api/predictions');
      state = data; document.getElementById('status').innerText = `Încărcat cu succes (${state.matches.length} meciuri).`; render();
    } else { document.getElementById('status').innerText = 'Eroare: ' + data.message; }
  } catch(e) { document.getElementById('status').innerText = 'Eroare conexiune server.'; }
}

function uploadCSV() {
  const file = document.getElementById('csvFile').files[0];
  if(!file) return;
  const fd = new FormData(); fd.append('file', file);
  fetchAPI('/api/upload-csv', { method: 'POST', body: fd });
}
function syncGithub() { fetchAPI('/api/refresh-from-github', { method: 'POST' }); }

fetchAPI('/api/predictions');
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
