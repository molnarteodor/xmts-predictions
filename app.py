import os
import json
import math
import csv
import io
import urllib.request
import threading
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bucharest")
except Exception:
    TZ = None

def today_str():
    if TZ:
        return datetime.now(TZ).strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")

app = Flask(__name__)
CORS(app)

CACHE_FILE = "matches_cache.json"
STATS_CACHE_FILE = "team_stats_cache.json"
MAX_ROWS = 600

# ==========================================
# CONFIGURARE GITHUB AUTO-SYNC
# ==========================================
# Aici punem baza linkului tau de github (raw content)
# URL-ul complet catre fixtures.csv trebuie sa fie dat prin Environment Variable in Render
FIXTURES_CSV_URL = os.environ.get("FIXTURES_CSV_URL", "")

# Ligile pentru care vom incerca sa tragem automat istoricul de pe GitHub
# Presupunem ca fisierele de istoric se afla in acelasi folder cu fixtures.csv pe GitHub
TARGET_STATS_FILES = ["E0.csv", "SP1.csv", "I1.csv", "D1.csv", "F1.csv", "E1.csv", "SP2.csv", "I2.csv", "D2.csv"]

CONFIDENCE_THRESHOLD = 0.65
LOW_RISK_THRESHOLD = 0.75
FALLBACK_MIN_CONFIDENCE = 0.55

CORNERS_LINES = [8.5, 9.5, 10.5]
CARDS_LINES = [3.5, 4.5, 5.5]

PINNACLE_1X2 = ("PSH", "PSD", "PSA")
BOOKMAKER_1X2_COLUMNS = [
    ("B365H", "B365D", "B365A", "Bet365"),
    ("BWH", "BWD", "BWA", "Bwin"),
    ("IWH", "IWD", "IWA", "Interwetten"),
    ("WHH", "WHD", "WHA", "William Hill"),
    ("VCH", "VCD", "VCA", "BetVictor"),
]
OU25_PRIORITY = [("B365>2.5", "B365<2.5"), ("Avg>2.5", "Avg<2.5")]

LEAGUE_NAMES = {
    "E0": "Premier League (Anglia)", "E1": "Championship (Anglia)",
    "E2": "League One (Anglia)", "E3": "League Two (Anglia)", 
    "EC": "National League", "SC0": "Premiership (Scoția)", 
    "SC1": "Championship (Scoția)", "SP1": "La Liga (Spania)", 
    "SP2": "La Liga 2", "D1": "Bundesliga (Germania)", 
    "D2": "Bundesliga 2", "I1": "Serie A (Italia)", 
    "I2": "Serie B (Italia)", "F1": "Ligue 1 (Franța)", 
    "F2": "Ligue 2 (Franța)", "N1": "Eredivisie (Olanda)", 
    "B1": "Jupiler League (Belgia)", "P1": "Primeira Liga (Por)", 
    "T1": "Super Lig (Turcia)", "G1": "Super League (Grecia)",
}

DIXON_COLES_RHO_BASE = -0.08

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
    except Exception:
        pass

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

def implied_probs_sq(oh, od, oa):
    raw_h = math.sqrt(1.0 / oh)
    raw_d = math.sqrt(1.0 / od)
    raw_a = math.sqrt(1.0 / oa)
    total = raw_h + raw_d + raw_a
    return raw_h / total, raw_d / total, raw_a / total

def extract_1x2_odds(row):
    pinnacle = _valid_odds_triplet(row, *PINNACLE_1X2)
    if pinnacle:
        ph, pd, pa = implied_probs_sq(*pinnacle)
        return ph, pd, pa, "Pinnacle"

    probs = []
    for h_key, d_key, a_key, _label in BOOKMAKER_1X2_COLUMNS:
        triplet = _valid_odds_triplet(row, h_key, d_key, a_key)
        if triplet:
            probs.append(implied_probs_sq(*triplet))

    if probs:
        n = float(len(probs))
        sum_h = sum([p[0] for p in probs])
        sum_d = sum([p[1] for p in probs])
        sum_a = sum([p[2] for p in probs])
        return (sum_h / n), (sum_d / n), (sum_a / n), "Medie Case"

    avg = _valid_odds_triplet(row, "AvgH", "AvgD", "AvgA")
    if avg:
        ph, pd, pa = implied_probs_sq(*avg)
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

def poisson_pmf(k, lam):
    lam_safe = max(lam, 0.01)
    return math.exp(-lam_safe) * (lam_safe ** k) / math.factorial(k)

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

def _match_probs_from_lambdas(lam_h, lam_a, max_g, rho, over_line=None):
    p_h = p_d = p_a = p_over = 0.0
    for h in range(max_g):
        for a in range(max_g):
            p = poisson_pmf(h, lam_h) * poisson_pmf(a, lam_a)
            p = p * dixon_coles_tau(h, a, lam_h, lam_a, rho)
            if h > a: p_h += p
            elif h == a: p_d += p
            else: p_a += p
            
            if over_line is not None and (h + a) > over_line:
                p_over += p
    return p_h, p_d, p_a, p_over

def calibrate_lambdas(target_h, target_d, target_a, rho, target_over25=None):
    best = (1.4, 1.1)
    best_err = 999.0
    for i in range(10):
        lh = round(0.4 + i * 0.4, 2)
        for j in range(8):
            la = round(0.4 + j * 0.4, 2)
            ph, pd, pa, p_over25 = _match_probs_from_lambdas(lh, la, max_g=7, rho=rho, over_line=2.5)
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
            ph, pd, pa, p_over25 = _match_probs_from_lambdas(lh, la, max_g=9, rho=rho, over_line=2.5)
            err = (ph - target_h)**2 + (pd - target_d)**2 + (pa - target_a)**2
            if target_over25 is not None:
                err += ((p_over25 - target_over25)**2) * 1.5
            if err < best_err:
                best_err = err
                best = (lh, la)
    return round(best[0], 2), round(best[1], 2)

def predict_from_odds(row, rho_league):
    odds_1x2 = extract_1x2_odds(row)
    if not odds_1x2:
        return None
    p_h, p_d, p_a, bookmaker = odds_1x2

    ou = extract_ou25_odds(row)
    target_over25 = None
    if ou:
        o_over, o_under = ou
        sr_over = math.sqrt(1.0/o_over)
        sr_under = math.sqrt(1.0/o_under)
        target_over25 = sr_over / (sr_over + sr_under)

    lam_h, lam_a = calibrate_lambdas(p_h, p_d, p_a, rho_league, target_over25)

    max_g = 10
    p_home = p_draw = p_away = p_btts = 0.0
    p_over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}

    for h in range(max_g):
        for a in range(max_g):
            p = poisson_pmf(h, lam_h) * poisson_pmf(a, lam_a)
            p = p * dixon_coles_tau(h, a, lam_h, lam_a, rho_league)
            if h > a: p_home += p
            elif h == a: p_draw += p
            else: p_away += p
            
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
    
    lam_h_ht = lam_h * 0.45
    lam_a_ht = lam_a * 0.45
    p_over05_ht = 1.0 - (math.exp(-lam_h_ht) * math.exp(-lam_a_ht))
    
    lam_h_st = lam_h * 0.55
    lam_a_st = lam_a * 0.55
    p_over05_st = 1.0 - (math.exp(-lam_h_st) * math.exp(-lam_a_st))

    markets = {
        "1 (Gazde)": p_home, "X (Egal)": p_draw, "2 (Oaspeți)": p_away,
        "Peste 2.5 goluri": p_over[2.5], "Sub 2.5 goluri": max(0.01, 1.0 - p_over[2.5]),
        "GG - Da": p_btts
    }
    fallback = [("Șansă Dublă 1X", p_home + p_draw), ("Șansă Dublă X2", p_draw + p_away)]

    best_market = max(markets, key=markets.get)
    best_p = markets[best_market]

    result = {
        "principal": best_market,
        "principal_pct": round(best_p * 100, 1),
        "exp_goals_home": round(lam_h, 2),
        "exp_goals_away": round(lam_a, 2),
        "bookmaker": bookmaker,
        "league_rho": rho_league,
        "probs": {
            "over15": round(p_over[1.5] * 100, 1), "over25": round(p_over[2.5] * 100, 1),
            "btts": round(p_btts * 100, 1), "over05_ht": round(p_over05_ht * 100, 1),
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

def _decay_avg(values, alpha=0.85):
    if not values: return 0.0
    num, den = 0.0, 0.0
    rev_vals = list(reversed(values))
    for i, val in enumerate(rev_vals):
        w = alpha ** i
        num += val * w
        den += w
    return num / den

def estimate_corners_cards(home_team, away_team, team_stats):
    h = team_stats.get(home_team)
    a = team_stats.get(away_team)
    if not h or not a:
        return None
    if len(h.get("cf_h", [])) < 1 or len(a.get("cf_a", [])) < 1:
        return None

    h_cf_avg = _decay_avg(h["cf_h"])
    h_ca_avg = _decay_avg(h["ca_h"])
    a_cf_avg = _decay_avg(a["cf_a"])
    a_ca_avg = _decay_avg(a["ca_a"])
    
    h_cards_avg = _decay_avg(h["cards_h"])
    a_cards_avg = _decay_avg(a["cards_a"])

    exp_corners = (h_cf_avg + a_ca_avg) / 2.0 + (a_cf_avg + h_ca_avg) / 2.0
    exp_cards = h_cards_avg + a_cards_avg

    def over_prob(exp_val, line):
        return sum(poisson_pmf(k, exp_val) for k in range(math.ceil(line), 25))

    return {
        "exp_corners": round(exp_corners, 1),
        "exp_cards": round(exp_cards, 1),
        "corners_over": {str(l): round(over_prob(exp_corners, l) * 100, 1) for l in CORNERS_LINES},
        "cards_over": {str(l): round(over_prob(exp_cards, l) * 100, 1) for l in CARDS_LINES},
        "sample": len(h["cf_h"]) + len(a["cf_a"])
    }

def process_csv_content(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    processed = []
    skipped_no_odds = 0
    existing_stats = _load_json(STATS_CACHE_FILE, {})

    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            break
        home = (row.get("HomeTeam") or "").strip()
        away = (row.get("AwayTeam") or "").strip()
        if not home or not away:
            continue
        
        league_code = (row.get("Div") or "").strip()
        rho_val = DIXON_COLES_RHO_BASE
        
        if existing_stats and "__rhos__" in existing_stats:
            rho_val = existing_stats["__rhos__"].get(league_code, DIXON_COLES_RHO_BASE)

        pred = predict_from_odds(row, rho_val)
        if pred is None:
            skipped_no_odds += 1
            continue

        cc = estimate_corners_cards(home, away, existing_stats) if existing_stats else None
        league_name = LEAGUE_NAMES.get(league_code, league_code)
        
        processed.append({
            "league": league_name, "date": parse_uk_date(row.get("Date")),
            "time": (row.get("Time") or "").strip(), "home": home, "away": away,
            "corners_cards": cc, **pred
        })

    processed.sort(key=lambda m: -(m.get("principal_pct") or 0))
    processed.sort(key=lambda m: m["date"])
    return processed, skipped_no_odds

def _build_fixtures_cache(content, source):
    matches, skipped = process_csv_content(content)
    existing_stats = _load_json(STATS_CACHE_FILE, {})
    cache_data = {
        "uploaded_at": datetime.now().isoformat(),
        "upload_date": today_str(),
        "matches": matches,
        "skipped_no_odds": skipped,
        "api_active": True,
        "source": source,
        "stats_uploaded": len(existing_stats) > 0
    }
    _save_json(CACHE_FILE, cache_data)
    return cache_data

def update_team_stats_from_csv(content, team_stats):
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        h = (row.get("HomeTeam") or "").strip()
        a = (row.get("AwayTeam") or "").strip()
        if not h or not a: continue
        
        div = (row.get("Div") or "").strip()
        fthg_s, ftag_s = row.get("FTHG"), row.get("FTAG")
        if fthg_s and ftag_s:
            try:
                hg, ag = float(fthg_s), float(ftag_s)
                if div not in team_stats["__leagues__"]:
                    team_stats["__leagues__"][div] = {"hg": [], "ag": []}
                team_stats["__leagues__"][div]["hg"].append(hg)
                team_stats["__leagues__"][div]["ag"].append(ag)
            except ValueError:
                pass

        try:
            hc, ac = float(row.get("HC") or 0), float(row.get("AC") or 0)
            hy, ay = float(row.get("HY") or 0), float(row.get("AY") or 0)
            hr, ar = float(row.get("HR") or 0), float(row.get("AR") or 0)
        except (ValueError, TypeError):
            continue
        
        if h not in team_stats: team_stats[h] = {"cf_h":[], "ca_h":[], "cards_h":[], "cf_a":[], "ca_a":[], "cards_a":[]}
        if a not in team_stats: team_stats[a] = {"cf_h":[], "ca_h":[], "cards_h":[], "cf_a":[], "ca_a":[], "cards_a":[]}
        
        team_stats[h]["cf_h"].append(hc)
        team_stats[h]["ca_h"].append(ac)
        team_stats[h]["cards_h"].append(hy + hr)
        team_stats[a]["cf_a"].append(ac)
        team_stats[a]["ca_a"].append(hc)
        team_stats[a]["cards_a"].append(ay + ar)
    return team_stats

def compute_dynamic_rho(team_stats):
    for div, goals in team_stats["__leagues__"].items():
        hg, ag = goals["hg"], goals["ag"]
        n = len(hg)
        if n > 20:
            mean_h, mean_a = sum(hg)/n, sum(ag)/n
            cov = sum((hg[i]-mean_h)*(ag[i]-mean_a) for i in range(n)) / n
            var_h = sum((x-mean_h)**2 for x in hg) / n
            var_a = sum((x-mean_a)**2 for x in ag) / n
            if var_h > 0 and var_a > 0:
                corr = cov / math.sqrt(var_h * var_a)
                rho = max(-0.20, min(0.10, corr))
            else:
                rho = DIXON_COLES_RHO_BASE
        else:
            rho = DIXON_COLES_RHO_BASE
        team_stats["__rhos__"][div] = round(rho, 3)
    return team_stats

def fetch_data_from_github_auto():
    """Functia care se declanseaza automat in spate cand serverul porneste cu memoria goala"""
    if not FIXTURES_CSV_URL:
        return
    
    try:
        # Extragem baza link-ului GitHub (folderul in care se afla fixtures.csv)
        base_url = FIXTURES_CSV_URL.rsplit('/', 1)[0]
        
        # 1. Tragem istoricul (E0.csv, SP1.csv, etc.)
        team_stats = {"__leagues__": {}, "__rhos__": {}}
        for stat_file in TARGET_STATS_FILES:
            try:
                url = f"{base_url}/{stat_file}"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    content = resp.read().decode('utf-8')
                    team_stats = update_team_stats_from_csv(content, team_stats)
            except Exception:
                pass # Ignoram fisierele care nu exista pe GitHub
        
        if len(team_stats) > 2:
            team_stats = compute_dynamic_rho(team_stats)
            _save_json(STATS_CACHE_FILE, team_stats)
            
        # 2. Tragem fixtures.csv si actualizam meciurile folosind noul istoric
        req = urllib.request.Request(FIXTURES_CSV_URL, headers={'User-Agent': 'Mozilla'})
        with urllib.request.urlopen(req, timeout=10) as response:
            csv_data = response.read().decode('utf-8')
            _build_fixtures_cache(csv_data, "github_auto")
    except Exception as e:
        print(f"Eroare GitHub Auto-Sync: {e}")

@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files: return jsonify({"status": "error"}), 400
    file = request.files['file']
    try:
        content = file.read().decode('utf-8', errors='ignore')
        c = _build_fixtures_cache(content, "upload_manual")
        return jsonify({"status": "success", "count": len(c["matches"]), "skipped": c["skipped_no_odds"]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/upload-stats-csv', methods=['POST'])
def upload_stats_csv():
    files = request.files.getlist('files')
    team_stats = _load_json(STATS_CACHE_FILE, {"__leagues__": {}, "__rhos__": {}})
    for f in files:
        content = f.read().decode('utf-8', errors='ignore')
        team_stats = update_team_stats_from_csv(content, team_stats)
    
    team_stats = compute_dynamic_rho(team_stats)
    _save_json(STATS_CACHE_FILE, team_stats)
    
    cache = _load_json(CACHE_FILE, None)
    if cache and cache.get("matches"):
        for m in cache["matches"]: m["corners_cards"] = estimate_corners_cards(m["home"], m["away"], team_stats)
        cache["stats_uploaded"] = True
        _save_json(CACHE_FILE, cache)
    return jsonify({"status": "success"})

@app.route('/api/refresh-from-github', methods=['POST'])
def refresh_from_github():
    # Acest buton acum face sincronizare totala
    thread = threading.Thread(target=fetch_data_from_github_auto)
    thread.start()
    return jsonify({"status": "success", "message": "Sincronizare in fundal pornita. Reimprospateaza pagina in 10 secunde."})

@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    data = _load_json(CACHE_FILE, None)
    
    # Auto-Sync: Daca datele nu exista pe server (serverul a repornit) 
    if not data or not data.get("matches"):
        if FIXTURES_CSV_URL:
            # Rulam descarcarea de pe GitHub, blocand putin API-ul ca sa apuce sa traga datele
            fetch_data_from_github_auto()
            # Incarcam datele din nou
            data = _load_json(CACHE_FILE, None)
            
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
    --accent-cyan: #06b6d4; --accent-gold: #eab308; --text-main: #f8fafc; 
    --text-muted: #94a3b8; --bar-green: #22c55e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
  body { background: var(--bg-dark); color: var(--text-main); padding: 10px; }
  .container { max-width: 580px; margin: 0 auto; }
  
  .glass-card {
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 16px; padding: 16px; margin-bottom: 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  }
  
  .upload-area { border: 1px dashed var(--card-border); text-align: center; }
  .btn { background: var(--accent-cyan); color: #fff; border: none; padding: 10px 14px; border-radius: 10px; font-weight: bold; cursor: pointer; display: inline-block; }
  
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
  }

  .golden-panel { display: none; margin-top: 15px; padding-top: 15px; border-top: 1px dashed var(--card-border); }
  .golden-header { text-align: center; color: var(--accent-gold); font-size: 18px; font-weight: 800; margin-bottom: 15px; text-transform: uppercase; }
  
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
  .bar-track { flex: 1; background: rgba(255,255,255,0.05); border-radius: 12px; height: 18px; position: relative; }
  .bar-fill { height: 100%; background: var(--bar-green); border-radius: 12px; display: flex; justify-content: flex-end; align-items: center; padding-right: 8px; color: #fff; font-size: 10px; }
  
  .acc-item { background: #1a1a1a; border: 1px solid var(--accent-gold); border-radius: 10px; margin-bottom: 10px; }
  .acc-header { padding: 12px 15px; display: flex; justify-content: space-between; cursor: pointer; color: #fff; font-weight: bold; }
  .acc-body { padding: 10px 15px; border-top: 1px solid #333; font-size: 12px; color: var(--text-muted); display: none; }
</style>
</head>
<body>
<div class="container">
  <div style="text-align:center; margin-bottom:15px; font-size:22px; font-weight:800; color:var(--accent-gold);">
    XMTS PREDICTIONS
  </div>

  <div class="glass-card upload-area">
    <div style="margin-bottom:10px; font-weight:700;">📂 Administrare Manuală</div>
    <div style="font-size:11px;color:var(--text-muted);margin-bottom:15px;">Dacă datele sunt încărcate pe GitHub, serverul se va sincroniza singur. Poți forța sincronizarea din butonul de mai jos.</div>
    <button class="btn" style="background:#3b82f6; width:100%;" onclick="syncGithub()">🔄 Forțează Sincronizarea cu GitHub</button>
    <div id="status" style="font-size:12px; margin-top:10px; color:var(--text-muted);">Așteptare date...</div>
  </div>

  <div class="tabs-wrapper">
    <button class="tab-btn active" onclick="switchTab('azi', this)">🗓️ Azi</button>
    <button class="tab-btn" onclick="switchTab('toate', this)">📋 Toate Zilele</button>
  </div>

  <div id="content"><div class="glass-card" style="text-align:center;">Așteaptă încărcarea datelor...</div></div>
</div>

<script>
let state = { matches: [], stats_uploaded: false };
let currentTab = 'azi';

function getTodayStr() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
}

function toggleGoldenPanel(btn) {
  const panel = btn.nextElementSibling;
  const isHidden = panel.style.display === 'none' || panel.style.display === '';
  panel.style.display = isHidden ? 'block' : 'none';
  btn.innerText = isHidden ? 'Ascunde Analiză' : 'Deschide Analiză Detaliată';
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

  const val_HT_H = Math.min(100, Math.round(p.over05_ht * (avgH / (avgH + avgA + 0.1)) * 1.5)).toFixed(2);
  const val_HT_A = Math.min(100, Math.round(p.over05_ht * (avgA / (avgH + avgA + 0.1)) * 1.5)).toFixed(2);
  const val_ST_H = Math.min(100, Math.round(p.over05_st * (avgH / (avgH + avgA + 0.1)) * 1.5)).toFixed(2);
  const val_ST_A = Math.min(100, Math.round(p.over05_st * (avgA / (avgH + avgA + 0.1)) * 1.5)).toFixed(2);
  const val_o15_H = Math.min(100, Math.round((avgH / 2) * 100)).toFixed(2);
  const val_o15_A = Math.min(100, Math.round((avgA / 2) * 100)).toFixed(2);
  
  const pronostic = m.principal || m.alternativ || "Echilibrat";
  const pronostic_pct = m.principal_pct || m.alternativ_pct || "-";

  let cardsHtml = '';
  let cornersHtml = '';
  
  if (m.corners_cards) {
      const cc = m.corners_cards;
      cardsHtml = `
        Estimat meci: ~<b style="color:#fff;">${cc.exp_cards}</b> cartonașe.<br>
        Peste 3.5: <b style="color:var(--accent-gold)">${cc.cards_over['3.5']}%</b><br>
        Peste 4.5: <b style="color:var(--accent-gold)">${cc.cards_over['4.5']}%</b><br>
        Peste 5.5: <b style="color:var(--accent-gold)">${cc.cards_over['5.5']}%</b><br>
        <i style="font-size:10px;">Model Cronologic Izolat (Eșantion: ${cc.sample} meciuri).</i>`;
      cornersHtml = `
        Estimat meci: ~<b style="color:#fff;">${cc.exp_corners}</b> cornere.<br>
        Peste 8.5: <b style="color:var(--accent-gold)">${cc.corners_over['8.5']}%</b><br>
        Peste 9.5: <b style="color:var(--accent-gold)">${cc.corners_over['9.5']}%</b><br>
        Peste 10.5: <b style="color:var(--accent-gold)">${cc.corners_over['10.5']}%</b><br>
        <i style="font-size:10px;">Model Cronologic Izolat (Eșantion: ${cc.sample} meciuri).</i>`;
  } else {
      if (state.stats_uploaded) {
          const noDataMsg = `<span style="color:var(--accent-gold)">⚠️ Nu există date suficiente în istoric (necesar min. 1 meci acasă pt gazdă și 1 în deplasare pt oaspete).</span>`;
          cardsHtml = noDataMsg;
          cornersHtml = noDataMsg;
      } else {
          const needFileMsg = `<i>Datele exacte necesită prezența fișierelor istorice pe GitHub.</i>`;
          cardsHtml = `Estimat global: ~4.5 cartonașe.<br>${needFileMsg}`;
          cornersHtml = `Estimat global: ~9.5 cornere.<br>${needFileMsg}`;
      }
  }

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
            ⭐ ${pronostic} <span style="color:var(--accent-gold);">(${pronostic_pct}%)</span>
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
        <div class="h2h-row"><div class="h2h-val gold">${val_HT_H}%</div><div class="h2h-label">Team Over 0.5 HT</div><div class="h2h-val gold">${val_HT_A}%</div></div>
        <div class="h2h-row"><div class="h2h-val gold">${val_ST_H}%</div><div class="h2h-label">Team Over 0.5 ST</div><div class="h2h-val gold">${val_ST_A}%</div></div>
        <div class="h2h-row"><div class="h2h-val gold">${val_o15_H}%</div><div class="h2h-label">Team Over 1.5 Goals</div><div class="h2h-val gold">${val_o15_A}%</div></div>

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
              <div>🟨 Cartonașe</div><div>▼</div>
            </div>
            <div class="acc-body" style="line-height:1.6;">${cardsHtml}</div>
          </div>
          <div class="acc-item">
            <div class="acc-header" onclick="toggleAccordion(this)">
              <div>🚩 Cornere</div><div>▼</div>
            </div>
            <div class="acc-body" style="line-height:1.6;">${cornersHtml}</div>
          </div>
        </div>
      </div>
    </div>`;
}

function render() {
  const c = document.getElementById('content');
  if(!state.matches || !state.matches.length) { 
    c.innerHTML = '<div class="glass-card" style="text-align:center;">Nu există date. Asigură-te că ai urcat fixtures.csv pe GitHub.</div>'; 
    return; 
  }
  
  const today = getTodayStr();
  const todayMatches = state.matches.filter(m => m.date === today);
  
  if(currentTab === 'azi') {
    if(todayMatches.length) {
      c.innerHTML = todayMatches.map(renderMatchCard).join('');
    } else {
      c.innerHTML = `<div class="glass-card" style="text-align:center;">Nu sunt meciuri programate pentru azi (${today}).<br><br>Vezi secțiunea "Toate Zilele".</div>`;
    }
  } else if(currentTab === 'toate') {
    c.innerHTML = state.matches.map(renderMatchCard).join('');
  }
}

function switchTab(t, btn) { 
    currentTab = t; 
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active')); 
    btn.classList.add('active'); 
    render(); 
}

async function fetchAPI(url = '/api/predictions', options = {}) {
  try {
    const s = document.getElementById('status');
    if(s) s.innerText = 'Se extrag datele...';
    
    const res = await fetch(url, options);
    const data = await res.json(); 
    
    if(data.status === 'success' || url === '/api/predictions') {
        if(url !== '/api/predictions') {
            // Asteptam putin sa se termine sincronizarea din fundal si reluam datele
            setTimeout(() => { fetchAPI('/api/predictions'); }, 2000);
            return;
        }
        state = data; 
        if(s) s.innerText = `Sistem activ. ${state.matches ? state.matches.length : 0} meciuri gasite.`; 
        render();
    }
  } catch(e) { 
    const s = document.getElementById('status');
    if(s) s.innerText = 'Sistem pregatit.';
  }
}

function syncGithub() { 
  const s = document.getElementById('status');
  if(s) s.innerText = 'Se conectează la GitHub... (dureaza 5 secunde)';
  fetchAPI('/api/refresh-from-github', { method: 'POST' }); 
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
