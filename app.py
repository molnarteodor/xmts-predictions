import os
import json
import math
import csv
import io
import urllib.request
import threading
from datetime import datetime, timedelta
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
MAX_ROWS = 1000

FIXTURES_CSV_URL = os.environ.get("FIXTURES_CSV_URL", "")
# Adaugam EL.csv in lista de fisiere urmarite
TARGET_STATS_FILES = ["E0.csv", "SP1.csv", "I1.csv", "D1.csv", "F1.csv", "E1.csv", "SP2.csv", "I2.csv", "D2.csv", "CL.csv", "EL1.csv"]

CONFIDENCE_THRESHOLD = 0.50
LOW_RISK_THRESHOLD = 0.65

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
    "CL": "UEFA Champions League", "EL": "UEFA Europa League"
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
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            # Daca contine si ora, extragem doar data
            if " " in date_str and ":" in date_str and fmt == "%d/%m/%Y %H:%M":
                dt = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
                return dt.strftime("%Y-%m-%d")
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str

def parse_uk_time(date_str):
    date_str = (date_str or "").strip()
    if " " in date_str and ":" in date_str:
        try:
            dt = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
            return dt.strftime("%H:%M")
        except ValueError:
            pass
    return ""

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
        oh, od, oa = pinnacle
        return ph, pd, pa, "Pinnacle", oh, od, oa

    for h_key, d_key, a_key, _label in BOOKMAKER_1X2_COLUMNS:
        triplet = _valid_odds_triplet(row, h_key, d_key, a_key)
        if triplet:
            ph, pd, pa = implied_probs_sq(*triplet)
            oh, od, oa = triplet
            return ph, pd, pa, _label, oh, od, oa

    avg = _valid_odds_triplet(row, "AvgH", "AvgD", "AvgA")
    if avg:
        ph, pd, pa = implied_probs_sq(*avg)
        oh, od, oa = avg
        return ph, pd, pa, "Medie Globală", oh, od, oa

    return 0.38, 0.28, 0.34, "Estimare Model", 2.15, 3.30, 3.10

def extract_ou25_odds(row):
    for over_key, under_key in OU25_PRIORITY:
        try:
            o_over = float(row.get(over_key) or 0)
            o_under = float(row.get(under_key) or 0)
            if o_over > 1.01 and o_under > 1.01:
                return o_over, o_under
        except (ValueError, TypeError):
            continue
    return 1.85, 1.85

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
    odds_data = extract_1x2_odds(row)
    if not odds_data:
        return None
    p_h, p_d, p_a, bookmaker, oh, od, oa = odds_data

    ou = extract_ou25_odds(row)
    o_over_val, o_under_val = ou
    sr_over = math.sqrt(1.0/o_over_val)
    sr_under = math.sqrt(1.0/o_under_val)
    target_over25 = sr_over / (sr_over + sr_under)

    lam_h, lam_a = calibrate_lambdas(p_h, p_d, p_a, rho_league, target_over25)

    max_g = 10
    p_home = p_draw = p_away = p_btts = 0.0
    p_over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    p_under = {2.5: 0.0}

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
            if tot <= 2.5: p_under[2.5] += p
            if tot > 3.5: p_over[3.5] += p
            if h > 0 and a > 0: p_btts += p

    total_prob = p_home + p_draw + p_away
    p_home /= total_prob
    p_draw /= total_prob
    p_away /= total_prob

    if target_over25 is not None:
        p_over[2.5] = target_over25
        p_under[2.5] = max(0.01, 1.0 - target_over25)
    p_over[1.5] = max(p_over[1.5], p_over[2.5])
    
    lam_h_ht = lam_h * 0.45
    lam_a_ht = lam_a * 0.45
    p_over05_ht = 1.0 - (math.exp(-lam_h_ht) * math.exp(-lam_a_ht))
    
    odd_1x = round(1.0 / max(0.05, (p_home + p_draw * 0.9)), 2)
    odd_x2 = round(1.0 / max(0.05, (p_away + p_draw * 0.9)), 2)

    home_name = (row.get("HomeTeam") or row.get("Home Team") or "Gazde").strip()
    away_name = (row.get("AwayTeam") or row.get("Away Team") or "Oaspeți").strip()

    market_options = [
        {"name": f"1 ({home_name})", "prob": p_home, "odds": oh},
        {"name": "X (Egal)", "prob": p_draw, "odds": od},
        {"name": f"2 ({away_name})", "prob": p_away, "odds": oa},
        {"name": "Șansă Dublă 1X", "prob": p_home + p_draw, "odds": odd_1x},
        {"name": "Șansă Dublă X2", "prob": p_draw + p_away, "odds": odd_x2},
        {"name": "Peste 2.5 goluri", "prob": p_over[2.5], "odds": o_over_val},
        {"name": "Sub 2.5 goluri", "prob": p_under[2.5], "odds": o_under_val},
        {"name": "GG - Ambele marchează", "prob": p_btts, "odds": 1.90}
    ]

    filtered_for_main = {
        f"1 ({home_name})": p_home,
        "X (Egal)": p_draw,
        f"2 ({away_name})": p_away,
        "Șansă Dublă 1X": p_home + p_draw,
        "Șansă Dublă X2": p_draw + p_away,
        "Peste 2.5 goluri": p_over[2.5],
        "Sub 2.5 goluri": p_under[2.5],
        "GG - Ambele marchează": p_btts
    }

    best_market = max(filtered_for_main, key=filtered_for_main.get)
    best_p = filtered_for_main[best_market]

    result = {
        "principal": best_market,
        "principal_pct": round(best_p * 100, 1),
        "exp_goals_home": round(lam_h, 2),
        "exp_goals_away": round(lam_a, 2),
        "bookmaker": bookmaker,
        "league_rho": rho_league,
        "market_options": market_options,
        "probs": {
            "home": round(p_home * 100, 1),
            "draw": round(p_draw * 100, 1),
            "away": round(p_away * 100, 1),
            "over15": round(p_over[1.5] * 100, 1),
            "over25": round(p_over[2.5] * 100, 1),
            "under25": round(p_under[2.5] * 100, 1),
            "btts": round(p_btts * 100, 1),
            "over05_ht": round(p_over05_ht * 100, 1)
        }
    }

    if best_p >= LOW_RISK_THRESHOLD:
        result["risc"] = "Scăzut"
    elif best_p >= CONFIDENCE_THRESHOLD:
        result["risc"] = "Mediu"
    else:
        result["risc"] = "Ridicat"

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

def process_csv_content(csv_text, filename=""):
    reader = csv.DictReader(io.StringIO(csv_text))
    processed = []
    skipped_no_odds = 0
    existing_stats = _load_json(STATS_CACHE_FILE, {})

    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            break
        
        # Suport pentru ambele formate (Football-Data clasic sau Open Football cu Home Team)
        home = (row.get("HomeTeam") or row.get("Home Team") or "").strip()
        away = (row.get("AwayTeam") or row.get("Away Team") or "").strip()
        if not home or not away:
            continue
        
        league_code = (row.get("Div") or "").strip()
        if not league_code and "EL" in filename.upper():
            league_code = "EL"
        elif not league_code and "CL" in filename.upper():
            league_code = "CL"

        rho_val = DIXON_COLES_RHO_BASE
        if existing_stats and "__rhos__" in existing_stats:
            rho_val = existing_stats["__rhos__"].get(league_code, DIXON_COLES_RHO_BASE)

        pred = predict_from_odds(row, rho_val)
        if pred is None:
            skipped_no_odds += 1
            continue

        cc = estimate_corners_cards(home, away, existing_stats) if existing_stats else None
        
        if cc:
            c85 = cc['corners_over']['8.5'] / 100.0
            c95 = cc['corners_over']['9.5'] / 100.0
            cd35 = cc['cards_over']['3.5'] / 100.0
            
            odd_c85 = round(1.0 / max(0.05, c85 * 0.95), 2)
            odd_c95 = round(1.0 / max(0.05, c95 * 0.95), 2)
            odd_cd35 = round(1.0 / max(0.05, cd35 * 0.95), 2)

            if c85 >= 0.50 and odd_c85 <= 2.20:
                pred["market_options"].append({"name": "Peste 8.5 cornere", "prob": c85, "odds": odd_c85})
            if c95 >= 0.45 and odd_c95 <= 2.60:
                pred["market_options"].append({"name": "Peste 9.5 cornere", "prob": c95, "odds": odd_c95})
            if cd35 >= 0.50 and odd_cd35 <= 2.20:
                pred["market_options"].append({"name": "Peste 3.5 cartonașe", "prob": cd35, "odds": odd_cd35})

        league_name = LEAGUE_NAMES.get(league_code, league_code)
        if "EL" in filename.upper() and league_code == "EL":
            league_name = "UEFA Europa League"

        raw_date = row.get("Date") or row.get("Match Date") or ""
        match_date = parse_uk_date(raw_date)
        match_time = parse_uk_time(raw_date) or (row.get("Time") or "").strip()

        # Verificam scorul final (suport pentru FTHG sau coloane cu scor direct in format open data)
        fthg = row.get("FTHG")
        ftag = row.get("FTAG")
        has_res = False
        res_h, res_a = None, None

        if fthg is not None and ftag is not None and str(fthg).strip() != "" and str(ftag).strip() != "":
            try:
                res_h = int(float(fthg))
                res_a = int(float(ftag))
                has_res = True
            except ValueError:
                pass

        is_cl = (league_code == "CL" or "CL" in filename.upper() or "Champions League" in league_name)
        is_el = (league_code == "EL" or "EL" in filename.upper() or "Europa League" in league_name)

        processed.append({
            "league": league_name, "is_cl": is_cl, "is_el": is_el, "date": match_date,
            "time": match_time, "home": home, "away": away,
            "has_result": has_res, "res_home": res_h, "res_away": res_a,
            "corners_cards": cc, **pred
        })

    processed.sort(key=lambda m: -(m.get("principal_pct") or 0))
    processed.sort(key=lambda m: m["date"])
    return processed, skipped_no_odds

def _build_fixtures_cache(base_url):
    all_matches = []
    total_skipped = 0
    existing_stats = _load_json(STATS_CACHE_FILE, {})

    for stat_file in TARGET_STATS_FILES:
        try:
            url = f"{base_url}/{stat_file}" if base_url else stat_file
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode('utf-8')
                matches, skipped = process_csv_content(content, filename=stat_file)
                all_matches.extend(matches)
                total_skipped += skipped
        except Exception as e:
            print(f"Eroare citire {stat_file}: {e}")

    all_matches.sort(key=lambda m: -(m.get("principal_pct") or 0))
    all_matches.sort(key=lambda m: m["date"])

    cache_data = {
        "uploaded_at": datetime.now().isoformat(),
        "upload_date": today_str(),
        "matches": all_matches,
        "skipped_no_odds": total_skipped,
        "api_active": True,
        "source": "github_multi",
        "stats_uploaded": len(existing_stats) > 0
    }
    _save_json(CACHE_FILE, cache_data)
    return cache_data

def update_team_stats_from_csv(content, team_stats):
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        h = (row.get("HomeTeam") or row.get("Home Team") or "").strip()
        a = (row.get("AwayTeam") or row.get("Away Team") or "").strip()
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
    if not FIXTURES_CSV_URL:
        return
    try:
        base_url = FIXTURES_CSV_URL.rsplit('/', 1)[0]
        team_stats = {"__leagues__": {}, "__rhos__": {}}
        for stat_file in TARGET_STATS_FILES:
            try:
                url = f"{base_url}/{stat_file}"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    content = resp.read().decode('utf-8')
                    team_stats = update_team_stats_from_csv(content, team_stats)
            except Exception:
                pass
        if len(team_stats) > 2:
            team_stats = compute_dynamic_rho(team_stats)
            _save_json(STATS_CACHE_FILE, team_stats)
            
        _build_fixtures_cache(base_url)
    except Exception as e:
        print(f"Eroare GitHub Auto-Sync: {e}")

@app.route('/api/refresh-from-github', methods=['POST'])
def refresh_from_github():
    thread = threading.Thread(target=fetch_data_from_github_auto)
    thread.start()
    return jsonify({"status": "success", "message": "Sincronizare pornită."})

@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    data = _load_json(CACHE_FILE, None)
    if not data or not data.get("matches"):
        if FIXTURES_CSV_URL:
            base_url = FIXTURES_CSV_URL.rsplit('/', 1)[0]
            _build_fixtures_cache(base_url)
            data = _load_json(CACHE_FILE, None)
    return jsonify(data or {"matches": [], "api_active": False})

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
    --accent-cyan: #06b6d4; --accent-gold: #eab308; --accent-orange: #f97316; --text-main: #f8fafc; 
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
  
  .tabs-wrapper { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 10px; margin-bottom: 10px; scrollbar-width: none; }
  .tabs-wrapper::-webkit-scrollbar { display: none; }
  .tab-btn { background: #1f1f1f; border: 1px solid var(--card-border); color: var(--text-muted); padding: 8px 12px; border-radius: 10px; font-weight: 600; white-space: nowrap; cursor: pointer; font-size: 12px; }
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

  .ticket-config { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 15px; }
  .odds-btn { background: #222; border: 1px solid var(--card-border); color: #fff; padding: 8px 12px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 13px; }
  .odds-btn.active { background: var(--accent-gold); color: #000; border-color: var(--accent-gold); }
  .ticket-match-row { display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; margin-bottom: 8px; font-size: 13px; }

  .date-picker-bar { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 12px; scrollbar-width: none; }
  .date-picker-bar::-webkit-scrollbar { display: none; }
  .date-chip { background: #1f1f1f; border: 1px solid var(--card-border); color: var(--text-muted); padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: bold; white-space: nowrap; cursor: pointer; }
  .date-chip.active { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }

  .result-badge { font-weight: 800; font-size: 11px; padding: 2px 6px; border-radius: 4px; margin-left: 6px; }
  .res-win { background: rgba(34, 197, 94, 0.2); color: #22c55e; border: 1px solid #22c55e; }
  .res-loss { background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
  .res-pending { background: rgba(148, 163, 184, 0.1); color: #94a3b8; }
</style>
</head>
<body>
<div class="container">
  <div style="text-align:center; margin-bottom:15px; font-size:22px; font-weight:800; color:var(--accent-gold);">
    XMTS PREDICTIONS
  </div>

  <div class="tabs-wrapper">
    <button class="tab-btn active" onclick="switchTab('meciuri', this)">⚽ Naționale</button>
    <button class="tab-btn" onclick="switchTab('cl', this)" style="border-color:var(--accent-cyan); color:var(--accent-cyan);">🏆 UCL</button>
    <button class="tab-btn" onclick="switchTab('el', this)" style="border-color:var(--accent-orange); color:var(--accent-orange);">🇪🇺 UEL</button>
    <button class="tab-btn" onclick="switchTab('bilete', this)" style="border-color:var(--accent-gold); color:var(--accent-gold);">🎟️ Bilete</button>
  </div>

  <div id="dateSelectorContainer"></div>
  <div id="content"><div class="glass-card" style="text-align:center;">Se încarcă datele...</div></div>
</div>

<script>
let state = { matches: [], stats_uploaded: false };
let currentTab = 'meciuri';
let selectedDate = getTodayStr();
let selectedClDate = '';
let selectedElDate = '';
let selectedTargetOdds = 10;

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

function evaluatePrediction(m, marketName) {
  if (!m.has_result) return { status: 'pending' };
  
  const h = m.res_home;
  const a = m.res_away;
  const tot = h + a;
  
  if (marketName.includes("1 (Gazde)")) return h > a ? {status: 'win'} : {status: 'loss'};
  if (marketName.includes("X (Egal)")) return h === a ? {status: 'win'} : {status: 'loss'};
  if (marketName.includes("2 (Oaspeți)")) return a > h ? {status: 'win'} : {status: 'loss'};
  if (marketName.includes("Șansă Dublă 1X")) return h >= a ? {status: 'win'} : {status: 'loss'};
  if (marketName.includes("Șansă Dublă X2")) return a >= h ? {status: 'win'} : {status: 'loss'};
  if (marketName.includes("Peste 2.5")) return tot > 2.5 ? {status: 'win'} : {status: 'loss'};
  if (marketName.includes("Sub 2.5")) return tot <= 2.5 ? {status: 'win'} : {status: 'loss'};
  if (marketName.includes("GG")) return (h > 0 && a > 0) ? {status: 'win'} : {status: 'loss'};
  
  return { status: 'pending' };
}

function renderMatchCard(m) {
  const p = m.probs;
  const avgH = m.exp_goals_home;
  const avgA = m.exp_goals_away;
  
  const pronostic = m.principal || "Echilibrat";
  const pronostic_pct = m.principal_pct || "-";

  const evalRes = evaluatePrediction(m, pronostic);
  let badgeHtml = '';
  if (m.has_result) {
    badgeHtml = evalRes.status === 'win' ? `<span class="result-badge res-win">✔ CÂȘTIGAT (${m.res_home}-${m.res_away})</span>` : `<span class="result-badge res-loss">✖ PIERDUT (${m.res_home}-${m.res_away})</span>`;
  } else {
    badgeHtml = `<span class="result-badge res-pending">⏳ Viitor</span>`;
  }

  let cardsHtml = '';
  let cornersHtml = '';
  if (m.corners_cards) {
      const cc = m.corners_cards;
      cardsHtml = `Estimat meci: ~<b style="color:#fff;">${cc.exp_cards}</b> cartonașe.<br>Peste 3.5: <b style="color:var(--accent-gold)">${cc.cards_over['3.5']}%</b>`;
      cornersHtml = `Estimat meci: ~<b style="color:#fff;">${cc.exp_corners}</b> cornere.<br>Peste 8.5: <b style="color:var(--accent-gold)">${cc.corners_over['8.5']}%</b>`;
  } else {
      cardsHtml = `Fără date istorice cartonașe.`;
      cornersHtml = `Fără date istorice cornere.`;
  }

  return `
    <div class="glass-card">
      <div class="match-basic">
        <div style="font-size:11px;color:var(--text-muted);display:flex;justify-content:space-between;">
          <span>${m.league} · ${m.date} ${m.time || ''}</span>
          <span>${badgeHtml}</span>
        </div>
        <div style="font-size:16px;font-weight:800;text-align:center; margin-top:4px;">${m.home} VS ${m.away}</div>
        
        <div class="pred-row" style="margin-top:6px;">
          <span style="font-size:13px;font-weight:700;color:#fff;">
            ⭐ ${pronostic} <span style="color:var(--accent-gold);">(${pronostic_pct}%)</span>
          </span>
          <span class="risk-tag risk-${m.risc}">${m.risc}</span>
        </div>
      </div>

      <button class="btn-expand" onclick="toggleGoldenPanel(this)">Deschide Analiză Detaliată</button>
      
      <div class="golden-panel">
        <div class="team-logos">
          <div class="t-badge"><div class="t-badge-circle">${m.home.substring(0,3).toUpperCase()}</div><div style="font-size:11px;font-weight:bold;">${m.home.toUpperCase()}</div></div>
          <div style="font-size:12px;font-weight:bold;color:var(--text-muted);">VS</div>
          <div class="t-badge"><div class="t-badge-circle">${m.away.substring(0,3).toUpperCase()}</div><div style="font-size:11px;font-weight:bold;">${m.away.toUpperCase()}</div></div>
        </div>

        <div class="golden-header">STATISTICS (PROBABILITĂȚI)</div>
        <div class="h2h-row"><div class="h2h-val">${avgH}</div><div class="h2h-label">Expected Goals (xG)</div><div class="h2h-val">${avgA}</div></div>

        <div class="bars-section">
          <div class="bar-row"><div class="bar-label">1 (Gazde):</div><div class="bar-track"><div class="bar-fill" style="width: ${p.home}%;">${p.home}%</div></div></div>
          <div class="bar-row"><div class="bar-label">X (Egal):</div><div class="bar-track"><div class="bar-fill" style="width: ${p.draw}%; background:#3b82f6;">${p.draw}%</div></div></div>
          <div class="bar-row"><div class="bar-label">2 (Oaspeți):</div><div class="bar-track"><div class="bar-fill" style="width: ${p.away}%; background:#a855f7;">${p.away}%</div></div></div>
          <div class="bar-row"><div class="bar-label">Over 1.5:</div><div class="bar-track"><div class="bar-fill" style="width: ${p.over15}%;">${p.over15}%</div></div></div>
          <div class="bar-row"><div class="bar-label">Over 2.5:</div><div class="bar-track"><div class="bar-fill" style="width: ${p.over25}%;">${p.over25}%</div></div></div>
          <div class="bar-row"><div class="bar-label">Both Score:</div><div class="bar-track"><div class="bar-fill" style="width: ${p.btts}%;">${p.btts}%</div></div></div>
        </div>

        <div style="margin-top: 20px;">
          <div class="acc-item"><div class="acc-header" onclick="toggleAccordion(this)"><div>🟨 Cartonașe</div><div>▼</div></div><div class="acc-body">${cardsHtml}</div></div>
          <div class="acc-item"><div class="acc-header" onclick="toggleAccordion(this)"><div>🚩 Cornere</div><div>▼</div></div><div class="acc-body">${cornersHtml}</div></div>
        </div>
      </div>
    </div>`;
}

function renderDateSelector() {
  const matches = (state.matches || []).filter(m => {
    if (currentTab === 'cl') return m.is_cl;
    if (currentTab === 'el') return m.is_el;
    return !m.is_cl && !m.is_el;
  });
  
  const datesSet = [...new Set(matches.map(m => m.date))].sort();
  
  if (datesSet.length > 0) {
    if (currentTab === 'cl') {
      if (!selectedClDate || !datesSet.includes(selectedClDate)) selectedClDate = datesSet[0];
    } else if (currentTab === 'el') {
      if (!selectedElDate || !datesSet.includes(selectedElDate)) selectedElDate = datesSet[0];
    } else {
      if (!selectedDate || !datesSet.includes(selectedDate)) {
        selectedDate = datesSet.includes(getTodayStr()) ? getTodayStr() : datesSet[0];
      }
    }
  }

  let activeD = (currentTab === 'cl') ? selectedClDate : (currentTab === 'el' ? selectedElDate : selectedDate);

  let chips = datesSet.map(d => `
    <button class="date-chip ${activeD === d ? 'active' : ''}" onclick="selectDate('${d}')">${d}</button>
  `).join('');

  return `<div class="date-picker-bar">${chips || '<span style="font-size:12px;color:var(--text-muted)">Nicio dată disponibilă</span>'}</div>`;
}

function selectDate(d) {
  if (currentTab === 'cl') selectedClDate = d;
  else if (currentTab === 'el') selectedElDate = d;
  else selectedDate = d;
  render();
}

function renderTicketGenerator() {
  const activeD = (currentTab === 'cl') ? selectedClDate : (currentTab === 'el' ? selectedElDate : selectedDate);
  const matches = (state.matches || []).filter(m => {
    if (currentTab === 'cl') return m.is_cl && m.date === activeD && !m.has_result;
    if (currentTab === 'el') return m.is_el && m.date === activeD && !m.has_result;
    return !m.is_cl && !m.is_el && m.date === activeD && !m.has_result;
  });
  
  let pool = [];
  matches.forEach(m => {
    if (m.market_options) {
      m.market_options.forEach(opt => {
        if (opt.prob >= 0.50 && opt.odds >= 1.20 && opt.odds <= 3.80) {
          pool.push({
            match: `${m.home} - ${m.away}`,
            league: m.league,
            date: m.date,
            market: opt.name,
            odds: opt.odds,
            prob: opt.prob,
            score: opt.prob * (1.0 / Math.max(0.1, Math.abs(opt.odds - 1.7)))
          });
        }
      });
    }
  });

  pool.sort((a, b) => b.score - a.score);

  let selectedPicks = [];
  let currentOdds = 1.0;
  
  for (let item of pool) {
    if (selectedPicks.length >= 15) break;
    if (selectedPicks.some(p => p.match === item.match)) continue;

    if (currentOdds < selectedTargetOdds) {
      selectedPicks.push(item);
      currentOdds *= item.odds;
    } else {
      break;
    }
  }

  let oddsButtons = [5, 10, 20, 50, 100, 250, 500].map(val => 
    `<button class="odds-btn ${selectedTargetOdds === val ? 'active' : ''}" onclick="setTargetOdds(${val})">Cotă ${val}</button>`
  ).join('');

  let picksHtml = selectedPicks.map((p, idx) => `
    <div class="ticket-match-row">
      <div>
        <div style="font-weight:bold; color:#fff;">${idx+1}. ${p.match}</div>
        <div style="font-size:11px; color:var(--text-muted);">${p.league}</div>
        <div style="font-size:12px; color:var(--accent-cyan); margin-top:2px;">👉 <b>${p.market}</b></div>
      </div>
      <div style="text-align:right;">
        <div style="font-weight:800; font-size:15px; color:var(--accent-gold);">@${p.odds}</div>
        <div style="font-size:10px; color:#34d399;">Prob: ${Math.round(p.prob*100)}%</div>
      </div>
    </div>
  `).join('');

  return `
    <div class="glass-card">
      <div style="font-weight:800; font-size:16px; margin-bottom:10px; color:var(--accent-gold);">🎟️ Generator Bilete (${activeD || 'General'})</div>
      <div style="font-size:12px; color:var(--text-muted); margin-bottom:15px;">Construiește biletul inteligent.</div>
      
      <div class="ticket-config">${oddsButtons}</div>

      <div style="background:rgba(0,0,0,0.5); border:1px solid var(--card-border); border-radius:12px; padding:12px; margin-top:15px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid #333; padding-bottom:8px;">
          <span style="font-weight:bold; font-size:13px;">Cotă Țintă: ~${selectedTargetOdds}</span>
          <span style="background:var(--accent-gold); color:#000; font-weight:800; padding:4px 10px; border-radius:8px; font-size:14px;">Cotă Totală: ${currentOdds.toFixed(2)}</span>
        </div>
        ${picksHtml || '<div style="text-align:center; padding:20px; color:var(--text-muted);">Nu sunt suficiente meciuri viitoare pentru această cotă în data selectată.</div>'}
        <div style="font-size:10px; color:var(--text-muted); text-align:center; margin-top:10px;">Selecții: ${selectedPicks.length} (Max 15)</div>
      </div>
    </div>
  `;
}

function setTargetOdds(val) {
  selectedTargetOdds = val;
  render();
}

function render() {
  const dateContainer = document.getElementById('dateSelectorContainer');
  const c = document.getElementById('content');
  
  if (!state.matches || !state.matches.length) { 
    dateContainer.innerHTML = '';
    c.innerHTML = '<div class="glass-card" style="text-align:center;">Nu există date. Sincronizează cu GitHub.</div>'; 
    return; 
  }
  
  dateContainer.innerHTML = renderDateSelector();
  
  const activeD = (currentTab === 'cl') ? selectedClDate : (currentTab === 'el' ? selectedElDate : selectedDate);
  const matches = (state.matches || []).filter(m => {
    if (currentTab === 'cl') return m.is_cl && m.date === activeD;
    if (currentTab === 'el') return m.is_el && m.date === activeD;
    return !m.is_cl && !m.is_el && m.date === activeD;
  });
  
  if (currentTab === 'meciuri' || currentTab === 'cl' || currentTab === 'el') {
    c.innerHTML = matches.length ? matches.map(renderMatchCard).join('') : `<div class="glass-card" style="text-align:center;">Niciun meci în data de ${activeD || 'selectată'}. Alege altă etapă/zi din bară.</div>`;
  } else if (currentTab === 'bilete') {
    c.innerHTML = renderTicketGenerator();
  }
}

function switchTab(t, btn) { 
    currentTab = t; 
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active')); 
    btn.classList.add('active'); 
    render(); 
}

async function fetchAPI() {
  try {
    const res = await fetch('/api/predictions');
    const data = await res.json(); 
    state = data; 
    render();
  } catch(e) { console.error(e); }
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
