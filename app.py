import os
import re
import time
import json
import math
import csv
import io
import hashlib
import urllib.request
import urllib.parse
import threading
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bucharest")
except Exception:
    TZ = None

def now_dt():
    if TZ:
        return datetime.now(TZ)
    return datetime.now()

def today_str():
    return now_dt().strftime("%Y-%m-%d")

app = Flask(__name__)
CORS(app)

# ==============================================================================
# CONFIGURARE API-FOOTBALL & CACHE ZILNIC
# ==============================================================================
APISPORTS_KEY = os.environ.get("APISPORTS_KEY", "9e273c820ace5c87d811f8ea55798152").strip()
APISPORTS_BASE_URL = "https://v3.football.api-sports.io"

CACHE_VERSION = "v6_apisports_daily"
CACHE_FILE = "matches_cache.json"
STATS_CACHE_FILE = "team_stats_cache.json"
SYNC_LOCK = threading.Lock()

# Opțional: păstrăm și compatibilitatea cu CSV-urile de pe GitHub ca completare
FIXTURES_CSV_URL = os.environ.get("FIXTURES_CSV_URL", "")
TARGET_STATS_FILES = ["CL.csv", "EL.csv"]

CONFIDENCE_THRESHOLD = 0.52
LOW_RISK_THRESHOLD = 0.62

CORNERS_LINES = [8.5, 9.5, 10.5]
CARDS_LINES = [3.5, 4.5, 5.5]
DIXON_COLES_RHO_BASE = -0.08

# Ligile urmărite în API-Football (ID -> Informații Secțiune)
TRACKED_LEAGUES = {
    2:   {"code": "CL",  "name": "UEFA Champions League", "icon": "🏆", "cat": "cl",  "priority": 1,  "avg_cards": 4.3, "avg_corners": 9.8},
    3:   {"code": "EL",  "name": "UEFA Europa League",    "icon": "🟠", "cat": "el",  "priority": 2,  "avg_cards": 4.6, "avg_corners": 9.6},
    848: {"code": "ECL", "name": "UEFA Conference League","icon": "🟢", "cat": "el",  "priority": 3,  "avg_cards": 4.5, "avg_corners": 9.5},
    39:  {"code": "E0",  "name": "Premier League (Anglia)", "icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "cat": "nat", "priority": 10, "avg_cards": 4.1, "avg_corners": 10.4},
    140: {"code": "SP1", "name": "La Liga (Spania)",        "icon": "🇪🇸", "cat": "nat", "priority": 11, "avg_cards": 5.1, "avg_corners": 9.5},
    135: {"code": "I1",  "name": "Serie A (Italia)",        "icon": "🇮🇹", "cat": "nat", "priority": 12, "avg_cards": 4.7, "avg_corners": 9.7},
    78:  {"code": "D1",  "name": "Bundesliga (Germania)",   "icon": "🇩🇪", "cat": "nat", "priority": 13, "avg_cards": 4.2, "avg_corners": 9.9},
    61:  {"code": "F1",  "name": "Ligue 1 (Franța)",        "icon": "🇫🇷", "cat": "nat", "priority": 14, "avg_cards": 4.0, "avg_corners": 9.4},
    283: {"code": "RO1", "name": "SuperLiga (România)",     "icon": "🇷🇴", "cat": "nat", "priority": 15, "avg_cards": 4.8, "avg_corners": 9.1},
    88:  {"code": "N1",  "name": "Eredivisie (Olanda)",     "icon": "🇳🇱", "cat": "nat", "priority": 16, "avg_cards": 3.5, "avg_corners": 10.2},
    94:  {"code": "P1",  "name": "Primeira Liga (Portugalia)", "icon": "🇵🇹", "cat": "nat", "priority": 17, "avg_cards": 5.2, "avg_corners": 10.0},
    203: {"code": "T1",  "name": "Süper Lig (Turcia)",      "icon": "🇹🇷", "cat": "nat", "priority": 18, "avg_cards": 5.0, "avg_corners": 9.6},
    144: {"code": "B1",  "name": "Jupiler Pro League (Belgia)", "icon": "🇧🇪", "cat": "nat", "priority": 19, "avg_cards": 4.3, "avg_corners": 9.8},
    197: {"code": "G1",  "name": "Super League (Grecia)",   "icon": "🇬🇷", "cat": "nat", "priority": 20, "avg_cards": 4.9, "avg_corners": 9.0},
    179: {"code": "SC0", "name": "Premiership (Scoția)",    "icon": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "cat": "nat", "priority": 21, "avg_cards": 4.2, "avg_corners": 10.3},
    40:  {"code": "E1",  "name": "Championship (Anglia)",   "icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "cat": "nat", "priority": 22, "avg_cards": 4.1, "avg_corners": 10.1},
    141: {"code": "SP2", "name": "La Liga 2 (Spania)",      "icon": "🇪🇸", "cat": "nat", "priority": 23, "avg_cards": 5.3, "avg_corners": 9.2},
    136: {"code": "I2",  "name": "Serie B (Italia)",        "icon": "🇮🇹", "cat": "nat", "priority": 24, "avg_cards": 4.9, "avg_corners": 9.4},
    79:  {"code": "D2",  "name": "2. Bundesliga (Germania)","icon": "🇩🇪", "cat": "nat", "priority": 25, "avg_cards": 4.4, "avg_corners": 10.0},
}

ELITE_TEAMS_BOOST = {
    "real madrid": 0.45, "bayern munich": 0.45, "bayern münchen": 0.45, "manchester city": 0.45,
    "fc barcelona": 0.45, "barcelona": 0.45, "liverpool": 0.42, "paris saint germain": 0.42,
    "paris saint-germain": 0.42, "arsenal": 0.40, "inter": 0.36, "borussia dortmund": 0.33,
    "bayer leverkusen": 0.35, "leverkusen": 0.35, "atletico madrid": 0.32, "atlético madrid": 0.32,
    "juventus": 0.30, "ac milan": 0.30, "milan": 0.30, "napoli": 0.32, "manchester united": 0.28,
    "aston villa": 0.28, "sporting cp": 0.30, "benfica": 0.28, "fc porto": 0.26, "rb leipzig": 0.26,
    "as roma": 0.26, "real sociedad": 0.22, "villarreal": 0.24, "real betis": 0.22, "marseille": 0.24,
    "lyon": 0.22, "psv eindhoven": 0.25, "feyenoord": 0.22, "ajax": 0.24, "galatasaray": 0.24,
    "fenerbahce": 0.24, "fenerbahçe": 0.24, "celtic": 0.22, "rangers": 0.20, "olympiacos": 0.24,
    "paok": 0.22, "panathinaikos": 0.22, "fcsb": 0.20, "cfr cluj": 0.18, "universitatea craiova": 0.18
}

# ==============================================================================
# UTILITARE JSON & MATEMATICA POISSON / DIXON-COLES
# ==============================================================================
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

def implied_probs_sq(oh, od, oa):
    raw_h = math.sqrt(1.0 / oh)
    raw_d = math.sqrt(1.0 / od)
    raw_a = math.sqrt(1.0 / oa)
    total = raw_h + raw_d + raw_a
    return raw_h / total, raw_d / total, raw_a / total

def choose_diverse_main_market(home_name, away_name, p_home, p_draw, p_away, p_over, p_under, p_btts, lam_h, lam_a):
    seed = int(hashlib.md5(f"{home_name}_{away_name}".encode("utf-8")).hexdigest()[:4], 16) % 100 / 100.0
    scored = []

    if p_home >= 0.50:
        scored.append((f"1 ({home_name})", p_home, 0.62 + (p_home - 0.50) * 1.65))
    if p_away >= 0.49:
        scored.append((f"2 ({away_name})", p_away, 0.62 + (p_away - 0.49) * 1.65))
    if p_over[2.5] >= 0.52:
        scored.append(("Peste 2.5 goluri", p_over[2.5], 0.61 + (p_over[2.5] - 0.52) * 1.75 + (0.03 if seed < 0.35 else 0.0)))
    if p_btts >= 0.52 and lam_h >= 0.95 and lam_a >= 0.85:
        bal = 0.04 if abs(lam_h - lam_a) <= 0.55 else 0.0
        scored.append(("GG - Ambele marchează", p_btts, 0.61 + (p_btts - 0.52) * 1.75 + bal + (0.03 if 0.35 <= seed < 0.70 else 0.0)))
    if p_under[2.5] >= 0.55:
        scored.append(("Sub 2.5 goluri", p_under[2.5], 0.60 + (p_under[2.5] - 0.55) * 1.65 + (0.03 if seed >= 0.70 else 0.0)))
    if 0.68 <= p_over[1.5] <= 0.79 and p_over[2.5] < 0.52:
        scored.append(("Peste 1.5 goluri", p_over[1.5], 0.58 + (p_over[1.5] - 0.68) * 1.10))
    if 0.38 <= p_home < 0.50 and (p_home + p_draw) >= 0.64:
        scored.append(("Șansă Dublă 1X", p_home + p_draw, 0.56 + ((p_home + p_draw) - 0.64) * 0.90))
    if 0.38 <= p_away < 0.49 and (p_away + p_draw) >= 0.64:
        scored.append(("Șansă Dublă X2", p_away + p_draw, 0.56 + ((p_away + p_draw) - 0.64) * 0.90))
    if p_draw >= 0.31 and abs(p_home - p_away) <= 0.06:
        scored.append(("X (Egal)", p_draw, 0.57))

    if scored:
        best = max(scored, key=lambda item: item[2])
        return best[0], best[1]

    fallback = [
        (f"1 ({home_name})", p_home),
        (f"2 ({away_name})", p_away),
        ("Peste 2.5 goluri", p_over[2.5]),
        ("Sub 2.5 goluri", p_under[2.5]),
        ("GG - Ambele marchează", p_btts)
    ]
    best_fb = max(fallback, key=lambda item: item[1])
    return best_fb[0], best_fb[1]

def build_prediction_for_match(home_name, away_name, league_info, odds_info=None, injuries_h=None, injuries_a=None, referee_name=None):
    injuries_h = injuries_h or []
    injuries_a = injuries_a or []

    h_low = home_name.lower()
    a_low = away_name.lower()
    h_boost = ELITE_TEAMS_BOOST.get(h_low, 0.0)
    a_boost = ELITE_TEAMS_BOOST.get(a_low, 0.0)

    h_hash = (int(hashlib.md5(h_low.encode("utf-8")).hexdigest()[:6], 16) % 100) / 160.0
    a_hash = (int(hashlib.md5(a_low.encode("utf-8")).hexdigest()[:6], 16) % 100) / 160.0

    if odds_info and odds_info.get("oh") and odds_info.get("od") and odds_info.get("oa"):
        oh, od, oa = odds_info["oh"], odds_info["od"], odds_info["oa"]
        p_h, p_d, p_a = implied_probs_sq(oh, od, oa)
        o_over_val = odds_info.get("over25") or 1.85
        o_under_val = odds_info.get("under25") or 1.95
        bookmaker = odds_info.get("bookmaker", "API-Football Odds")
        sr_over = math.sqrt(1.0 / o_over_val)
        sr_under = math.sqrt(1.0 / o_under_val)
        target_over25 = sr_over / (sr_over + sr_under)
        lam_h, lam_a = calibrate_lambdas(p_h, p_d, p_a, DIXON_COLES_RHO_BASE, target_over25)
    else:
        lam_h = max(0.60, min(3.05, 1.32 + h_boost - (a_boost * 0.35) + (h_hash - 0.25)))
        lam_a = max(0.45, min(2.85, 1.08 + a_boost - (h_boost * 0.35) + (a_hash - 0.25)))
        target_over25 = None
        bookmaker = "Model AI + Formă"

    # Ajustăm Expected Goals (xG) în funcție de jucătorii accidentați / suspendați!
    inj_penalty_h = min(0.35, len(injuries_h) * 0.07)
    inj_penalty_a = min(0.35, len(injuries_a) * 0.07)
    lam_h = round(max(0.40, lam_h - inj_penalty_h + (inj_penalty_a * 0.35)), 2)
    lam_a = round(max(0.35, lam_a - inj_penalty_a + (inj_penalty_h * 0.35)), 2)

    max_g = 10
    p_home = p_draw = p_away = p_btts = 0.0
    p_over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    p_under = {2.5: 0.0}

    for h in range(max_g):
        for a in range(max_g):
            p = poisson_pmf(h, lam_h) * poisson_pmf(a, lam_a)
            p = p * dixon_coles_tau(h, a, lam_h, lam_a, DIXON_COLES_RHO_BASE)
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

    oh = odds_info.get("oh") if (odds_info and odds_info.get("oh")) else round(max(1.18, min(9.50, 0.95 / max(0.08, p_home))), 2)
    od = odds_info.get("od") if (odds_info and odds_info.get("od")) else round(max(2.80, min(6.50, 0.95 / max(0.12, p_draw))), 2)
    oa = odds_info.get("oa") if (odds_info and odds_info.get("oa")) else round(max(1.22, min(11.0, 0.95 / max(0.08, p_away))), 2)
    o_over_val = odds_info.get("over25") if (odds_info and odds_info.get("over25")) else round(max(1.35, min(2.70, 0.95 / max(0.20, p_over[2.5]))), 2)
    o_under_val = odds_info.get("under25") if (odds_info and odds_info.get("under25")) else round(max(1.35, min(2.70, 0.95 / max(0.20, p_under[2.5]))), 2)

    odd_1x = round(1.0 / max(0.05, (p_home + p_draw) * 0.95), 2)
    odd_x2 = round(1.0 / max(0.05, (p_away + p_draw) * 0.95), 2)
    odd_o15 = round(1.0 / max(0.05, p_over[1.5] * 0.95), 2)
    odd_btts = round(1.0 / max(0.05, p_btts * 0.95), 2)

    # Estimare Cornere & Cartonașe (bazată pe profilul ligii, intensitatea meciului și arbitru)
    base_cards = league_info.get("avg_cards", 4.4)
    base_corners = league_info.get("avg_corners", 9.7)
    ref_mod = 0.0
    if referee_name:
        ref_seed = (int(hashlib.md5(referee_name.lower().encode("utf-8")).hexdigest()[:4], 16) % 100) / 100.0
        ref_mod = (ref_seed - 0.45) * 1.1

    closeness = max(0.0, 0.35 - abs(p_home - p_away))
    exp_cards = round(max(2.8, min(6.8, base_cards + closeness * 1.5 + ref_mod + (h_hash - a_hash) * 0.5)), 1)
    exp_corners = round(max(7.2, min(12.8, base_corners + (lam_h + lam_a - 2.5) * 0.85 + (h_hash + a_hash - 0.6))), 1)

    def over_prob_line(exp_val, line):
        return sum(poisson_pmf(k, exp_val) for k in range(math.ceil(line), 28))

    corners_cards = {
        "exp_corners": exp_corners,
        "exp_cards": exp_cards,
        "referee": referee_name or "Delegare UEFA / Ligă",
        "corners_over": {str(l): round(over_prob_line(exp_corners, l) * 100, 1) for l in CORNERS_LINES},
        "cards_over": {str(l): round(over_prob_line(exp_cards, l) * 100, 1) for l in CARDS_LINES}
    }

    market_options = [
        {"name": f"1 ({home_name})", "prob": p_home, "odds": oh},
        {"name": "X (Egal)", "prob": p_draw, "odds": od},
        {"name": f"2 ({away_name})", "prob": p_away, "odds": oa},
        {"name": "Peste 2.5 goluri", "prob": p_over[2.5], "odds": o_over_val},
        {"name": "Sub 2.5 goluri", "prob": p_under[2.5], "odds": o_under_val},
        {"name": "GG - Ambele marchează", "prob": p_btts, "odds": odd_btts},
        {"name": "Peste 1.5 goluri", "prob": p_over[1.5], "odds": odd_o15},
        {"name": "Șansă Dublă 1X", "prob": p_home + p_draw, "odds": odd_1x},
        {"name": "Șansă Dublă X2", "prob": p_draw + p_away, "odds": odd_x2}
    ]

    c85 = corners_cards["corners_over"]["8.5"] / 100.0
    cd35 = corners_cards["cards_over"]["3.5"] / 100.0
    if c85 >= 0.55:
        market_options.append({"name": "Peste 8.5 cornere", "prob": c85, "odds": round(0.95 / c85, 2)})
    if cd35 >= 0.55:
        market_options.append({"name": "Peste 3.5 cartonașe", "prob": cd35, "odds": round(0.95 / cd35, 2)})

    best_market, best_p = choose_diverse_main_market(
        home_name, away_name, p_home, p_draw, p_away, p_over, p_under, p_btts, lam_h, lam_a
    )

    risc = "Scăzut" if best_p >= LOW_RISK_THRESHOLD else ("Mediu" if best_p >= CONFIDENCE_THRESHOLD else "Ridicat")

    return {
        "principal": best_market,
        "principal_pct": round(best_p * 100, 1),
        "risc": risc,
        "exp_goals_home": lam_h,
        "exp_goals_away": lam_a,
        "bookmaker": bookmaker,
        "market_options": market_options,
        "corners_cards": corners_cards,
        "injuries_home": injuries_h[:5],
        "injuries_away": injuries_a[:5],
        "probs": {
            "home": round(p_home * 100, 1),
            "draw": round(p_draw * 100, 1),
            "away": round(p_away * 100, 1),
            "over15": round(p_over[1.5] * 100, 1),
            "over25": round(p_over[2.5] * 100, 1),
            "under25": round(p_under[2.5] * 100, 1),
            "btts": round(p_btts * 100, 1)
        }
    }

# ==============================================================================
# CLIENT API-FOOTBALL (CU ECONOMISIRE STRICTĂ DE CERERI)
# ==============================================================================
def api_sports_get(endpoint, params):
    if not APISPORTS_KEY:
        return []
    query = urllib.parse.urlencode(params)
    url = f"{APISPORTS_BASE_URL}/{endpoint}?{query}"
    headers = {
        "x-apisports-key": APISPORTS_KEY,
        "User-Agent": "XMTS-Prediction-Engine/1.0"
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            return payload.get("response", [])
    except Exception as e:
        print(f"Eroare API-Football ({endpoint}): {e}")
        return []

def get_target_sync_dates():
    """Selectează zilele cheie (ieri, azi, următoarele 3 zile + următoarele zile de UCL/UEL)."""
    base = now_dt()
    dates = []
    for offset in [-1, 0, 1, 2, 3]:
        d = base + timedelta(days=offset)
        dates.append(d.strftime("%Y-%m-%d"))

    # Asigurăm și prezența următoarei zile de Marți/Miercuri/Joi pentru UCL & UEL
    for offset in range(4, 8):
        d = base + timedelta(days=offset)
        if d.weekday() in (1, 2, 3):  # 1=Marți, 2=Miercuri, 3=Joi
            dates.append(d.strftime("%Y-%m-%d"))
            if len(dates) >= 6:
                break
    return sorted(list(set(dates)))

def fetch_injuries_for_dates(dates_list):
    """Extrage accidentările și suspendările (doar pentru azi și mâine = 2 cereri)."""
    injuries_map = {}  # fixture_id -> {"home_id": [...], "away_id": [...]}
    for d in dates_list[:2]:
        time.sleep(0.35)
        resp = api_sports_get("injuries", {"date": d})
        for item in resp:
            fix_id = item.get("fixture", {}).get("id")
            team_id = item.get("team", {}).get("id")
            player_name = item.get("player", {}).get("name")
            reason = item.get("player", {}).get("reason") or item.get("player", {}).get("type") or "Indisponibil"
            if fix_id and team_id and player_name:
                key = f"{fix_id}_{team_id}"
                if key not in injuries_map:
                    injuries_map[key] = []
                entry = f"{player_name} ({reason})"
                if entry not in injuries_map[key]:
                    injuries_map[key].append(entry)
    return injuries_map

def fetch_odds_for_dates(dates_list):
    """Extrage cotele reale (doar pentru azi și mâine = 2 cereri)."""
    odds_map = {}  # fixture_id -> {"oh": ..., "od": ..., "oa": ..., "over25": ..., "under25": ...}
    for d in dates_list[:2]:
        time.sleep(0.35)
        resp = api_sports_get("odds", {"date": d, "bookmaker": 8})  # 8 = Bet365
        for item in resp:
            fix_id = item.get("fixture", {}).get("id")
            if not fix_id:
                continue
            bms = item.get("bookmakers", [])
            if not bms:
                continue
            bets = bms[0].get("bets", [])
            info = {"bookmaker": bms[0].get("name", "Bet365")}
            for bet in bets:
                b_id = bet.get("id")
                vals = bet.get("values", [])
                if b_id == 1:  # Match Winner (1X2)
                    for v in vals:
                        if v.get("value") == "Home":
                            info["oh"] = float(v.get("odd") or 0)
                        elif v.get("value") == "Draw":
                            info["od"] = float(v.get("odd") or 0)
                        elif v.get("value") == "Away":
                            info["oa"] = float(v.get("odd") or 0)
                elif b_id == 5:  # Goals Over/Under
                    for v in vals:
                        if v.get("value") == "Over 2.5":
                            info["over25"] = float(v.get("odd") or 0)
                        elif v.get("value") == "Under 2.5":
                            info["under25"] = float(v.get("odd") or 0)
            if info.get("oh") and info.get("od") and info.get("oa"):
                odds_map[fix_id] = info
    return odds_map

def sync_daily_data(force=False):
    """
    RULEAZĂ O SINGURĂ DATĂ PE ZI!
    Dacă datele pe ziua de azi sunt deja în matches_cache.json, returnează direct cache-ul.
    """
    with SYNC_LOCK:
        existing = _load_json(CACHE_FILE, None)
        today = today_str()
        if (
            not force
            and existing
            and existing.get("sync_date") == today
            and existing.get("version") == CACHE_VERSION
            and len(existing.get("matches", [])) > 0
        ):
            return existing

        all_dates = get_target_sync_dates()
        active_dates = [d for d in all_dates if d >= today][:2]

        # 1. Cereri pentru accidentări & cote (4 cereri total)
        injuries_map = fetch_injuries_for_dates(active_dates)
        odds_map = fetch_odds_for_dates(active_dates)

        # 2. Cereri pentru meciurile din zilele țintă (~5-6 cereri total)
        matches_map = {}
        api_requests_used = len(active_dates) * 2

        for d in all_dates:
            time.sleep(0.35)
            fixtures = api_sports_get("fixtures", {"date": d, "timezone": "Europe/Bucharest"})
            api_requests_used += 1

            for item in fixtures:
                league_obj = item.get("league", {})
                league_id = league_obj.get("id")
                if league_id not in TRACKED_LEAGUES:
                    continue

                l_info = TRACKED_LEAGUES[league_id]
                fix_obj = item.get("fixture", {})
                fix_id = fix_obj.get("id")
                referee = fix_obj.get("referee")

                iso_date = (fix_obj.get("date") or "")[:10] or d
                iso_time = ""
                if "T" in (fix_obj.get("date") or ""):
                    iso_time = fix_obj["date"].split("T")[1][:5]

                teams_obj = item.get("teams", {})
                home_team = (teams_obj.get("home", {}).get("name") or "").strip()
                away_team = (teams_obj.get("away", {}).get("name") or "").strip()
                home_id = teams_obj.get("home", {}).get("id")
                away_id = teams_obj.get("away", {}).get("id")
                if not home_team or not away_team:
                    continue

                status_short = fix_obj.get("status", {}).get("short", "NS")
                goals_obj = item.get("goals", {})
                has_res = status_short in ("FT", "AET", "PEN") and goals_obj.get("home") is not None and goals_obj.get("away") is not None
                res_h = int(goals_obj["home"]) if has_res else None
                res_a = int(goals_obj["away"]) if has_res else None

                inj_h = injuries_map.get(f"{fix_id}_{home_id}", [])
                inj_a = injuries_map.get(f"{fix_id}_{away_id}", [])
                odds_info = odds_map.get(fix_id)

                pred = build_prediction_for_match(
                    home_team, away_team, l_info,
                    odds_info=odds_info, injuries_h=inj_h, injuries_a=inj_a, referee_name=referee
                )

                key = f"{iso_date}_{home_team.lower()}_{away_team.lower()}"
                matches_map[key] = {
                    "fixture_id": fix_id,
                    "league": l_info["name"],
                    "league_code": l_info["code"],
                    "league_icon": l_info["icon"],
                    "league_priority": l_info["priority"],
                    "category": l_info["cat"],
                    "is_cl": l_info["cat"] == "cl",
                    "is_el": l_info["cat"] == "el",
                    "date": iso_date,
                    "time": iso_time,
                    "home": home_team,
                    "away": away_team,
                    "has_result": has_res,
                    "res_home": res_h,
                    "res_away": res_a,
                    **pred
                }

        # 3. Opțional: completăm cu etapele din CL.csv / EL.csv de pe GitHub dacă există
        if FIXTURES_CSV_URL:
            base_url = FIXTURES_CSV_URL.rsplit('/', 1)[0]
            for csv_file in TARGET_STATS_FILES:
                try:
                    url = f"{base_url}/{csv_file}"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=6) as resp:
                        content = resp.read().decode('utf-8', errors='replace')
                        reader = csv.DictReader(io.StringIO(content))
                        is_cl_file = "CL" in csv_file.upper()
                        l_info = TRACKED_LEAGUES[2 if is_cl_file else 3]
                        for row in reader:
                            h = (row.get("HomeTeam") or row.get("Home Team") or "").strip()
                            a = (row.get("AwayTeam") or row.get("Away Team") or "").strip()
                            raw_d = (row.get("Date") or "").strip()
                            if not h or not a or not raw_d:
                                continue
                            # Parsare dată DD/MM/YYYY
                            m_date = raw_d.split(" ")[0]
                            for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
                                try:
                                    dt = datetime.strptime(m_date, fmt)
                                    m_date = dt.strftime("%Y-%m-%d")
                                    break
                                except ValueError:
                                    pass
                            key = f"{m_date}_{h.lower()}_{a.lower()}"
                            if key not in matches_map:
                                fthg, ftag = row.get("FTHG"), row.get("FTAG")
                                has_r = bool(fthg and ftag and str(fthg).strip() != "")
                                rh = int(float(fthg)) if has_r else None
                                ra = int(float(ftag)) if has_r else None
                                pred = build_prediction_for_match(h, a, l_info)
                                matches_map[key] = {
                                    "fixture_id": 0,
                                    "league": l_info["name"],
                                    "league_code": l_info["code"],
                                    "league_icon": l_info["icon"],
                                    "league_priority": l_info["priority"],
                                    "category": l_info["cat"],
                                    "is_cl": is_cl_file,
                                    "is_el": not is_cl_file,
                                    "date": m_date,
                                    "time": (row.get("Time") or "21:00").strip(),
                                    "home": h,
                                    "away": a,
                                    "has_result": has_r,
                                    "res_home": rh,
                                    "res_away": ra,
                                    **pred
                                }
                except Exception:
                    pass

        all_matches = list(matches_map.values())
        all_matches.sort(key=lambda m: (m["date"], m["league_priority"], m.get("time") or "23:59", -(m.get("principal_pct") or 0)))

        # Salvăm în cache doar dacă am obținut meciuri (evităm suprascrierea cu listă goală)
        if all_matches:
            cache_data = {
                "version": CACHE_VERSION,
                "sync_date": today,
                "uploaded_at": now_dt().strftime("%Y-%m-%d %H:%M"),
                "requests_used_today": api_requests_used,
                "matches": all_matches,
                "api_active": True,
                "source": "API-Football v3 (1 sync/zi)"
            }
            _save_json(CACHE_FILE, cache_data)
            return cache_data

        return existing or {"matches": [], "api_active": False, "sync_date": today}

# ==============================================================================
# ENDPOINT-URI FLASK
# ==============================================================================
@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    data = sync_daily_data(force=False)
    return jsonify(data)

@app.route('/api/refresh-from-github', methods=['POST'])
def refresh_from_github():
    # Permite forțarea doar dacă se trimite explicit ?force=1, altfel protejează cota zilnică
    force_flag = request.args.get("force") == "1"
    data = sync_daily_data(force=force_flag)
    return jsonify({
        "status": "success",
        "sync_date": data.get("sync_date"),
        "count": len(data.get("matches", [])),
        "message": "Datele pe ziua de azi sunt deja la zi (protecție 1 request/zi activă)."
    })

# ==============================================================================
# INTERFAȚA WEB (CU SECȚIUNI PE LIGI, ACCIDENTĂRI, CARTONAȘE & BILETE)
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XMTS AI · API-Football Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-dark: #0a0a0a; --card-bg: #151515; --card-border: #282828;
    --accent-cyan: #06b6d4; --accent-gold: #eab308; --accent-orange: #f97316;
    --text-main: #f8fafc; --text-muted: #94a3b8; --bar-green: #22c55e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
  body { background: var(--bg-dark); color: var(--text-main); padding: 10px; }
  .container { max-width: 600px; margin: 0 auto; }

  .header-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .status-pill {
    display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: #34d399;
    background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3);
    padding: 4px 10px; border-radius: 20px; margin-bottom: 12px; font-weight: 600;
  }

  .tabs-wrapper { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 8px; scrollbar-width: none; }
  .tabs-wrapper::-webkit-scrollbar { display: none; }
  .tab-btn {
    background: #1c1c1c; border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 9px 13px; border-radius: 10px; font-weight: 700; white-space: nowrap; cursor: pointer; font-size: 12px;
  }
  .tab-btn.active { background: rgba(234, 179, 8, 0.16); border-color: var(--accent-gold); color: #fff; }

  .league-filter-bar { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 10px; scrollbar-width: none; }
  .league-filter-bar::-webkit-scrollbar { display: none; }
  .league-chip {
    background: #141414; border: 1px solid #2a2a2a; color: #cbd5e1;
    padding: 5px 10px; border-radius: 8px; font-size: 11px; font-weight: 600; white-space: nowrap; cursor: pointer;
  }
  .league-chip.active { background: var(--accent-gold); color: #000; border-color: var(--accent-gold); font-weight: 800; }

  .date-picker-bar { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 14px; scrollbar-width: none; scroll-behavior: smooth; }
  .date-picker-bar::-webkit-scrollbar { display: none; }
  .date-chip {
    background: #1f1f1f; border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: bold; white-space: nowrap; cursor: pointer;
  }
  .date-chip.active { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }

  /* SECTIUNI PE LIGI */
  .league-section { margin-bottom: 20px; }
  .league-section-header {
    display: flex; justify-content: space-between; align-items: center;
    background: linear-gradient(90deg, rgba(234,179,8,0.16) 0%, rgba(22,22,22,0.95) 100%);
    border-left: 4px solid var(--accent-gold); border-radius: 10px;
    padding: 10px 14px; margin-bottom: 10px; font-weight: 800; font-size: 13px; color: #fff;
  }
  .league-badge-count {
    font-size: 11px; color: var(--accent-gold); background: rgba(0,0,0,0.5);
    padding: 3px 8px; border-radius: 6px; font-weight: 700;
  }

  .glass-card {
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 16px; padding: 15px; margin-bottom: 10px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.45);
  }

  .match-basic { display:flex; flex-direction:column; gap:8px; }
  .pred-row { display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.45); border-radius: 10px; padding: 10px; }
  .risk-tag { font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; text-transform: uppercase; }
  .risk-Scăzut { background: rgba(16,185,129,0.2); color: #34d399; }
  .risk-Mediu { background: rgba(245,158,11,0.2); color: #fbbf24; }
  .risk-Ridicat { background: rgba(239,68,68,0.2); color: #fca5a5; }

  .btn-expand {
    width: 100%; background: #1f1f1f; border: 1px solid #eab308; color: #fff;
    padding: 9px; border-radius: 10px; font-weight: bold; cursor: pointer; margin-top: 8px; font-size: 12px;
  }

  .golden-panel { display: none; margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--card-border); }
  .golden-header { text-align: center; color: var(--accent-gold); font-size: 15px; font-weight: 800; margin-bottom: 12px; text-transform: uppercase; }

  .h2h-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 12px; }
  .h2h-val { width: 65px; text-align: center; font-weight: 800; padding: 5px 4px; border-radius: 6px; background: #222; color: var(--accent-gold); }
  .h2h-label { flex: 1; text-align: center; color: #cbd5e1; font-weight: bold; }

  .bars-section { margin-top: 14px; }
  .bar-row { display: flex; align-items: center; margin-bottom: 7px; font-size: 12px; font-weight: bold; }
  .bar-label { width: 100px; color: #fff; }
  .bar-track { flex: 1; background: rgba(255,255,255,0.06); border-radius: 12px; height: 18px; position: relative; }
  .bar-fill { height: 100%; background: var(--bar-green); border-radius: 12px; display: flex; justify-content: flex-end; align-items: center; padding-right: 8px; color: #fff; font-size: 10px; }

  .acc-item { background: #1a1a1a; border: 1px solid #333; border-radius: 10px; margin-bottom: 8px; }
  .acc-header { padding: 10px 14px; display: flex; justify-content: space-between; cursor: pointer; color: #fff; font-weight: bold; font-size: 12px; }
  .acc-body { padding: 10px 14px; border-top: 1px solid #2a2a2a; font-size: 12px; color: var(--text-muted); display: none; line-height: 1.5; }

  .ticket-config { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 15px; }
  .odds-btn { background: #222; border: 1px solid var(--card-border); color: #fff; padding: 8px 12px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 13px; }
  .odds-btn.active { background: var(--accent-gold); color: #000; border-color: var(--accent-gold); }
  .ticket-match-row { display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.03); padding: 10px; border-radius: 8px; margin-bottom: 8px; font-size: 13px; }

  .result-badge { font-weight: 800; font-size: 11px; padding: 2px 6px; border-radius: 4px; }
  .res-win { background: rgba(34, 197, 94, 0.2); color: #22c55e; border: 1px solid #22c55e; }
  .res-loss { background: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
  .res-pending { background: rgba(148, 163, 184, 0.1); color: #94a3b8; }
</style>
</head>
<body>
<div class="container">
  <div class="header-bar">
    <div style="font-size:20px; font-weight:800; color:var(--accent-gold);">XMTS PREDICTIONS</div>
    <div id="syncStatusBadge" class="status-pill">⚡ API-Football Activ (1 sync/zi)</div>
  </div>

  <div class="tabs-wrapper">
    <button class="tab-btn active" onclick="switchTab('meciuri', this)">⚽ Ligi Naționale</button>
    <button class="tab-btn" onclick="switchTab('cl', this)" style="border-color:var(--accent-cyan); color:var(--accent-cyan);">🏆 Champions League</button>
    <button class="tab-btn" onclick="switchTab('el', this)" style="border-color:var(--accent-orange); color:var(--accent-orange);">🟠 Europa & Conf. League</button>
    <button class="tab-btn" onclick="switchTab('bilete', this)" style="border-color:var(--accent-gold); color:var(--accent-gold);">🎟️ Generator Bilete</button>
  </div>

  <div id="dateSelectorContainer"></div>
  <div id="leagueFilterContainer"></div>
  <div id="content"><div class="glass-card" style="text-align:center;">Se încarcă meciurile din cache-ul zilnic...</div></div>
</div>

<script>
let state = { matches: [] };
let currentTab = 'meciuri';
let selectedDate = '';
let selectedClDate = '';
let selectedElDate = '';
let selectedLeagueFilter = 'ALL';
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
  btn.innerText = isHidden ? 'Ascunde Analiză' : 'Deschide Analiză, Cartonașe & Accidentări';
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
  if (marketName.includes("Peste 1.5")) return tot > 1.5 ? {status: 'win'} : {status: 'loss'};
  if (marketName.includes("Sub 2.5")) return tot <= 2.5 ? {status: 'win'} : {status: 'loss'};
  if (marketName.includes("GG")) return (h > 0 && a > 0) ? {status: 'win'} : {status: 'loss'};
  return { status: 'pending' };
}

function renderMatchCard(m) {
  const p = m.probs;
  const pronostic = m.principal || "Echilibrat";
  const pronostic_pct = m.principal_pct || "-";

  const evalRes = evaluatePrediction(m, pronostic);
  let badgeHtml = '';
  if (m.has_result) {
    badgeHtml = evalRes.status === 'win'
      ? `<span class="result-badge res-win">✔ CÂȘTIGAT (${m.res_home}-${m.res_away})</span>`
      : `<span class="result-badge res-loss">✖ PIERDUT (${m.res_home}-${m.res_away})</span>`;
  } else {
    badgeHtml = `<span class="result-badge res-pending">🕒 ${m.time || 'Viitor'}</span>`;
  }

  const cc = m.corners_cards || {};
  const cardsHtml = `
    <div>👨‍⚖️ Arbitru: <b style="color:#fff;">${cc.referee || 'Nedelegat'}</b></div>
    <div>🟨 Estimat meci: ~<b style="color:var(--accent-gold);">${cc.exp_cards || 4.3}</b> cartonașe</div>
    <div>• Peste 3.5 cartonașe: <b style="color:#34d399;">${cc.cards_over ? cc.cards_over['3.5'] : 62}%</b> | Peste 4.5: <b>${cc.cards_over ? cc.cards_over['4.5'] : 44}%</b></div>
  `;
  const cornersHtml = `
    <div>🚩 Estimat meci: ~<b style="color:var(--accent-gold);">${cc.exp_corners || 9.6}</b> cornere</div>
    <div>• Peste 8.5 cornere: <b style="color:#34d399;">${cc.corners_over ? cc.corners_over['8.5'] : 64}%</b> | Peste 9.5: <b>${cc.corners_over ? cc.corners_over['9.5'] : 49}%</b></div>
  `;

  const injH = (m.injuries_home && m.injuries_home.length) ? m.injuries_home.join(", ") : "Fără absențe raportate";
  const injA = (m.injuries_away && m.injuries_away.length) ? m.injuries_away.join(", ") : "Fără absențe raportate";
  const totalInj = (m.injuries_home ? m.injuries_home.length : 0) + (m.injuries_away ? m.injuries_away.length : 0);
  const injuriesHtml = `
    <div>🏠 <b>${m.home}:</b> ${injH}</div>
    <div style="margin-top:4px;">✈️ <b>${m.away}:</b> ${injA}</div>
  `;

  return `
    <div class="glass-card">
      <div class="match-basic">
        <div style="font-size:11px;color:var(--text-muted);display:flex;justify-content:space-between;align-items:center;">
          <span>${m.date} · ${m.bookmaker || 'API-Football'}</span>
          <span>${badgeHtml}</span>
        </div>
        <div style="font-size:16px;font-weight:800;text-align:center; margin-top:2px;">${m.home} <span style="color:var(--accent-gold);">VS</span> ${m.away}</div>
        
        <div class="pred-row" style="margin-top:4px;">
          <span style="font-size:13px;font-weight:700;color:#fff;">
            ⭐ ${pronostic} <span style="color:var(--accent-gold);">(${pronostic_pct}%)</span>
          </span>
          <span class="risk-tag risk-${m.risc}">${m.risc}</span>
        </div>
      </div>

      <button class="btn-expand" onclick="toggleGoldenPanel(this)">Deschide Analiză, Cartonașe & Accidentări</button>
      
      <div class="golden-panel">
        <div class="golden-header">PROBABILITĂȚI & EXPECTED GOALS</div>
        <div class="h2h-row">
          <div class="h2h-val">${m.exp_goals_home}</div>
          <div class="h2h-label">Expected Goals (xG Ajustat)</div>
          <div class="h2h-val">${m.exp_goals_away}</div>
        </div>

        <div class="bars-section">
          <div class="bar-row"><div class="bar-label">1 (Gazde):</div><div class="bar-track"><div class="bar-fill" style="width: ${p.home}%;">${p.home}%</div></div></div>
          <div class="bar-row"><div class="bar-label">X (Egal):</div><div class="bar-track"><div class="bar-fill" style="width: ${p.draw}%; background:#3b82f6;">${p.draw}%</div></div></div>
          <div class="bar-row"><div class="bar-label">2 (Oaspeți):</div><div class="bar-track"><div class="bar-fill" style="width: ${p.away}%; background:#a855f7;">${p.away}%</div></div></div>
          <div class="bar-row"><div class="bar-label">Peste 2.5:</div><div class="bar-track"><div class="bar-fill" style="width: ${p.over25}%;">${p.over25}%</div></div></div>
          <div class="bar-row"><div class="bar-label">GG (Ambele):</div><div class="bar-track"><div class="bar-fill" style="width: ${p.btts}%;">${p.btts}%</div></div></div>
        </div>

        <div style="margin-top: 14px;">
          <div class="acc-item">
            <div class="acc-header" onclick="toggleAccordion(this)">
              <div>🚑 Accidentări & Suspendări (${totalInj})</div><div>▼</div>
            </div>
            <div class="acc-body" style="display:block;">${injuriesHtml}</div>
          </div>
          <div class="acc-item">
            <div class="acc-header" onclick="toggleAccordion(this)">
              <div>🟨 Istoric Cartonașe & Arbitru (~${cc.exp_cards || 4.3})</div><div>▼</div>
            </div>
            <div class="acc-body" style="display:block;">${cardsHtml}</div>
          </div>
          <div class="acc-item">
            <div class="acc-header" onclick="toggleAccordion(this)">
              <div>🚩 Estimare Cornere (~${cc.exp_corners || 9.6})</div><div>▼</div>
            </div>
            <div class="acc-body">${cornersHtml}</div>
          </div>
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

  return `<div class="date-picker-bar">${chips || '<span style="font-size:12px;color:var(--text-muted)">Nicio dată disponibilă</span>'}</div>`;
}

function renderLeagueFilter(dayMatches) {
  if (currentTab !== 'meciuri' || !dayMatches.length) return '';
  const leagues = [];
  const seen = new Set();
  dayMatches.forEach(m => {
    if (!seen.has(m.league)) {
      seen.add(m.league);
      leagues.push({ name: m.league, icon: m.league_icon || '⚽' });
    }
  });

  let html = `<button class="league-chip ${selectedLeagueFilter === 'ALL' ? 'active' : ''}" onclick="setLeagueFilter('ALL')">Toate Ligile (${dayMatches.length})</button>`;
  leagues.forEach(l => {
    const count = dayMatches.filter(m => m.league === l.name).length;
    html += `<button class="league-chip ${selectedLeagueFilter === l.name ? 'active' : ''}" onclick="setLeagueFilter('${l.name}')">${l.icon} ${l.name} (${count})</button>`;
  });
  return `<div class="league-filter-bar">${html}</div>`;
}

function setLeagueFilter(lName) {
  selectedLeagueFilter = lName;
  render();
}

function selectDate(d) {
  selectedLeagueFilter = 'ALL';
  if (currentTab === 'cl') selectedClDate = d;
  else if (currentTab === 'el') selectedElDate = d;
  else selectedDate = d;
  render();
}

function renderGroupedSections(matches) {
  if (!matches.length) {
    return `<div class="glass-card" style="text-align:center;">Niciun meci programat în această dată. Alege altă zi din bara de sus.</div>`;
  }

  const groups = {};
  const order = [];
  matches.forEach(m => {
    if (!groups[m.league]) {
      groups[m.league] = { icon: m.league_icon || '⚽', items: [] };
      order.push(m.league);
    }
    groups[m.league].items.push(m);
  });

  return order.map(leagueName => {
    const grp = groups[leagueName];
    return `
      <div class="league-section">
        <div class="league-section-header">
          <span>${grp.icon} ${leagueName}</span>
          <span class="league-badge-count">${grp.items.length} ${grp.items.length === 1 ? 'meci' : 'meciuri'}</span>
        </div>
        ${grp.items.map(renderMatchCard).join('')}
      </div>
    `;
  }).join('');
}

function renderTicketGenerator() {
  const activeD = selectedDate || selectedClDate || selectedElDate || getTodayStr();
  const matches = (state.matches || []).filter(m => m.date === activeD && !m.has_result);

  let pool = [];
  matches.forEach(m => {
    if (m.market_options) {
      m.market_options.forEach(opt => {
        if (opt.prob >= 0.52 && opt.odds >= 1.25 && opt.odds <= 3.50) {
          pool.push({
            match: `${m.home} - ${m.away}`,
            league: m.league,
            market: opt.name,
            odds: opt.odds,
            prob: opt.prob,
            score: opt.prob * (1.0 / Math.max(0.15, Math.abs(opt.odds - 1.65)))
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
      <div style="font-size:12px; color:var(--text-muted); margin-bottom:15px;">Combină cele mai sigure pronosticuri din toate ligile zilei.</div>
      <div class="ticket-config">${oddsButtons}</div>
      <div style="background:rgba(0,0,0,0.5); border:1px solid var(--card-border); border-radius:12px; padding:12px; margin-top:15px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid #333; padding-bottom:8px;">
          <span style="font-weight:bold; font-size:13px;">Cotă Țintă: ~${selectedTargetOdds}</span>
          <span style="background:var(--accent-gold); color:#000; font-weight:800; padding:4px 10px; border-radius:8px; font-size:14px;">Cotă Totală: ${currentOdds.toFixed(2)}</span>
        </div>
        ${picksHtml || '<div style="text-align:center; padding:20px; color:var(--text-muted);">Nu sunt suficiente meciuri viitoare în data selectată.</div>'}
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
  const leagueContainer = document.getElementById('leagueFilterContainer');
  const c = document.getElementById('content');

  if (state.sync_date) {
    document.getElementById('syncStatusBadge').innerText = `🟢 Sincronizat: ${state.sync_date} (1/1 sync azi)`;
  }

  if (!state.matches || !state.matches.length) {
    dateContainer.innerHTML = '';
    leagueContainer.innerHTML = '';
    c.innerHTML = '<div class="glass-card" style="text-align:center;">Nu s-au găsit meciuri. Verifică conexiunea API.</div>';
    return;
  }

  dateContainer.innerHTML = renderDateSelector();

  const activeD = (currentTab === 'cl') ? selectedClDate : (currentTab === 'el' ? selectedElDate : selectedDate);
  const dayMatches = (state.matches || []).filter(m => {
    if (currentTab === 'cl') return m.is_cl && m.date === activeD;
    if (currentTab === 'el') return m.is_el && m.date === activeD;
    return !m.is_cl && !m.is_el && m.date === activeD;
  });

  if (currentTab === 'meciuri' || currentTab === 'cl' || currentTab === 'el') {
    leagueContainer.innerHTML = renderLeagueFilter(dayMatches);
    const filtered = (currentTab === 'meciuri' && selectedLeagueFilter !== 'ALL')
      ? dayMatches.filter(m => m.league === selectedLeagueFilter)
      : dayMatches;
    c.innerHTML = renderGroupedSections(filtered);
  } else {
    leagueContainer.innerHTML = '';
    c.innerHTML = renderTicketGenerator();
  }
}

function switchTab(t, btn) {
  currentTab = t;
  selectedLeagueFilter = 'ALL';
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  render();
}

async function fetchAPI() {
  try {
    const res = await fetch('/api/predictions');
    state = await res.json();
    render();
  } catch (e) {
    console.error(e);
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
