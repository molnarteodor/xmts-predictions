import os
import re
import json
import math
import csv
import io
import hashlib
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
MAX_ROWS = 2000

FIXTURES_CSV_URL = os.environ.get("FIXTURES_CSV_URL", "")
TARGET_STATS_FILES = [
    "E0.csv", "SP1.csv", "I1.csv", "D1.csv", "F1.csv",
    "E1.csv", "SP2.csv", "I2.csv", "D2.csv", "CL.csv", "EL.csv"
]

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

ELITE_TEAMS_BOOST = {
    "real madrid": 0.45, "bayern munich": 0.45, "manchester city": 0.45, "man city": 0.45,
    "fc barcelona": 0.45, "barcelona": 0.45, "liverpool": 0.42, "liverpool fc": 0.42,
    "paris saint-germain": 0.42, "paris sg": 0.42, "arsenal": 0.40, "arsenal fc": 0.40,
    "inter": 0.35, "borussia dortmund": 0.32, "dortmund": 0.32, "leverkusen": 0.35,
    "atletico madrid": 0.30, "atlético madrid": 0.30, "juventus": 0.30, "milan": 0.30,
    "ssc napoli": 0.30, "napoli": 0.30, "manchester united": 0.28, "man utd": 0.28,
    "aston villa": 0.28, "sporting cp": 0.28, "sporting": 0.28, "benfica": 0.28,
    "fc porto": 0.25, "rb leipzig": 0.25, "as roma": 0.25, "roma": 0.25,
    "real sociedad": 0.22, "villarreal cf": 0.22, "villarreal": 0.22, "real betis": 0.22,
    "marseille": 0.22, "lyon": 0.20, "psv eindhoven": 0.20, "feyenoord": 0.18,
    "galatasaray": 0.18, "fenerbahçe": 0.18, "fenerbahce": 0.18, "celtic": 0.18
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
    if not date_str:
        return ""
    if " " in date_str:
        date_str = date_str.split(" ")[0].strip()

    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str

def parse_uk_time(date_str):
    date_str = (date_str or "").strip()
    if " " in date_str and ":" in date_str:
        parts = date_str.split(" ")
        for p in parts[1:]:
            if ":" in p:
                return p.strip()[:5]
    return ""

def parse_result_string(res_str):
    """Parsează scoruri din formatul '0 - 2' sau scoruri afectate de Excel ('4-Jan', 'Jan-00')."""
    if not res_str:
        return None, None
    s = str(res_str).strip()
    if not s or s == "-":
        return None, None

    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }

    m = re.match(r"^(\d+)\s*[-:]\s*(\d+)$", s)
    if m:
        return int(m.group(1)), int(m.group(2))

    parts = re.split(r"[-/]", s)
    if len(parts) == 2:
        p1, p2 = parts[0].strip().lower(), parts[1].strip().lower()
        if p1 in month_map and p2.isdigit():
            return month_map[p1], int(p2)
        if p1.isdigit() and p2 in month_map:
            return int(p1), month_map[p2]

    return None, None

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

def estimate_synthetic_odds(home_name, away_name, team_stats):
    """Generează cote și probabilități dinamice când meciul nu are cote în CSV."""
    h_low = home_name.lower()
    a_low = away_name.lower()

    h_boost = ELITE_TEAMS_BOOST.get(h_low, 0.0)
    a_boost = ELITE_TEAMS_BOOST.get(a_low, 0.0)

    # Adăugăm variație deterministă bazată pe numele echipei ca să nu existe două meciuri identice
    h_hash = (int(hashlib.md5(h_low.encode("utf-8")).hexdigest()[:6], 16) % 100) / 250.0
    a_hash = (int(hashlib.md5(a_low.encode("utf-8")).hexdigest()[:6], 16) % 100) / 250.0

    h_stat = team_stats.get(home_name, {}) if team_stats else {}
    a_stat = team_stats.get(away_name, {}) if team_stats else {}

    h_gf = _decay_avg(h_stat.get("gf_h", [])) if h_stat.get("gf_h") else (1.35 + h_boost + h_hash)
    h_ga = _decay_avg(h_stat.get("ga_h", [])) if h_stat.get("ga_h") else max(0.65, 1.15 - h_boost * 0.5)
    a_gf = _decay_avg(a_stat.get("gf_a", [])) if a_stat.get("gf_a") else (1.15 + a_boost + a_hash)
    a_ga = _decay_avg(a_stat.get("ga_a", [])) if a_stat.get("ga_a") else max(0.70, 1.30 - a_boost * 0.5)

    lam_h = max(0.55, min(3.10, (h_gf + a_ga) / 2.0 + 0.12))
    lam_a = max(0.45, min(2.90, (a_gf + h_ga) / 2.0 - 0.05))

    ph, pd, pa, p_over25 = _match_probs_from_lambdas(lam_h, lam_a, max_g=9, rho=DIXON_COLES_RHO_BASE, over_line=2.5)
    tot = ph + pd + pa
    ph, pd, pa = ph / tot, pd / tot, pa / tot

    oh = round(max(1.18, min(9.50, 0.95 / max(0.08, ph))), 2)
    od = round(max(2.80, min(6.50, 0.95 / max(0.12, pd))), 2)
    oa = round(max(1.22, min(11.0, 0.95 / max(0.08, pa))), 2)
    o_over = round(max(1.35, min(2.70, 0.95 / max(0.20, p_over25))), 2)
    o_under = round(max(1.35, min(2.70, 0.95 / max(0.20, 1.0 - p_over25))), 2)

    return ph, pd, pa, "Model AI", oh, od, oa, o_over, o_under

def extract_1x2_odds(row, home_name="", away_name="", team_stats=None):
    pinnacle = _valid_odds_triplet(row, *PINNACLE_1X2)
    if pinnacle:
        ph, pd, pa = implied_probs_sq(*pinnacle)
        oh, od, oa = pinnacle
        return ph, pd, pa, "Pinnacle", oh, od, oa, None, None

    for h_key, d_key, a_key, _label in BOOKMAKER_1X2_COLUMNS:
        triplet = _valid_odds_triplet(row, h_key, d_key, a_key)
        if triplet:
            ph, pd, pa = implied_probs_sq(*triplet)
            oh, od, oa = triplet
            return ph, pd, pa, _label, oh, od, oa, None, None

    avg = _valid_odds_triplet(row, "AvgH", "AvgD", "AvgA")
    if avg:
        ph, pd, pa = implied_probs_sq(*avg)
        oh, od, oa = avg
        return ph, pd, pa, "Medie Globală", oh, od, oa, None, None

    return estimate_synthetic_odds(home_name, away_name, team_stats)

def extract_ou25_odds(row, synth_over=None, synth_under=None):
    for over_key, under_key in OU25_PRIORITY:
        try:
            o_over = float(row.get(over_key) or 0)
            o_under = float(row.get(under_key) or 0)
            if o_over > 1.01 and o_under > 1.01:
                return o_over, o_under
        except (ValueError, TypeError):
            continue
    if synth_over and synth_under:
        return synth_over, synth_under
    return 1.85, 1.95

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
            if h > a:
                p_h += p
            elif h == a:
                p_d += p
            else:
                p_a += p

            if over_line is not None and (h + a) > over_line:
                p_over += p
    return p_h, p_d, p_a, p_over

def calibrate_lambdas(target_h, target_d, target_a, rho, target_over25=None):
    best = (1.4, 1.1)
    best_err = 999.0
    for i in range(10):
        lh = round(0.4 + i * 0.35, 2)
        for j in range(10):
            la = round(0.4 + j * 0.35, 2)
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

def predict_from_odds(row, rho_league, team_stats=None):
    home_name = (row.get("HomeTeam") or row.get("Home Team") or "Gazde").strip()
    away_name = (row.get("AwayTeam") or row.get("Away Team") or "Oaspeți").strip()

    odds_data = extract_1x2_odds(row, home_name, away_name, team_stats)
    if not odds_data:
        return None
    p_h, p_d, p_a, bookmaker, oh, od, oa, synth_over, synth_under = odds_data

    o_over_val, o_under_val = extract_ou25_odds(row, synth_over, synth_under)
    sr_over = math.sqrt(1.0 / o_over_val)
    sr_under = math.sqrt(1.0 / o_under_val)
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
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p

            tot = h + a
            if tot > 1.5:
                p_over[1.5] += p
            if tot > 2.5:
                p_over[2.5] += p
            if tot <= 2.5:
                p_under[2.5] += p
            if tot > 3.5:
                p_over[3.5] += p
            if h > 0 and a > 0:
                p_btts += p

    total_prob = p_home + p_draw + p_away
    p_home /= total_prob
    p_draw /= total_prob
    p_away /= total_prob

    if target_over25 is not None:
        p_over[2.5] = (p_over[2.5] + target_over25) / 2.0
        p_under[2.5] = max(0.01, 1.0 - p_over[2.5])
    p_over[1.5] = max(p_over[1.5], p_over[2.5])

    lam_h_ht = lam_h * 0.45
    lam_a_ht = lam_a * 0.45
    p_over05_ht = 1.0 - (math.exp(-lam_h_ht) * math.exp(-lam_a_ht))

    odd_1x = round(1.0 / max(0.05, (p_home + p_draw) * 0.95), 2)
    odd_x2 = round(1.0 / max(0.05, (p_away + p_draw) * 0.95), 2)
    odd_btts = round(1.0 / max(0.05, p_btts * 0.95), 2)

    market_options = [
        {"name": f"1 ({home_name})", "prob": p_home, "odds": oh},
        {"name": "X (Egal)", "prob": p_draw, "odds": od},
        {"name": f"2 ({away_name})", "prob": p_away, "odds": oa},
        {"name": "Șansă Dublă 1X", "prob": p_home + p_draw, "odds": odd_1x},
        {"name": "Șansă Dublă X2", "prob": p_draw + p_away, "odds": odd_x2},
        {"name": "Peste 2.5 goluri", "prob": p_over[2.5], "odds": o_over_val},
        {"name": "Sub 2.5 goluri", "prob": p_under[2.5], "odds": o_under_val},
        {"name": "GG - Ambele marchează", "prob": p_btts, "odds": odd_btts}
    ]

    # Selecție inteligentă și diversificată pentru pronosticul principal
    # (penalizăm ușor șansa dublă ca să nu monopolizeze toate meciurile)
    candidates = {
        f"1 ({home_name})": (p_home, p_home * 1.12 if p_home >= 0.52 else p_home),
        f"2 ({away_name})": (p_away, p_away * 1.12 if p_away >= 0.52 else p_away),
        "Peste 2.5 goluri": (p_over[2.5], p_over[2.5] * 1.08 if p_over[2.5] >= 0.55 else p_over[2.5]),
        "Sub 2.5 goluri": (p_under[2.5], p_under[2.5] * 1.05 if p_under[2.5] >= 0.58 else p_under[2.5] * 0.95),
        "GG - Ambele marchează": (p_btts, p_btts * 1.08 if p_btts >= 0.56 else p_btts),
        "Șansă Dublă 1X": (p_home + p_draw, (p_home + p_draw) * 0.86),
        "Șansă Dublă X2": (p_draw + p_away, (p_draw + p_away) * 0.86),
        "X (Egal)": (p_draw, p_draw * 1.05 if p_draw >= 0.34 else p_draw)
    }

    best_market = max(candidates, key=lambda k: candidates[k][1])
    best_p = candidates[best_market][0]

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
    if not values:
        return 0.0
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

def _get_csv_reader(csv_text):
    first_line = csv_text.splitlines()[0] if csv_text else ""
    delimiter = "\t" if "\t" in first_line and "," not in first_line else ","
    return csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)

def process_csv_content(csv_text, filename="", existing_stats=None):
    if existing_stats is None:
        existing_stats = _load_json(STATS_CACHE_FILE, {})

    reader = _get_csv_reader(csv_text)
    rows = list(reader)
    if len(rows) > MAX_ROWS:
        rows = rows[-MAX_ROWS:]

    processed = []
    skipped_no_odds = 0

    for row in rows:
        home = (row.get("HomeTeam") or row.get("Home Team") or "").strip()
        away = (row.get("AwayTeam") or row.get("Away Team") or "").strip()
        if not home or not away:
            continue

        league_code = (row.get("Div") or "").strip()
        fname_up = filename.upper()
        if not league_code:
            if "EL" in fname_up:
                league_code = "EL"
            elif "CL" in fname_up:
                league_code = "CL"
            else:
                league_code = fname_up.replace(".CSV", "")

        rho_val = DIXON_COLES_RHO_BASE
        if existing_stats and "__rhos__" in existing_stats:
            rho_val = existing_stats["__rhos__"].get(league_code, DIXON_COLES_RHO_BASE)

        pred = predict_from_odds(row, rho_val, existing_stats)
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

        raw_date = row.get("Date") or row.get("Match Date") or ""
        match_date = parse_uk_date(raw_date)
        match_time = (row.get("Time") or "").strip() or parse_uk_time(raw_date)

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
        elif row.get("Result"):
            rh, ra = parse_result_string(row.get("Result"))
            if rh is not None and ra is not None:
                res_h, res_a = rh, ra
                has_res = True

        is_cl = (league_code == "CL" or "CL.CSV" in fname_up or "Champions League" in league_name)
        is_el = (league_code == "EL" or "EL.CSV" in fname_up or "Europa League" in league_name)

        processed.append({
            "league": league_name,
            "is_cl": is_cl,
            "is_el": is_el,
            "date": match_date,
            "time": match_time,
            "home": home,
            "away": away,
            "has_result": has_res,
            "res_home": res_h,
            "res_away": res_a,
            "corners_cards": cc,
            **pred
        })

    return processed, skipped_no_odds

def update_team_stats_from_csv(content, team_stats):
    reader = _get_csv_reader(content)
    for row in reader:
        h = (row.get("HomeTeam") or row.get("Home Team") or "").strip()
        a = (row.get("AwayTeam") or row.get("Away Team") or "").strip()
        if not h or not a:
            continue

        div = (row.get("Div") or "").strip()
        fthg_s, ftag_s = row.get("FTHG"), row.get("FTAG")
        hg, ag = None, None

        if fthg_s is not None and ftag_s is not None and str(fthg_s).strip() != "" and str(ftag_s).strip() != "":
            try:
                hg, ag = float(fthg_s), float(ftag_s)
            except ValueError:
                pass
        elif row.get("Result"):
            rh, ra = parse_result_string(row.get("Result"))
            if rh is not None and ra is not None:
                hg, ag = float(rh), float(ra)

        if h not in team_stats:
            team_stats[h] = {"cf_h": [], "ca_h": [], "cards_h": [], "cf_a": [], "ca_a": [], "cards_a": [], "gf_h": [], "ga_h": [], "gf_a": [], "ga_a": []}
        if a not in team_stats:
            team_stats[a] = {"cf_h": [], "ca_h": [], "cards_h": [], "cf_a": [], "ca_a": [], "cards_a": [], "gf_h": [], "ga_h": [], "gf_a": [], "ga_a": []}

        if hg is not None and ag is not None:
            if div:
                if div not in team_stats["__leagues__"]:
                    team_stats["__leagues__"][div] = {"hg": [], "ag": []}
                team_stats["__leagues__"][div]["hg"].append(hg)
                team_stats["__leagues__"][div]["ag"].append(ag)
            team_stats[h]["gf_h"].append(hg)
            team_stats[h]["ga_h"].append(ag)
            team_stats[a]["gf_a"].append(ag)
            team_stats[a]["ga_a"].append(hg)

        try:
            if row.get("HC") is not None and row.get("AC") is not None and str(row.get("HC")).strip() != "":
                hc, ac = float(row.get("HC") or 0), float(row.get("AC") or 0)
                hy, ay = float(row.get("HY") or 0), float(row.get("AY") or 0)
                hr, ar = float(row.get("HR") or 0), float(row.get("AR") or 0)
                team_stats[h]["cf_h"].append(hc)
                team_stats[h]["ca_h"].append(ac)
                team_stats[h]["cards_h"].append(hy + hr)
                team_stats[a]["cf_a"].append(ac)
                team_stats[a]["ca_a"].append(hc)
                team_stats[a]["cards_a"].append(ay + ar)
        except (ValueError, TypeError):
            continue

    return team_stats

def compute_dynamic_rho(team_stats):
    for div, goals in team_stats["__leagues__"].items():
        hg, ag = goals["hg"], goals["ag"]
        n = len(hg)
        if n > 20:
            mean_h, mean_a = sum(hg) / n, sum(ag) / n
            cov = sum((hg[i] - mean_h) * (ag[i] - mean_a) for i in range(n)) / n
            var_h = sum((x - mean_h) ** 2 for x in hg) / n
            var_a = sum((x - mean_a) ** 2 for x in ag) / n
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
        raw_files_content = {}

        # 1. Descărcăm fișierele pe ligi (inclusiv CL.csv și EL.csv)
        for stat_file in TARGET_STATS_FILES:
            try:
                url = f"{base_url}/{stat_file}"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    content = resp.read().decode('utf-8', errors='replace')
                    raw_files_content[stat_file] = content
                    team_stats = update_team_stats_from_csv(content, team_stats)
            except Exception as e:
                print(f"Info: Nu s-a putut descărca {stat_file}: {e}")

        # 2. Descărcăm și fixtures.csv principal
        fixtures_content = None
        try:
            req = urllib.request.Request(FIXTURES_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                fixtures_content = response.read().decode('utf-8', errors='replace')
                team_stats = update_team_stats_from_csv(fixtures_content, team_stats)
        except Exception as e:
            print(f"Info: Nu s-a putut descărca fixtures.csv: {e}")

        if len(team_stats) > 2:
            team_stats = compute_dynamic_rho(team_stats)
            _save_json(STATS_CACHE_FILE, team_stats)

        # 3. Construim lista unificată de meciuri (fără duplicate)
        matches_map = {}
        total_skipped = 0

        for stat_file, content in raw_files_content.items():
            m_list, skipped = process_csv_content(content, filename=stat_file, existing_stats=team_stats)
            total_skipped += skipped
            for m in m_list:
                key = f"{m['date']}_{m['home'].lower()}_{m['away'].lower()}"
                matches_map[key] = m

        if fixtures_content:
            m_list, skipped = process_csv_content(fixtures_content, filename="fixtures.csv", existing_stats=team_stats)
            total_skipped += skipped
            for m in m_list:
                key = f"{m['date']}_{m['home'].lower()}_{m['away'].lower()}"
                matches_map[key] = m

        all_matches = list(matches_map.values())
        all_matches.sort(key=lambda m: (m["date"], -(m.get("principal_pct") or 0)))

        cache_data = {
            "uploaded_at": datetime.now().isoformat(),
            "upload_date": today_str(),
            "matches": all_matches,
            "skipped_no_odds": total_skipped,
            "api_active": True,
            "source": "github_multi",
            "stats_uploaded": len(team_stats) > 2
        }
        _save_json(CACHE_FILE, cache_data)
    except Exception as e:
        print(f"Eroare GitHub Auto-Sync: {e}")

@app.route('/api/refresh-from-github', methods=['POST'])
def refresh_from_github():
    fetch_data_from_github_auto()
    data = _load_json(CACHE_FILE, {"matches": [], "api_active": False})
    return jsonify({"status": "success", "count": len(data.get("matches", []))})

@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    data = _load_json(CACHE_FILE, None)
    if not data or not data.get("matches"):
        if FIXTURES_CSV_URL:
            fetch_data_from_github_auto()
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
  
  .header-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
  .sync-btn {
    background: #1f1f1f; border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 6px 10px; border-radius: 8px; font-size: 11px; font-weight: 700; cursor: pointer;
  }
  .sync-btn:hover { border-color: var(--accent-gold); color: #fff; }

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

  .date-picker-bar { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 12px; scrollbar-width: none; scroll-behavior: smooth; }
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
  <div class="header-bar">
    <div style="font-size:20px; font-weight:800; color:var(--accent-gold);">XMTS PREDICTIONS</div>
    <button class="sync-btn" id="syncBtn" onclick="forceSync()">🔄 Sincronizează</button>
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
let selectedDate = '';
let selectedClDate = '';
let selectedElDate = '';
let selectedTargetOdds = 10;

function getTodayStr() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
}

function getSmartDefaultDate(datesSet) {
  if (!datesSet || !datesSet.length) return '';
  const today = getTodayStr();
  if (datesSet.includes(today)) return today;
  const nextUpcoming = datesSet.find(d => d >= today);
  if (nextUpcoming) return nextUpcoming;
  return datesSet[datesSet.length - 1];
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
  
  if (marketName.startsWith("1 (")) return h > a ? {status: 'win'} : {status: 'loss'};
  if (marketName.includes("X (Egal)")) return h === a ? {status: 'win'} : {status: 'loss'};
  if (marketName.startsWith("2 (")) return a > h ? {status: 'win'} : {status: 'loss'};
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
    badgeHtml = evalRes.status === 'win'
      ? `<span class="result-badge res-win">✔ CÂȘTIGAT (${m.res_home}-${m.res_away})</span>`
      : `<span class="result-badge res-loss">✖ PIERDUT (${m.res_home}-${m.res_away})</span>`;
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
        <div style="font-size:11px;color:var(--text-muted);display:flex;justify-content:space-between;align-items:center;">
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
  
  const datesSet = [...new Set(matches.map(m => m.date).filter(Boolean))].sort();
  
  if (datesSet.length > 0) {
    if (currentTab === 'cl') {
      if (!selectedClDate || !datesSet.includes(selectedClDate)) selectedClDate = getSmartDefaultDate(datesSet);
    } else if (currentTab === 'el') {
      if (!selectedElDate || !datesSet.includes(selectedElDate)) selectedElDate = getSmartDefaultDate(datesSet);
    } else {
      if (!selectedDate || !datesSet.includes(selectedDate)) selectedDate = getSmartDefaultDate(datesSet);
    }
  }

  let activeD = (currentTab === 'cl') ? selectedClDate : (currentTab === 'el' ? selectedElDate : selectedDate);

  let chips = datesSet.map(d => `
    <button class="date-chip ${activeD === d ? 'active' : ''}" id="chip-${d}" onclick="selectDate('${d}')">${d}</button>
  `).join('');

  setTimeout(() => {
    const activeChip = document.getElementById(`chip-${activeD}`);
    if (activeChip) activeChip.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }, 50);

  return `<div class="date-picker-bar">${chips || '<span style="font-size:12px;color:var(--text-muted)">Nicio dată disponibilă</span>'}</div>`;
}

function selectDate(d) {
  if (currentTab === 'cl') selectedClDate = d;
  else if (currentTab === 'el') selectedElDate = d;
  else selectedDate = d;
  render();
}

function renderTicketGenerator() {
  const activeD = selectedDate || selectedClDate || selectedElDate || getTodayStr();
  const matches = (state.matches || []).filter(m => m.date === activeD && !m.has_result);
  
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
      <div style="font-weight:800; font-size:16px; margin-bottom:10px; color:var(--accent-gold);">🎟️ Generator Bilete (${activeD})</div>
      <div style="font-size:12px; color:var(--text-muted); margin-bottom:15px;">Construiește biletul inteligent din toate competițiile zilei selectate.</div>
      
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
    c.innerHTML = '<div class="glass-card" style="text-align:center;">Nu există date încărcate. Apasă pe „🔄 Sincronizează” sus.</div>'; 
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
    c.innerHTML = matches.length
      ? matches.map(renderMatchCard).join('')
      : `<div class="glass-card" style="text-align:center;">Niciun meci găsit pentru ${activeD || 'această secțiune'}. Apasă pe „🔄 Sincronizează” dacă tocmai ai urcat fișierele pe GitHub.</div>`;
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

async function forceSync() {
  const btn = document.getElementById('syncBtn');
  btn.innerText = '⏳ Se sincronizează...';
  try {
    await fetch('/api/refresh-from-github', { method: 'POST' });
    await fetchAPI();
    btn.innerText = '✔ Sincronizat!';
    setTimeout(() => { btn.innerText = '🔄 Sincronizează'; }, 2000);
  } catch (e) {
    btn.innerText = '❌ Eroare';
  }
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
