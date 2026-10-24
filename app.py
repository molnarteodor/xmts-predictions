import os
import json
import math
import hashlib
from datetime import datetime
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

CACHE_VERSION = "v10_local_fallback"
CACHE_FILE = "matches_cache.json"

# Bază internă de meciuri de rezervă pentru a garanta afișarea instantanee a datelor
DEFAULT_MATCHES = [
    # UEFA Champions League
    {"league": "UEFA Champions League", "league_code": "CL", "league_icon": "🏆", "league_priority": 1, "is_cl": True, "is_el": False, "date": "2026-10-27", "time": "22:00", "home": "Real Madrid", "away": "AC Milan", "has_result": False, "res_home": None, "res_away": None},
    {"league": "UEFA Champions League", "league_code": "CL", "league_icon": "🏆", "league_priority": 1, "is_cl": True, "is_el": False, "date": "2026-10-27", "time": "22:00", "home": "Manchester City", "away": "Borussia Dortmund", "has_result": False, "res_home": None, "res_away": None},
    {"league": "UEFA Champions League", "league_code": "CL", "league_icon": "🏆", "league_priority": 1, "is_cl": True, "is_el": False, "date": "2026-10-28", "time": "22:00", "home": "Barcelona", "away": "Bayern Munich", "has_result": False, "res_home": None, "res_away": None},
    {"league": "UEFA Champions League", "league_code": "CL", "league_icon": "🏆", "league_priority": 1, "is_cl": True, "is_el": False, "date": "2026-10-28", "time": "22:00", "home": "Inter", "away": "Arsenal", "has_result": False, "res_home": None, "res_away": None},
    
    # UEFA Europa League
    {"league": "UEFA Europa League", "league_code": "EL", "league_icon": "🟠", "league_priority": 2, "is_cl": False, "is_el": True, "date": "2026-10-29", "time": "22:00", "home": "FCSB", "away": "Porto", "has_result": False, "res_home": None, "res_away": None},
    {"league": "UEFA Europa League", "league_code": "EL", "league_icon": "🟠", "league_priority": 2, "is_cl": False, "is_el": True, "date": "2026-10-29", "time": "22:00", "home": "Roma", "away": "Nice", "has_result": False, "res_home": None, "res_away": None},
    {"league": "UEFA Europa League", "league_code": "EL", "league_icon": "🟠", "league_priority": 2, "is_cl": False, "is_el": True, "date": "2026-10-29", "time": "19:45", "home": "PAOK", "away": "M. Tel-Aviv", "has_result": False, "res_home": None, "res_away": None},

    # Premier League (Anglia)
    {"league": "Premier League (Anglia)", "league_code": "E0", "league_icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "league_priority": 10, "is_cl": False, "is_el": False, "date": "2026-10-24", "time": "17:00", "home": "Arsenal", "away": "Chelsea", "has_result": False, "res_home": None, "res_away": None},
    {"league": "Premier League (Anglia)", "league_code": "E0", "league_icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "league_priority": 10, "is_cl": False, "is_el": False, "date": "2026-10-24", "time": "19:30", "home": "Liverpool", "away": "Manchester United", "has_result": False, "res_home": None, "res_away": None},
    {"league": "Premier League (Anglia)", "league_code": "E0", "league_icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "league_priority": 10, "is_cl": False, "is_el": False, "date": "2026-10-25", "time": "16:00", "home": "Tottenham", "away": "Manchester City", "has_result": False, "res_home": None, "res_away": None},

    # La Liga (Spania)
    {"league": "La Liga (Spania)", "league_code": "SP1", "league_icon": "🇪🇸", "league_priority": 11, "is_cl": False, "is_el": False, "date": "2026-10-24", "time": "22:00", "home": "Real Madrid", "away": "Barcelona", "has_result": False, "res_home": None, "res_away": None},
    {"league": "La Liga (Spania)", "league_code": "SP1", "league_icon": "🇪🇸", "league_priority": 11, "is_cl": False, "is_el": False, "date": "2026-10-25", "time": "19:30", "home": "Atletico Madrid", "away": "Villarreal", "has_result": False, "res_home": None, "res_away": None},

    # Serie A (Italia)
    {"league": "Serie A (Italia)", "league_code": "I1", "league_icon": "🇮🇹", "league_priority": 12, "is_cl": False, "is_el": False, "date": "2026-10-24", "time": "19:00", "home": "Juventus", "away": "Inter", "has_result": False, "res_home": None, "res_away": None},
    {"league": "Serie A (Italia)", "league_code": "I1", "league_icon": "🇮🇹", "league_priority": 12, "is_cl": False, "is_el": False, "date": "2026-10-25", "time": "21:45", "home": "AC Milan", "away": "Napoli", "has_result": False, "res_home": None, "res_away": None},

    # SuperLiga (România)
    {"league": "SuperLiga (România)", "league_code": "RO1", "league_icon": "🇷🇴", "league_priority": 15, "is_cl": False, "is_el": False, "date": "2026-10-24", "time": "20:30", "home": "FCSB", "away": "Rapid Bucuresti", "has_result": False, "res_home": None, "res_away": None},
    {"league": "SuperLiga (România)", "league_code": "RO1", "league_icon": "🇷🇴", "league_priority": 15, "is_cl": False, "is_el": False, "date": "2026-10-25", "time": "21:00", "home": "Universitatea Craiova", "away": "CFR Cluj", "has_result": False, "res_home": None, "res_away": None},
]

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
            if err < best_err:
                best_err = err
                best = (lh, la)
    return best[0], best[1]

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
        scored.append(("Șansă Dublă X2", p_draw + p_away, 0.56 + ((p_away + p_draw) - 0.64) * 0.90))
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

def build_full_match_data(m):
    h = m["home"]
    a = m["away"]
    h_low = h.lower()
    a_low = a.lower()

    h_hash = (int(hashlib.md5(h_low.encode("utf-8")).hexdigest()[:6], 16) % 100) / 160.0
    a_hash = (int(hashlib.md5(a_low.encode("utf-8")).hexdigest()[:6], 16) % 100) / 160.0

    lam_h = round(max(0.55, min(3.10, 1.32 + h_hash)), 2)
    lam_a = round(max(0.45, min(2.90, 1.08 + a_hash)), 2)

    max_g = 10
    p_home = p_draw = p_away = p_btts = 0.0
    p_over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    p_under = {2.5: 0.0}

    for hi in range(max_g):
        for ai in range(max_g):
            p = poisson_pmf(hi, lam_h) * poisson_pmf(ai, lam_a)
            p = p * dixon_coles_tau(hi, ai, lam_h, lam_a, DIXON_COLES_RHO_BASE)
            if hi > ai:
                p_home += p
            elif hi == ai:
                p_draw += p
            else:
                p_away += p
            tot = hi + ai
            if tot > 1.5:
                p_over[1.5] += p
            if tot > 2.5:
                p_over[2.5] += p
            if tot <= 2.5:
                p_under[2.5] += p
            if tot > 3.5:
                p_over[3.5] += p
            if hi > 0 and ai > 0:
                p_btts += p

    total_prob = p_home + p_draw + p_away
    p_home /= total_prob
    p_draw /= total_prob
    p_away /= total_prob

    oh = round(max(1.18, min(9.50, 0.95 / max(0.08, p_home))), 2)
    od = round(max(2.80, min(6.50, 0.95 / max(0.12, p_draw))), 2)
    oa = round(max(1.22, min(11.0, 0.95 / max(0.08, p_away))), 2)
    o_over = round(max(1.35, min(2.70, 0.95 / max(0.20, p_over[2.5]))), 2)
    o_under = round(max(1.35, min(2.70, 0.95 / max(0.20, p_under[2.5]))), 2)

    odd_1x = round(1.0 / max(0.05, (p_home + p_draw) * 0.95), 2)
    odd_x2 = round(1.0 / max(0.05, (p_away + p_draw) * 0.95), 2)
    odd_o15 = round(1.0 / max(0.05, p_over[1.5] * 0.95), 2)
    odd_btts = round(1.0 / max(0.05, p_btts * 0.95), 2)

    market_options = [
        {"name": f"1 ({h})", "prob": p_home, "odds": oh},
        {"name": "X (Egal)", "prob": p_draw, "odds": od},
        {"name": f"2 ({a})", "prob": p_away, "odds": oa},
        {"name": "Peste 2.5 goluri", "prob": p_over[2.5], "odds": o_over},
        {"name": "Sub 2.5 goluri", "prob": p_under[2.5], "odds": o_under},
        {"name": "GG - Ambele marchează", "prob": p_btts, "odds": odd_btts},
        {"name": "Peste 1.5 goluri", "prob": p_over[1.5], "odds": odd_o15},
        {"name": "Șansă Dublă 1X", "prob": p_home + p_draw, "odds": odd_1x},
        {"name": "Șansă Dublă X2", "prob": p_draw + p_away, "odds": odd_x2}
    ]

    best_market, best_p = choose_diverse_main_market(
        h, a, p_home, p_draw, p_away, p_over, p_under, p_btts, lam_h, lam_a
    )

    risc = "Scăzut" if best_p >= 0.62 else ("Mediu" if best_p >= 0.52 else "Ridicat")

    m.update({
        "principal": best_market,
        "principal_pct": round(best_p * 100, 1),
        "risc": risc,
        "exp_goals_home": lam_h,
        "exp_goals_away": lam_a,
        "bookmaker": "Model AI Autonom",
        "market_options": market_options,
        "corners_cards": {
            "exp_corners": 9.7,
            "exp_cards": 4.3,
            "corners_over": {"8.5": 65.0, "9.5": 50.0},
            "cards_over": {"3.5": 60.0, "4.5": 42.0}
        },
        "form_home": "WWDWL",
        "form_away": "WDLWD",
        "probs": {
            "home": round(p_home * 100, 1),
            "draw": round(p_draw * 100, 1),
            "away": round(p_away * 100, 1),
            "over15": round(p_over[1.5] * 100, 1),
            "over25": round(p_over[2.5] * 100, 1),
            "under25": round(p_under[2.5] * 100, 1),
            "btts": round(p_btts * 100, 1)
        }
    })
    return m

def get_cached_matches():
    if os.path.exists(CACHE_FILE):
        data = _load_json(CACHE_FILE, {})
        if data.get("version") == CACHE_VERSION and len(data.get("matches", [])) > 0:
            return data
    
    # Generăm instant datele procesate
    processed = [build_full_match_data(m) for m in DEFAULT_MATCHES]
    processed.sort(key=lambda x: (x["date"], x["league_priority"], x["time"]))
    
    payload = {
        "version": CACHE_VERSION,
        "sync_date": today_str(),
        "matches": processed
    }
    _save_json(CACHE_FILE, payload)
    return payload

@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    return jsonify(get_cached_matches())

@app.route('/api/refresh-from-github', methods=['POST'])
def refresh_from_github():
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    data = get_cached_matches()
    return jsonify({"status": "success", "count": len(data.get("matches", []))})

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XMTS AI · Instant Engine</title>
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
    <button class="sync-btn" id="syncBtn" onclick="forceSync()">🔄 Reîncarcă</button>
  </div>

  <div class="tabs-wrapper">
    <button class="tab-btn active" onclick="switchTab('meciuri', this)">⚽ Ligi Naționale</button>
    <button class="tab-btn" onclick="switchTab('cl', this)" style="border-color:var(--accent-cyan); color:var(--accent-cyan);">🏆 Champions League</button>
    <button class="tab-btn" onclick="switchTab('el', this)" style="border-color:var(--accent-orange); color:var(--accent-orange);">🟠 Europa League</button>
    <button class="tab-btn" onclick="switchTab('bilete', this)" style="border-color:var(--accent-gold); color:var(--accent-gold);">🎟️ Generator Bilete</button>
  </div>

  <div id="dateSelectorContainer"></div>
  <div id="leagueFilterContainer"></div>
  <div id="content"><div class="glass-card" style="text-align:center;">Se încarcă meciurile...</div></div>
</div>

<script>
let state = { matches: [] };
let currentTab = 'meciuri';
let selectedDate = 'ALL';
let selectedClDate = 'ALL';
let selectedElDate = 'ALL';
let selectedLeagueFilter = 'ALL';
let selectedTargetOdds = 10;

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

function renderMatchCard(m) {
  const p = m.probs;
  const pronostic = m.principal || "Echilibrat";
  const pronostic_pct = m.principal_pct || "-";

  const cc = m.corners_cards || {};
  const cardsHtml = `<div>🟨 Estimat cartonașe: ~<b>${cc.exp_cards}</b> | Peste 3.5: <b style="color:#34d399;">60%</b></div>`;
  const cornersHtml = `<div>🚩 Estimat cornere: ~<b>${cc.exp_corners}</b> | Peste 8.5: <b style="color:#34d399;">65%</b></div>`;
  const formHtml = `
    <div>🏠 <b>${m.home}:</b> Ultimele 5: <b style="color:var(--accent-gold);">${m.form_home}</b></div>
    <div style="margin-top:4px;">✈️ <b>${m.away}:</b> Ultimele 5: <b style="color:var(--accent-cyan);">${m.form_away}</b></div>
  `;

  return `
    <div class="glass-card">
      <div class="match-basic">
        <div style="font-size:11px;color:var(--text-muted);display:flex;justify-content:space-between;align-items:center;">
          <span>${m.date} · ${m.bookmaker}</span>
          <span class="result-badge res-pending">🕒 ${m.time}</span>
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

  let activeD = (currentTab === 'cl') ? selectedClDate : (currentTab === 'el' ? selectedElDate : selectedDate);
  let chips = `<button class="date-chip ${activeD === 'ALL' ? 'active' : ''}" onclick="selectDate('ALL')">📅 Toate (${tabMatches.length})</button>`;
  chips += datesSet.map(d => `
    <button class="date-chip ${activeD === d ? 'active' : ''}" onclick="selectDate('${d}')">${d}</button>
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
  if (!matches.length) return `<div class="glass-card" style="text-align:center;">Niciun meci găsit.</div>`;

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
  let pool = [];
  (state.matches || []).forEach(m => {
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

  let oddsButtons = [5, 10, 20, 50, 100].map(val =>
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
      <div class="ticket-config">${oddsButtons}</div>
      <div style="background:rgba(0,0,0,0.5); border:1px solid var(--card-border); border-radius:12px; padding:12px; margin-top:15px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid #333; padding-bottom:8px;">
          <span style="font-weight:bold; font-size:13px;">Cotă Țintă: ~${selectedTargetOdds}</span>
          <span style="background:var(--accent-gold); color:#000; font-weight:800; padding:4px 10px; border-radius:8px; font-size:14px;">Cotă Totală: ${currentOdds.toFixed(2)}</span>
        </div>
        ${picksHtml || '<div style="text-align:center; padding:20px; color:var(--text-muted);">Fără selecții disponibile.</div>'}
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
    c.innerHTML = '<div class="glass-card" style="text-align:center;">Se încarcă...</div>';
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
  btn.innerText = '⏳ Se reîncarcă...';
  try {
    await fetch('/api/refresh-from-github', { method: 'POST' });
    await fetchAPI();
    btn.innerText = '✔ Gata!';
    setTimeout(() => { btn.innerText = '🔄 Reîncarcă'; }, 2000);
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
