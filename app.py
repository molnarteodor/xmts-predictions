import os
import re
import json
import math
import hashlib
import urllib.request
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
# CONFIGURARE 100% AUTONOMĂ (FĂRĂ FIȘIERE CSV, FĂRĂ CHEIE API)
# ==============================================================================
CACHE_VERSION = "v9_pure_api_autonomous"
CACHE_FILE = "matches_cache.json"
STATS_CACHE_FILE = "team_stats_cache.json"
SYNC_LOCK = threading.Lock()

CONFIDENCE_THRESHOLD = 0.52
LOW_RISK_THRESHOLD = 0.62

CORNERS_LINES = [8.5, 9.5, 10.5]
CARDS_LINES = [3.5, 4.5, 5.5]
DIXON_COLES_RHO_BASE = -0.08

LEAGUE_META = {
    "CL":  {"name": "UEFA Champions League",       "icon": "🏆", "cat": "cl",  "priority": 1,  "avg_cards": 4.3, "avg_corners": 9.9},
    "EL":  {"name": "UEFA Europa League",          "icon": "🟠", "cat": "el",  "priority": 2,  "avg_cards": 4.6, "avg_corners": 9.6},
    "ECL": {"name": "UEFA Conference League",      "icon": "🟢", "cat": "el",  "priority": 3,  "avg_cards": 4.5, "avg_corners": 9.5},
    "E0":  {"name": "Premier League (Anglia)",     "icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "cat": "nat", "priority": 10, "avg_cards": 4.1, "avg_corners": 10.4},
    "SP1": {"name": "La Liga (Spania)",            "icon": "🇪🇸", "cat": "nat", "priority": 11, "avg_cards": 5.1, "avg_corners": 9.5},
    "I1":  {"name": "Serie A (Italia)",            "icon": "🇮🇹", "cat": "nat", "priority": 12, "avg_cards": 4.7, "avg_corners": 9.7},
    "D1":  {"name": "Bundesliga (Germania)",       "icon": "🇩🇪", "cat": "nat", "priority": 13, "avg_cards": 4.2, "avg_corners": 9.9},
    "F1":  {"name": "Ligue 1 (Franța)",            "icon": "🇫🇷", "cat": "nat", "priority": 14, "avg_cards": 4.0, "avg_corners": 9.4},
    "RO1": {"name": "SuperLiga (România)",         "icon": "🇷🇴", "cat": "nat", "priority": 15, "avg_cards": 4.8, "avg_corners": 9.1},
    "N1":  {"name": "Eredivisie (Olanda)",         "icon": "🇳🇱", "cat": "nat", "priority": 16, "avg_cards": 3.5, "avg_corners": 10.2},
    "P1":  {"name": "Primeira Liga (Portugalia)",  "icon": "🇵🇹", "cat": "nat", "priority": 17, "avg_cards": 5.2, "avg_corners": 10.0},
    "T1":  {"name": "Süper Lig (Turcia)",          "icon": "🇹🇷", "cat": "nat", "priority": 18, "avg_cards": 5.0, "avg_corners": 9.6},
    "B1":  {"name": "Jupiler Pro League (Belgia)", "icon": "🇧🇪", "cat": "nat", "priority": 19, "avg_cards": 4.3, "avg_corners": 9.8},
    "G1":  {"name": "Super League (Grecia)",       "icon": "🇬🇷", "cat": "nat", "priority": 20, "avg_cards": 4.9, "avg_corners": 9.0},
    "SC0": {"name": "Premiership (Scoția)",        "icon": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "cat": "nat", "priority": 21, "avg_cards": 4.2, "avg_corners": 10.3},
    "E1":  {"name": "Championship (Anglia)",       "icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "cat": "nat", "priority": 22, "avg_cards": 4.1, "avg_corners": 10.1},
    "SP2": {"name": "La Liga 2 (Spania)",          "icon": "🇪🇸", "cat": "nat", "priority": 23, "avg_cards": 5.3, "avg_corners": 9.2},
    "I2":  {"name": "Serie B (Italia)",            "icon": "🇮🇹", "cat": "nat", "priority": 24, "avg_cards": 4.9, "avg_corners": 9.4},
    "D2":  {"name": "Bundesliga 2 (Germania)",     "icon": "🇩🇪", "cat": "nat", "priority": 25, "avg_cards": 4.4, "avg_corners": 10.0},
}

ESPN_SLUG_TO_CODE = {
    "uefa.champions": "CL",
    "uefa.europa": "EL",
    "uefa.europa.conf": "ECL",
    "eng.1": "E0",
    "esp.1": "SP1",
    "ita.1": "I1",
    "ger.1": "D1",
    "fra.1": "F1",
    "rou.1": "RO1",
    "ned.1": "N1",
    "por.1": "P1",
    "tur.1": "T1",
    "bel.1": "B1",
    "gre.1": "G1",
    "sco.1": "SC0",
    "eng.2": "E1",
}

ELITE_TEAMS_BOOST = {
    "real madrid": 0.45, "bayern munich": 0.45, "bayern münchen": 0.45, "manchester city": 0.45,
    "man city": 0.45, "fc barcelona": 0.45, "barcelona": 0.45, "liverpool": 0.42, "liverpool fc": 0.42,
    "paris saint-germain": 0.42, "paris sg": 0.42, "psg": 0.42, "arsenal": 0.40, "arsenal fc": 0.40,
    "inter": 0.36, "inter milan": 0.36, "borussia dortmund": 0.33, "dortmund": 0.33,
    "bayer leverkusen": 0.35, "leverkusen": 0.35, "atletico madrid": 0.32, "atlético madrid": 0.32,
    "juventus": 0.30, "ac milan": 0.30, "milan": 0.30, "napoli": 0.32, "ssc napoli": 0.32,
    "manchester united": 0.28, "man utd": 0.28, "aston villa": 0.28, "sporting cp": 0.30, "sporting": 0.30,
    "benfica": 0.28, "fc porto": 0.26, "porto": 0.26, "rb leipzig": 0.26, "as roma": 0.26, "roma": 0.26,
    "real sociedad": 0.22, "villarreal": 0.24, "villarreal cf": 0.24, "real betis": 0.22, "betis": 0.22,
    "marseille": 0.24, "lyon": 0.22, "psv eindhoven": 0.25, "psv": 0.25, "feyenoord": 0.22, "ajax": 0.24,
    "galatasaray": 0.24, "fenerbahce": 0.24, "fenerbahçe": 0.24, "celtic": 0.22, "rangers": 0.20,
    "olympiacos": 0.25, "olympiakos": 0.25, "paok": 0.24, "panathinaikos": 0.24,
    "fcsb": 0.22, "cfr cluj": 0.18, "universitatea craiova": 0.18
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
        scored.append(("Șansă Dublă X2", p_draw + p_away, 0.56 + ((p_draw + p_away) - 0.64) * 0.90))
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

def american_to_decimal(am_odds):
    try:
        val = float(am_odds)
        if val > 0:
            return round(1.0 + (val / 100.0), 2)
        elif val < 0:
            return round(1.0 + (100.0 / abs(val)), 2)
    except Exception:
        pass
    return None

def build_prediction(home_name, away_name, league_code, odds_info=None, form_h="", form_a=""):
    l_meta = LEAGUE_META.get(league_code, {"name": league_code, "icon": "⚽", "cat": "nat", "priority": 50, "avg_cards": 4.3, "avg_corners": 9.7})
    h_low = home_name.lower()
    a_low = away_name.lower()

    h_boost = ELITE_TEAMS_BOOST.get(h_low, 0.0) + form_bonus_from_str(form_h)
    a_boost = ELITE_TEAMS_BOOST.get(a_low, 0.0) + form_bonus_from_str(form_a)
    h_hash = (int(hashlib.md5(h_low.encode("utf-8")).hexdigest()[:6], 16) % 100) / 160.0
    a_hash = (int(hashlib.md5(a_low.encode("utf-8")).hexdigest()[:6], 16) % 100) / 160.0

    if odds_info and odds_info.get("oh") and odds_info.get("od") and odds_info.get("oa"):
        oh, od, oa = odds_info["oh"], odds_info["od"], odds_info["oa"]
        p_h, p_d, p_a = implied_probs_sq(oh, od, oa)
        o_over_val = odds_info.get("over25") or 1.85
        o_under_val = odds_info.get("under25") or 1.95
        bookmaker = odds_info.get("bookmaker", "Cote Oficiale")
        sr_o = math.sqrt(1.0 / o_over_val)
        sr_u = math.sqrt(1.0 / o_under_val)
        target_over25 = sr_o / (sr_o + sr_u)
        lam_h, lam_a = calibrate_lambdas(p_h, p_d, p_a, DIXON_COLES_RHO_BASE, target_over25)
    else:
        lam_h = round(max(0.55, min(3.10, 1.30 + h_boost + (h_hash - 0.25))), 2)
        lam_a = round(max(0.45, min(2.90, 1.08 + a_boost + (a_hash - 0.25))), 2)
        target_over25 = None
        bookmaker = "Model AI Autonom"
        oh = od = oa = o_over_val = o_under_val = None

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

    if not oh:
        oh = round(max(1.18, min(9.50, 0.95 / max(0.08, p_home))), 2)
        od = round(max(2.80, min(6.50, 0.95 / max(0.12, p_draw))), 2)
        oa = round(max(1.22, min(11.0, 0.95 / max(0.08, p_away))), 2)
    if not o_over_val:
        o_over_val = round(max(1.35, min(2.70, 0.95 / max(0.20, p_over[2.5]))), 2)
        o_under_val = round(max(1.35, min(2.70, 0.95 / max(0.20, p_under[2.5]))), 2)

    odd_1x = round(1.0 / max(0.05, (p_home + p_draw) * 0.95), 2)
    odd_x2 = round(1.0 / max(0.05, (p_away + p_draw) * 0.95), 2)
    odd_o15 = round(1.0 / max(0.05, p_over[1.5] * 0.95), 2)
    odd_btts = round(1.0 / max(0.05, p_btts * 0.95), 2)

    closeness = max(0.0, 0.35 - abs(p_home - p_away))
    exp_cards = round(max(2.8, min(6.8, l_meta.get("avg_cards", 4.4) + closeness * 1.4 + (h_hash - a_hash) * 0.5)), 1)
    exp_corners = round(max(7.2, min(12.8, l_meta.get("avg_corners", 9.7) + (lam_h + lam_a - 2.5) * 0.85)), 1)

    def over_prob_line(exp_val, line):
        return sum(poisson_pmf(k, exp_val) for k in range(math.ceil(line), 28))

    corners_cards = {
        "exp_corners": exp_corners,
        "exp_cards": exp_cards,
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
        "league": l_meta["name"],
        "league_code": league_code,
        "league_icon": l_meta["icon"],
        "league_priority": l_meta["priority"],
        "category": l_meta["cat"],
        "is_cl": l_meta["cat"] == "cl",
        "is_el": l_meta["cat"] == "el",
        "principal": best_market,
        "principal_pct": round(best_p * 100, 1),
        "risc": risc,
        "exp_goals_home": lam_h,
        "exp_goals_away": lam_a,
        "bookmaker": bookmaker,
        "market_options": market_options,
        "corners_cards": corners_cards,
        "form_home": form_h or "WWDWL",
        "form_away": form_a or "WDLWD",
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
# DOWNLOADER PARALEL PENTRU ESPN (FĂRĂ FIȘIERE EXTERNE)
# ==============================================================================
def _download_espn_slug(slug, dates_param):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={dates_param}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return slug, data.get("events", [])
    except Exception:
        return slug, []

def sync_daily_data(force=False):
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

        base_dt = now_dt()
        dates_param = f"{(base_dt - timedelta(days=2)).strftime('%Y%m%d')}-{(base_dt + timedelta(days=10)).strftime('%Y%m%d')}"
        matches_map = {}

        with ThreadPoolExecutor(max_workers=12) as ex:
            futures = [ex.submit(_download_espn_slug, slug, dates_param) for slug in ESPN_SLUG_TO_CODE.keys()]
            for fut in as_completed(futures):
                try:
                    slug, events = fut.result()
                    l_code = ESPN_SLUG_TO_CODE[slug]
                    for ev in events:
                        comps = ev.get("competitions", [])
                        if not comps:
                            continue
                        comp = comps[0]
                        competitors = comp.get("competitors", [])
                        if len(competitors) < 2:
                            continue

                        h_c = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                        a_c = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                        h_name = (h_c.get("team", {}).get("displayName") or h_c.get("team", {}).get("name") or "").strip()
                        a_name = (a_c.get("team", {}).get("displayName") or a_c.get("team", {}).get("name") or "").strip()
                        if not h_name or not a_name:
                            continue

                        raw_iso = comp.get("date") or ev.get("date") or ""
                        m_date = raw_iso[:10]
                        m_time = "20:00"
                        try:
                            dt_ro = datetime.strptime(raw_iso[:16], "%Y-%m-%dT%H:%M") + timedelta(hours=3)
                            m_date = dt_ro.strftime("%Y-%m-%d")
                            m_time = dt_ro.strftime("%H:%M")
                        except Exception:
                            pass

                        st = comp.get("status", {}).get("type", {})
                        done = bool(st.get("completed"))
                        rh = int(h_c.get("score", 0)) if done and str(h_c.get("score", "")).isdigit() else None
                        ra = int(a_c.get("score", 0)) if done and str(a_c.get("score", "")).isdigit() else None

                        odds_info = None
                        odds_list = comp.get("odds", [])
                        if odds_list:
                            o_obj = odds_list[0]
                            oh = american_to_decimal(o_obj.get("homeTeamOdds", {}).get("moneyLine"))
                            oa = american_to_decimal(o_obj.get("awayTeamOdds", {}).get("moneyLine"))
                            od = american_to_decimal(o_obj.get("drawOdds", {}).get("moneyLine"))
                            if oh and od and oa:
                                odds_info = {"oh": oh, "od": od, "oa": oa, "bookmaker": o_obj.get("provider", {}).get("name", "ESPN Bet")}

                        pred = build_prediction(
                            h_name, a_name, l_code, odds_info=odds_info,
                            form_h=h_c.get("form") or "", form_a=a_c.get("form") or ""
                        )

                        key = f"{m_date}_{h_name.lower()}_{a_name.lower()}"
                        matches_map[key] = {
                            "date": m_date,
                            "time": m_time,
                            "home": h_name,
                            "away": a_name,
                            "has_result": done and rh is not None and ra is not None,
                            "res_home": rh,
                            "res_away": ra,
                            **pred
                        }
                except Exception:
                    pass

        all_matches = list(matches_map.values())
        all_matches.sort(key=lambda m: (m["date"], m["league_priority"], m.get("time") or "23:59", -(m.get("principal_pct") or 0)))

        cache_data = {
            "version": CACHE_VERSION,
            "sync_date": today,
            "uploaded_at": now_dt().strftime("%Y-%m-%d %H:%M"),
            "matches": all_matches if all_matches else (existing.get("matches", []) if existing else []),
            "api_active": True,
            "source": "100% Autonom (Fără Fișiere)"
        }
        _save_json(CACHE_FILE, cache_data)
        return cache_data

# ==============================================================================
# ENDPOINT-URI FLASK & INTERFAȚA WEB
# ==============================================================================
@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    data = sync_daily_data(force=False)
    return jsonify(data)

@app.route('/api/refresh-from-github', methods=['POST'])
def refresh_from_github():
    data = sync_daily_data(force=True)
    return jsonify({"status": "success", "sync_date": data.get("sync_date"), "count": len(data.get("matches", []))})

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XMTS AI · Autonomous Engine</title>
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

  .header-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
  .sync-btn {
    background: #1f1f1f; border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 6px 10px; border-radius: 8px; font-size: 11px; font-weight: 700; cursor: pointer;
  }
  .sync-btn:hover { border-color: var(--accent-gold); color: #fff; }

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

  .date-picker-bar { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 12px; scrollbar-width: none; scroll-behavior: smooth; }
  .date-picker-bar::-webkit-scrollbar { display: none; }
  .date-chip {
    background: #1f1f1f; border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: bold; white-space: nowrap; cursor: pointer;
  }
  .date-chip.active { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }

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
    <button class="sync-btn" id="syncBtn" onclick="forceSync()">🔄 Sincronizează</button>
  </div>

  <div class="tabs-wrapper">
    <button class="tab-btn active" onclick="switchTab('meciuri', this)">⚽ Ligi Naționale</button>
    <button class="tab-btn" onclick="switchTab('cl', this)" style="border-color:var(--accent-cyan); color:var(--accent-cyan);">🏆 Champions League</button>
    <button class="tab-btn" onclick="switchTab('el', this)" style="border-color:var(--accent-orange); color:var(--accent-orange);">🟠 Europa League</button>
    <button class="tab-btn" onclick="switchTab('bilete', this)" style="border-color:var(--accent-gold); color:var(--accent-gold);">🎟️ Generator Bilete</button>
  </div>

  <div id="dateSelectorContainer"></div>
  <div id="leagueFilterContainer"></div>
  <div id="content"><div class="glass-card" style="text-align:center;">Se încarcă meciurile autonom...</div></div>
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
  if (!datesSet || !datesSet.length) return 'ALL';
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
  btn.innerText = isHidden ? 'Ascunde Analiză' : 'Deschide Analiză, Formă & Cartonașe';
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
  const cardsHtml = `<div>🟨 Estimat cartonașe: ~<b>${cc.exp_cards || 4.3}</b> | Peste 3.5: <b style="color:#34d399;">${cc.cards_over ? cc.cards_over['3.5'] : 62}%</b></div>`;
  const cornersHtml = `<div>🚩 Estimat cornere: ~<b>${cc.exp_corners || 9.6}</b> | Peste 8.5: <b style="color:#34d399;">${cc.corners_over ? cc.corners_over['8.5'] : 64}%</b></div>`;
  const formHtml = `
    <div>🏠 <b>${m.home}:</b> Ultimele 5: <b style="color:var(--accent-gold); letter-spacing:1px;">${m.form_home}</b></div>
    <div style="margin-top:4px;">✈️ <b>${m.away}:</b> Ultimele 5: <b style="color:var(--accent-cyan); letter-spacing:1px;">${m.form_away}</b></div>
  `;

  return `
    <div class="glass-card">
      <div class="match-basic">
        <div style="font-size:11px;color:var(--text-muted);display:flex;justify-content:space-between;align-items:center;">
          <span>${m.date} · ${m.bookmaker || 'Model AI'}</span>
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

      <button class="btn-expand" onclick="toggleGoldenPanel(this)">Deschide Analiză, Formă & Cartonașe</button>
      
      <div class="golden-panel">
        <div class="golden-header">PROBABILITĂȚI & EXPECTED GOALS</div>
        <div class="h2h-row">
          <div class="h2h-val">${m.exp_goals_home}</div>
          <div class="h2h-label">Expected Goals (xG)</div>
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
          <div class="acc-item"><div class="acc-header" onclick="toggleAccordion(this)"><div>📈 Formă Echipe</div><div>▼</div></div><div class="acc-body" style="display:block;">${formHtml}</div></div>
          <div class="acc-item"><div class="acc-header" onclick="toggleAccordion(this)"><div>🟨 Istoric Cartonașe</div><div>▼</div></div><div class="acc-body" style="display:block;">${cardsHtml}</div></div>
          <div class="acc-item"><div class="acc-header" onclick="toggleAccordion(this)"><div>🚩 Estimare Cornere</div><div>▼</div></div><div class="acc-body">${cornersHtml}</div></div>
        </div>
      </div>
    </div>`;
}

function getTabMatches() {
  return (state.matches || []).filter(m => {
    if (currentTab === 'cl') return m.is_cl;
    if (currentTab === 'el') return m.is_el;
    return !m.is_cl && !m.is_el;
  });
}

function renderDateSelector() {
  if (currentTab === 'bilete') return '';
  const tabMatches = getTabMatches();
  const datesSet = [...new Set(tabMatches.map(m => m.date).filter(Boolean))].sort();

  if (datesSet.length > 0) {
    if (currentTab === 'cl') {
      if (!selectedClDate || (selectedClDate !== 'ALL' && !datesSet.includes(selectedClDate))) selectedClDate = getSmartDefaultDate(datesSet);
    } else if (currentTab === 'el') {
      if (!selectedElDate || (selectedElDate !== 'ALL' && !datesSet.includes(selectedElDate))) selectedElDate = getSmartDefaultDate(datesSet);
    } else {
      if (!selectedDate || (selectedDate !== 'ALL' && !datesSet.includes(selectedDate))) selectedDate = getSmartDefaultDate(datesSet);
    }
  }

  let activeD = (currentTab === 'cl') ? selectedClDate : (currentTab === 'el' ? selectedElDate : selectedDate);
  let chips = `<button class="date-chip ${activeD === 'ALL' ? 'active' : ''}" onclick="selectDate('ALL')">📅 Toate (${tabMatches.length})</button>`;
  chips += datesSet.map(d => `
    <button class="date-chip ${activeD === d ? 'active' : ''}" id="chip-${d}" onclick="selectDate('${d}')">${d}</button>
  `).join('');

  return `<div class="date-picker-bar">${chips}</div>`;
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
    return `<div class="glass-card" style="text-align:center;">Niciun meci găsit. Apasă pe „📅 Toate” din susul paginii.</div>`;
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
        ${grp.items.slice(0, 60).map(renderMatchCard).join('')}
      </div>
    `;
  }).join('');
}

function renderTicketGenerator() {
  const today = getTodayStr();
  let upcoming = (state.matches || []).filter(m => !m.has_result && m.date >= today);
  if (upcoming.length < 5) upcoming = (state.matches || []).filter(m => !m.has_result);

  let pool = [];
  upcoming.forEach(m => {
    if (m.market_options) {
      m.market_options.forEach(opt => {
        if (opt.prob >= 0.52 && opt.odds >= 1.25 && opt.odds <= 3.50) {
          pool.push({
            match: `${m.home} - ${m.away}`,
            league: `${m.league} (${m.date})`,
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
      <div style="font-weight:800; font-size:16px; margin-bottom:10px; color:var(--accent-gold);">🎟️ Generator Bilete Inteligente</div>
      <div style="font-size:12px; color:var(--text-muted); margin-bottom:15px;">Selectează automat cele mai sigure pronosticuri.</div>
      <div class="ticket-config">${oddsButtons}</div>
      <div style="background:rgba(0,0,0,0.5); border:1px solid var(--card-border); border-radius:12px; padding:12px; margin-top:15px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid #333; padding-bottom:8px;">
          <span style="font-weight:bold; font-size:13px;">Cotă Țintă: ~${selectedTargetOdds}</span>
          <span style="background:var(--accent-gold); color:#000; font-weight:800; padding:4px 10px; border-radius:8px; font-size:14px;">Cotă Totală: ${currentOdds.toFixed(2)}</span>
        </div>
        ${picksHtml || '<div style="text-align:center; padding:20px; color:var(--text-muted);">Nu sunt suficiente meciuri viitoare.</div>'}
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

  if (!state.matches || !state.matches.length) {
    dateContainer.innerHTML = '';
    leagueContainer.innerHTML = '';
    c.innerHTML = '<div class="glass-card" style="text-align:center;">Se încarcă meciurile autonom... Apasă pe „🔄 Sincronizează”.</div>';
    return;
  }

  dateContainer.innerHTML = renderDateSelector();

  if (currentTab === 'bilete') {
    leagueContainer.innerHTML = '';
    c.innerHTML = renderTicketGenerator();
    return;
  }

  const activeD = (currentTab === 'cl') ? selectedClDate : (currentTab === 'el' ? selectedElDate : selectedDate);
  const tabMatches = getTabMatches();
  const dayMatches = (activeD === 'ALL') ? tabMatches : tabMatches.filter(m => m.date === activeD);

  leagueContainer.innerHTML = renderLeagueFilter(dayMatches);
  const filtered = (currentTab === 'meciuri' && selectedLeagueFilter !== 'ALL')
    ? dayMatches.filter(m => m.league === selectedLeagueFilter)
    : dayMatches;

  c.innerHTML = renderGroupedSections(filtered);
}

function switchTab(t, btn) {
  currentTab = t;
  selectedLeagueFilter = 'ALL';
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  render();
}

async function forceSync() {
  const btn = document.getElementById('syncBtn');
  btn.innerText = '⏳ Se încarcă...';
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
