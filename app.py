import os
import re
import time
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

def now_dt():
    if TZ:
        return datetime.now(TZ)
    return datetime.now()

def today_str():
    return now_dt().strftime("%Y-%m-%d")

app = Flask(__name__)
CORS(app)

# ==============================================================================
# CONFIGURARE FĂRĂ CHEIE API (100% PUBLIC & IMUN LA BLOCARE)
# ==============================================================================
CACHE_VERSION = "v7_public_nokey"
CACHE_FILE = "matches_cache.json"
STATS_CACHE_FILE = "team_stats_cache.json"
SYNC_LOCK = threading.Lock()

FIXTURES_CSV_URL = os.environ.get("FIXTURES_CSV_URL", "")
TARGET_GITHUB_CSVS = ["CL.csv", "EL.csv"]

# Baza publică gratuită pentru istoric real de cornere și cartonașe (fără cont)
FOOTBALL_DATA_BASE = "https://www.football-data.co.uk/mmz4281/2526"
PUBLIC_STATS_CSVS = ["E0.csv", "SP1.csv", "I1.csv", "D1.csv", "F1.csv", "N1.csv", "P1.csv", "T1.csv", "G1.csv", "B1.csv"]

CONFIDENCE_THRESHOLD = 0.52
LOW_RISK_THRESHOLD = 0.62

CORNERS_LINES = [8.5, 9.5, 10.5]
CARDS_LINES = [3.5, 4.5, 5.5]
DIXON_COLES_RHO_BASE = -0.08

# Competițiile preluate din API-ul public ESPN (fără cheie)
ESPN_LEAGUES = [
    {"slug": "uefa.champions",      "code": "CL",  "name": "UEFA Champions League",       "icon": "🏆", "cat": "cl",  "priority": 1,  "avg_cards": 4.3, "avg_corners": 9.9},
    {"slug": "uefa.europa",         "code": "EL",  "name": "UEFA Europa League",          "icon": "🟠", "cat": "el",  "priority": 2,  "avg_cards": 4.6, "avg_corners": 9.6},
    {"slug": "uefa.europa.conf",    "code": "ECL", "name": "UEFA Conference League",      "icon": "🟢", "cat": "el",  "priority": 3,  "avg_cards": 4.5, "avg_corners": 9.5},
    {"slug": "eng.1",               "code": "E0",  "name": "Premier League (Anglia)",     "icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "cat": "nat", "priority": 10, "avg_cards": 4.1, "avg_corners": 10.4},
    {"slug": "esp.1",               "code": "SP1", "name": "La Liga (Spania)",            "icon": "🇪🇸", "cat": "nat", "priority": 11, "avg_cards": 5.1, "avg_corners": 9.5},
    {"slug": "ita.1",               "code": "I1",  "name": "Serie A (Italia)",            "icon": "🇮🇹", "cat": "nat", "priority": 12, "avg_cards": 4.7, "avg_corners": 9.7},
    {"slug": "ger.1",               "code": "D1",  "name": "Bundesliga (Germania)",       "icon": "🇩🇪", "cat": "nat", "priority": 13, "avg_cards": 4.2, "avg_corners": 9.9},
    {"slug": "fra.1",               "code": "F1",  "name": "Ligue 1 (Franța)",            "icon": "🇫🇷", "cat": "nat", "priority": 14, "avg_cards": 4.0, "avg_corners": 9.4},
    {"slug": "rou.1",               "code": "RO1", "name": "SuperLiga (România)",         "icon": "🇷🇴", "cat": "nat", "priority": 15, "avg_cards": 4.8, "avg_corners": 9.1},
    {"slug": "ned.1",               "code": "N1",  "name": "Eredivisie (Olanda)",         "icon": "🇳🇱", "cat": "nat", "priority": 16, "avg_cards": 3.5, "avg_corners": 10.2},
    {"slug": "por.1",               "code": "P1",  "name": "Primeira Liga (Portugalia)",  "icon": "🇵🇹", "cat": "nat", "priority": 17, "avg_cards": 5.2, "avg_corners": 10.0},
    {"slug": "tur.1",               "code": "T1",  "name": "Süper Lig (Turcia)",          "icon": "🇹🇷", "cat": "nat", "priority": 18, "avg_cards": 5.0, "avg_corners": 9.6},
    {"slug": "bel.1",               "code": "B1",  "name": "Jupiler Pro League (Belgia)", "icon": "🇧🇪", "cat": "nat", "priority": 19, "avg_cards": 4.3, "avg_corners": 9.8},
    {"slug": "gre.1",               "code": "G1",  "name": "Super League (Grecia)",       "icon": "🇬🇷", "cat": "nat", "priority": 20, "avg_cards": 4.9, "avg_corners": 9.0},
    {"slug": "sco.1",               "code": "SC0", "name": "Premiership (Scoția)",        "icon": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "cat": "nat", "priority": 21, "avg_cards": 4.2, "avg_corners": 10.3},
    {"slug": "eng.2",               "code": "E1",  "name": "Championship (Anglia)",       "icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "cat": "nat", "priority": 22, "avg_cards": 4.1, "avg_corners": 10.1},
]

ELITE_TEAMS_BOOST = {
    "real madrid": 0.45, "bayern munich": 0.45, "bayern münchen": 0.45, "manchester city": 0.45,
    "man city": 0.45, "fc barcelona": 0.45, "barcelona": 0.45, "liverpool": 0.42, "liverpool fc": 0.42,
    "paris saint-germain": 0.42, "paris sg": 0.42, "psg": 0.42, "arsenal": 0.40, "arsenal fc": 0.40,
    "inter": 0.36, "inter milan": 0.36, "internazionale": 0.36, "borussia dortmund": 0.33, "dortmund": 0.33,
    "bayer leverkusen": 0.35, "leverkusen": 0.35, "atletico madrid": 0.32, "atlético madrid": 0.32,
    "juventus": 0.30, "ac milan": 0.30, "milan": 0.30, "napoli": 0.32, "ssc napoli": 0.32,
    "manchester united": 0.28, "man utd": 0.28, "aston villa": 0.28, "sporting cp": 0.30, "sporting": 0.30,
    "benfica": 0.28, "fc porto": 0.26, "porto": 0.26, "rb leipzig": 0.26, "as roma": 0.26, "roma": 0.26,
    "real sociedad": 0.22, "villarreal": 0.24, "villarreal cf": 0.24, "real betis": 0.22, "betis": 0.22,
    "marseille": 0.24, "lyon": 0.22, "psv eindhoven": 0.25, "psv": 0.25, "feyenoord": 0.22, "ajax": 0.24,
    "galatasaray": 0.24, "fenerbahce": 0.24, "fenerbahçe": 0.24, "celtic": 0.22, "rangers": 0.20,
    "olympiacos": 0.24, "olympiakos": 0.24, "paok": 0.22, "panathinaikos": 0.22,
    "fcsb": 0.22, "cfr cluj": 0.18, "universitatea craiova": 0.18, "rapid bucuresti": 0.15
}

# ==============================================================================
# UTILITARE MATEMATICE & POISSON / DIXON-COLES
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

def _decay_avg(values, alpha=0.85):
    if not values:
        return 0.0
    num, den = 0.0, 0.0
    for i, val in enumerate(reversed(values)):
        w = alpha ** i
        num += val * w
        den += w
    return num / den

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

def form_bonus_from_str(form_str):
    """Calculează bonusul/penalizarea de formă din șiruri precum 'WWDLW'."""
    if not form_str:
        return 0.0
    score = 0.0
    for ch in form_str.upper()[:5]:
        if ch == 'W':
            score += 0.06
        elif ch == 'D':
            score += 0.01
        elif ch == 'L':
            score -= 0.05
    return max(-0.22, min(0.25, score))

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

# ==============================================================================
# EXTRAGERE ISTORIC REAL CORNERE & CARTONAȘE (FĂRĂ CHEIE API)
# ==============================================================================
def fetch_public_team_stats():
    """Descarcă statisticile de cornere, cartonașe și goluri din baza publică Football-Data."""
    existing = _load_json(STATS_CACHE_FILE, {})
    if existing and existing.get("sync_date") == today_str() and len(existing) > 10:
        return existing

    team_stats = {"sync_date": today_str()}
    for csv_name in PUBLIC_STATS_CSVS:
        try:
            url = f"{FOOTBALL_DATA_BASE}/{csv_name}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    h = (row.get("HomeTeam") or "").strip()
                    a = (row.get("AwayTeam") or "").strip()
                    if not h or not a:
                        continue
                    for t in (h, a):
                        if t.lower() not in team_stats:
                            team_stats[t.lower()] = {"corners": [], "cards": [], "gf": [], "ga": []}
                    try:
                        hc, ac = float(row.get("HC") or 0), float(row.get("AC") or 0)
                        hy, ay = float(row.get("HY") or 0), float(row.get("AY") or 0)
                        hr, ar = float(row.get("HR") or 0), float(row.get("AR") or 0)
                        hg, ag = float(row.get("FTHG") or 0), float(row.get("FTAG") or 0)
                        if hc + ac > 0:
                            team_stats[h.lower()]["corners"].append(hc + ac)
                            team_stats[a.lower()]["corners"].append(hc + ac)
                            team_stats[h.lower()]["cards"].append(hy + hr + ay + ar)
                            team_stats[a.lower()]["cards"].append(hy + hr + ay + ar)
                        team_stats[h.lower()]["gf"].append(hg)
                        team_stats[h.lower()]["ga"].append(ag)
                        team_stats[a.lower()]["gf"].append(ag)
                        team_stats[a.lower()]["ga"].append(hg)
                    except (ValueError, TypeError):
                        continue
        except Exception:
            pass

    if len(team_stats) > 5:
        _save_json(STATS_CACHE_FILE, team_stats)
    return team_stats

def build_prediction_for_match(home_name, away_name, league_info, team_stats, odds_info=None, form_h="", form_a="", rec_h="", rec_a="", venue=""):
    h_low = home_name.lower()
    a_low = away_name.lower()
    h_boost = ELITE_TEAMS_BOOST.get(h_low, 0.0) + form_bonus_from_str(form_h)
    a_boost = ELITE_TEAMS_BOOST.get(a_low, 0.0) + form_bonus_from_str(form_a)

    h_hash = (int(hashlib.md5(h_low.encode("utf-8")).hexdigest()[:6], 16) % 100) / 160.0
    a_hash = (int(hashlib.md5(a_low.encode("utf-8")).hexdigest()[:6], 16) % 100) / 160.0

    h_hist = team_stats.get(h_low, {})
    a_hist = team_stats.get(a_low, {})

    if odds_info and odds_info.get("oh") and odds_info.get("od") and odds_info.get("oa"):
        oh, od, oa = odds_info["oh"], odds_info["od"], odds_info["oa"]
        p_h, p_d, p_a = implied_probs_sq(oh, od, oa)
        o_over_val = odds_info.get("over25") or 1.85
        o_under_val = odds_info.get("under25") or 1.95
        bookmaker = odds_info.get("bookmaker", "Cote Oficiale")
        sr_over = math.sqrt(1.0 / o_over_val)
        sr_under = math.sqrt(1.0 / o_under_val)
        target_over25 = sr_over / (sr_over + sr_under)
        lam_h, lam
