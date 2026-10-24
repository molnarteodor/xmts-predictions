import os
import json
import math
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

def now_dt():
    if TZ:
        return datetime.now(TZ)
    return datetime.now()

def today_str():
    return now_dt().strftime("%Y-%m-%d")

app = Flask(__name__)
CORS(app)

CACHE_VERSION = "v11_live_espn"
CACHE_FILE = "matches_cache.json"
SYNC_LOCK = threading.Lock()

# Competițiile suportate și slug-urile lor în ESPN
ESPN_LEAGUES = [
    {"slug": "uefa.champions",      "code": "CL",  "name": "UEFA Champions League",       "icon": "🏆", "cat": "cl",  "priority": 1},
    {"slug": "uefa.europa",         "code": "EL",  "name": "UEFA Europa League",          "icon": "🟠", "cat": "el",  "priority": 2},
    {"slug": "uefa.europa.conf",    "code": "ECL", "name": "UEFA Conference League",      "icon": "🟢", "cat": "el",  "priority": 3},
    {"slug": "eng.1",               "code": "E0",  "name": "Premier League (Anglia)",     "icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "cat": "nat", "priority": 10},
    {"slug": "esp.1",               "code": "SP1", "name": "La Liga (Spania)",            "icon": "🇪🇸", "cat": "nat", "priority": 11},
    {"slug": "ita.1",               "code": "I1",  "name": "Serie A (Italia)",            "icon": "🇮🇹", "cat": "nat", "priority": 12},
    {"slug": "ger.1",               "code": "D1",  "name": "Bundesliga (Germania)",       "icon": "🇩🇪", "cat": "nat", "priority": 13},
    {"slug": "fra.1",               "code": "F1",  "name": "Ligue 1 (Franța)",            "icon": "🇫🇷", "cat": "nat", "priority": 14},
    {"slug": "rou.1",               "code": "RO1", "name": "SuperLiga (România)",         "icon": "🇷🇴", "cat": "nat", "priority": 15},
    {"slug": "ned.1",               "code": "N1",  "name": "Eredivisie (Olanda)",         "icon": "🇳🇱", "cat": "nat", "priority": 16},
    {"slug": "por.1",               "code": "P1",  "name": "Primeira Liga (Portugalia)",  "icon": "🇵🇹", "cat": "nat", "priority": 17},
    {"slug": "tur.1",               "code": "T1",  "name": "Süper Lig (Turcia)",          "icon": "🇹🇷", "cat": "nat", "priority": 18},
    {"slug": "bel.1",               "code": "B1",  "name": "Jupiler Pro League (Belgia)", "icon": "🇧🇪", "cat": "nat", "priority": 19},
    {"slug": "gre.1",               "code": "G1",  "name": "Super League (Grecia)",       "icon": "🇬🇷", "cat": "nat", "priority": 20},
    {"slug": "sco.1",               "code": "SC0", "name": "Premiership (Scoția)",        "icon": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "cat": "nat", "priority": 21},
    {"slug": "eng.2",               "code": "E1",  "name": "Championship (Anglia)",       "icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "cat": "nat", "priority": 22},
]

ESPN_SLUG_MAP = {l["slug"]: l for l in ESPN_LEAGUES}

ELITE_TEAMS_BOOST = {
    "real madrid": 0.45, "bayern munich": 0.45, "manchester city": 0.45,
    "fc barcelona": 0.45, "liverpool": 0.42, "paris saint-germain": 0.42,
    "arsenal": 0.40, "inter": 0.36, "borussia dortmund": 0.33, "leverkusen": 0.35,
    "atletico madrid": 0.32, "juventus": 0.30, "milan": 0.30, "napoli": 0.32,
    "manchester united": 0.28, "aston villa": 0.28, "benfica": 0.28, "fcsb": 0.22
}

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
    if x == 0 and y == 0: return 1.0 - (lam * mu * rho)
    elif x == 0 and y == 1: return 1.0 + (lam * rho)
    elif x == 1 and y == 0: return 1.0 + (mu * rho)
    elif x == 1 and y == 1: return 1.0 - rho
    return 1.0

def _match_probs_from_lambdas(lam_h, lam_a, max_g, rho, over_line=None):
    p_h = p_d = p_a = p_over = 0.0
    for h in range(max_g):
        for a in range(max_g):
            p = poisson_pmf(h, lam_h) * poisson_pmf(a, lam_a) * dixon_coles_tau(h, a, lam_h, lam_a, rho)
            if h > a: p_h += p
            elif h == a: p_d += p
            else: p_a += p
            if over_line is not None and (h + a) > over_line: p_over += p
    return p_h, p_d, p_a, p_over

def calibrate_lambdas(target_h, target_d, target_a, rho, target_over25=None):
    best = (1.4, 1.1)
    best_err = 999.0
    for i in range(8):
        lh = round(0.5 + i * 0.3, 2)
        for j in range(8):
            la = round(0.5 + j * 0.3, 2)
            ph, pd, pa, p_over25 = _match_probs_from_lambdas(lh, la, max_g=7, rho=rho, over_line=2.5)
            err = (ph - target_h)**2 + (pd - target_d)**2 + (pa - target_a)**2
            if err < best_err:
                best_err = err
                best = (lh, la)
    return best[0], best[1]

def implied_probs_sq(oh, od, oa):
    raw_h, raw_d, raw_a = math.sqrt(1.0 /
