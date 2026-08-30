cat > /mnt/user-data/outputs/predictie_csv/app.py << 'PYEOF'
import os
import json
import math
import csv
import io
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

CACHE_FILE = "matches_cache.json"
STATS_CACHE_FILE = "team_stats_cache.json"
MAX_ROWS = 300  # plafon de siguranta pt. un CSV neobisnuit de mare

# Praguri de incredere - aceleasi folosite in tot proiectul, pt. consistenta
CONFIDENCE_THRESHOLD = 0.65
LOW_RISK_THRESHOLD = 0.75
FALLBACK_MIN_CONFIDENCE = 0.55

CHALLENGE_TARGET_ODD = 1.5
TICKET_TARGET_ODDS = [2.0, 3.0, 5.0]
MIN_PICK_CONFIDENCE_FOR_TICKET = 0.55

TOP_LEAGUES = {"E0", "SP1", "I1", "D1", "F1"}  # "top 5" ligi europene
CORNERS_LINES = [8.5, 9.5, 10.5]
CARDS_LINES = [3.5, 4.5]
MIN_STATS_SAMPLE = 3

TICKET_DISCLAIMER = ("Cota afisata e cota corecta a modelului (1/probabilitate calculata), nu o cota "
                      "reala oferita de o casa de pariuri. Combinarea mai multor meciuri într-un bilet "
                      "scade probabilitatea totala de succes.")

BOOKMAKER_1X2_PRIORITY = [
    ("B365H", "B365D", "B365A", "Bet365"),
    ("PSH", "PSD", "PSA", "Pinnacle"),
    ("WHH", "WHD", "WHA", "William Hill"),
    ("VCH", "VCD", "VCA", "BetVictor"),
    ("AvgH", "AvgD", "AvgA", "Medie case"),
    ("BWH", "BWD", "BWA", "Bwin"),
    ("IWH", "IWD", "IWA", "Interwetten"),
]
OU25_PRIORITY = [("B365>2.5", "B365<2.5"), ("Avg>2.5", "Avg<2.5"), ("BbAv>2.5", "BbAv<2.5")]

LEAGUE_NAMES = {
    "E0": "Premier League (Anglia)", "E1": "Championship (Anglia)",
    "E2": "League One (Anglia)", "E3": "League Two (Anglia)", "EC": "National League (Anglia)",
    "SC0": "Premiership (Scotia)", "SC1": "Championship (Scotia)",
    "SP1": "La Liga (Spania)", "SP2": "La Liga 2 (Spania)",
    "D1": "Bundesliga (Germania)", "D2": "Bundesliga 2 (Germania)",
    "I1": "Serie A (Italia)", "I2": "Serie B (Italia)",
    "F1": "Ligue 1 (Franta)", "F2": "Ligue 2 (Franta)",
    "N1": "Eredivisie (Olanda)", "B1": "Jupiler Pro League (Belgia)",
    "P1": "Primeira Liga (Portugalia)", "T1": "Super Lig (Turcia)", "G1": "Super League (Grecia)",
}

BETBUILDER_COMBOS = [
    ("1 & Peste 1.5 goluri", lambda h, a: h > a and (h + a) > 1.5),
    ("1 & GG Da", lambda h, a: h > a and h > 0 and a > 0),
    ("2 & Peste 1.5 goluri", lambda h, a: h < a and (h + a) > 1.5),
    ("2 & GG Da", lambda h, a: h < a and h > 0 and a > 0),
    ("X & Sub 2.5 goluri", lambda h, a: h == a and (h + a) < 2.5),
    ("GG Da & Peste 2.5 goluri", lambda h, a: h > 0 and a > 0 and (h + a) > 2.5),
    ("Sansa Dubla 1X & Sub 3.5 goluri", lambda h, a: h >= a and (h + a) < 3.5),
    ("Sansa Dubla X2 & Sub 3.5 goluri", lambda h, a: h <= a and (h + a) < 3.5),
]


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[EROARE] Nu am putut scrie {path}: {e}")


def league_display_name(code):
    return LEAGUE_NAMES.get(code, code or "?")


def parse_uk_date(date_str):
    date_str = (date_str or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def extract_1x2_odds(row):
    for h_key, d_key, a_key, label in BOOKMAKER_1X2_PRIORITY:
        try:
            oh, od, oa = float(row.get(h_key) or 0), float(row.get(d_key) or 0), float(row.get(a_key) or 0)
            if oh > 1 and od > 1 and oa > 1:
                return oh, od, oa, label
        except (ValueError, TypeError):
            continue
    return None


def extract_ou25_odds(row):
    for over_key, under_key in OU25_PRIORITY:
        try:
            o_over, o_under = float(row.get(over_key) or 0), float(row.get(under_key) or 0)
            if o_over > 1 and o_under > 1:
                return o_over, o_under
        except (ValueError, TypeError):
            continue
    return None


def implied_probs(oh, od, oa):
    raw_h, raw_d, raw_a = 1 / oh, 1 / od, 1 / oa
    total = raw_h + raw_d + raw_a
    return raw_h / total, raw_d / total, raw_a / total


# ────────────────────────────── MODEL POISSON CALIBRAT ──────────────────────────────

def poisson_pmf(k, lam):
    lam = max(lam, 0.02)
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _match_probs_from_lambdas(lam_h, lam_a, max_g):
    ph_list = [poisson_pmf(h, lam_h) for h in range(max_g)]
    pa_list = [poisson_pmf(a, lam_a) for a in range(max_g)]
    p_h = p_d = p_a = 0.0
    for h in range(max_g):
        for a in range(max_g):
            p = ph_list[h] * pa_list[a]
            if h > a:
                p_h += p
            elif h == a:
                p_d += p
            else:
                p_a += p
    return p_h, p_d, p_a


def _frange(start, stop, step):
    vals, v = [], start
    while v <= stop + 1e-9:
        vals.append(round(v, 4))
        v += step
    return vals


def calibrate_lambdas(target_h, target_d, target_a):
    best, best_err = None, None
    for lh in _frange(0.2, 3.8, 0.2):
        for la in _frange(0.2, 3.0, 0.2):
            ph, pd, pa = _match_probs_from_lambdas(lh, la, max_g=6)
            err = (ph - target_h) ** 2 + (pd - target_d) ** 2 + (pa - target_a) ** 2
            if best_err is None or err < best_err:
                best_err, best = err, (lh, la)

    lh0, la0 = best
    for lh in _frange(max(0.05, lh0 - 0.15), lh0 + 0.15, 0.03):
        for la in _frange(max(0.05, la0 - 0.15), la0 + 0.15, 0.03):
            ph, pd, pa = _match_probs_from_lambdas(lh, la, max_g=7)
            err = (ph - target_h) ** 2 + (pd - target_d) ** 2 + (pa - target_a) ** 2
            if err < best_err:
                best_err, best = err, (lh, la)
    return best


def predict_from_odds(row):
    odds_1x2 = extract_1x2_odds(row)
    if not odds_1x2:
        return None
    oh, od, oa, bookmaker = odds_1x2
    p_h, p_d, p_a = implied_probs(oh, od, oa)
    lam_h, lam_a = calibrate_lambdas(p_h, p_d, p_a)

    max_g = 7
    ph_list = [poisson_pmf(h, lam_h) for h in range(max_g)]
    pa_list = [poisson_pmf(a, lam_a) for a in range(max_g)]
    p_home = p_draw = p_away = p_btts = 0.0
    p_over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    for h in range(max_g):
        for a in range(max_g):
            p = ph_list[h] * pa_list[a]
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
            tot = h + a
            for line in p_over:
                if tot > line:
                    p_over[line] += p
            if h > 0 and a > 0:
                p_btts += p

    ou = extract_ou25_odds(row)
    if ou:
        o_over, o_under = ou
        raw_over, raw_under = 1 / o_over, 1 / o_under
        s = raw_over + raw_under
        p_over[2.5] = raw_over / s

    markets = {
        "1 (Gazde)": p_home, "X (Egal)": p_draw, "2 (Oaspeti)": p_away,
        "Peste 1.5 goluri": p_over[1.5], "Peste 2.5 goluri": p_over[2.5],
        "Peste 3.5 goluri": p_over[3.5], "Sub 2.5 goluri": 1 - p_over[2.5],
        "GG - Da": p_btts, "GG - Nu": 1 - p_btts,
    }
    fallback = [
        ("Sansa Dubla 1X", p_home + p_draw), ("Sansa Dubla X2", p_draw + p_away),
        ("Sansa Dubla 12", p_home + p_away),
        ("Peste 1.5 goluri", p_over[1.5]), ("Sub 3.5 goluri", 1 - p_over[3.5]),
    ]

    best_market, best_p = max(markets.items(), key=lambda kv: kv[1])
    result = {
        "principal": best_market, "principal_pct": round(best_p * 100, 1),
        "alternativ": None, "alternativ_pct": None,
        "exp_goals_home": round(lam_h, 2), "exp_goals_away": round(lam_a, 2),
        "bookmaker": bookmaker,
        "pick_for_ticket": None, "pick_pct": None, "fair_odd": None,
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


def compute_betbuilder(lam_h, lam_a, max_g=7, top_n=3, min_pct=0.30):
    ph_list = [poisson_pmf(h, lam_h) for h in range(max_g)]
    pa_list = [poisson_pmf(a, lam_a) for a in range(max_g)]
    scored = []
    for label, cond in BETBUILDER_COMBOS:
        p = sum(ph_list[h] * pa_list[a] for h in range(max_g) for a in range(max_g) if cond(h, a))
        scored.append((label, p))
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return [{"combo": lbl, "pct": round(p * 100, 1)} for lbl, p in scored[:top_n] if p >= min_pct]


def process_stats_csv(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    team_stats = {}
    for row in reader:
        home = (row.get("HomeTeam") or "").strip()
        away = (row.get("AwayTeam") or "").strip()
        if not home or not away:
            continue
        try:
            hc, ac = float(row.get("HC") or 0), float(row.get("AC") or 0)
            hy, ay = float(row.get("HY") or 0), float(row.get("AY") or 0)
            hr, ar = float(row.get("HR") or 0), float(row.get("AR") or 0)
        except (ValueError, TypeError):
            continue

        team_stats.setdefault(home, {"corners_for": [], "corners_against": [], "cards": []})
        team_stats.setdefault(away, {"corners_for": [], "corners_against": [], "cards": []})
        team_stats[home]["corners_for"].append(hc)
        team_stats[home]["corners_against"].append(ac)
        team_stats[home]["cards"].append(hy + hr)
        team_stats[away]["corners_for"].append(ac)
        team_stats[away]["corners_against"].append(hc)
        team_stats[away]["cards"].append(ay + ar)
    return team_stats


def estimate_corners_cards(home_team, away_team, team_stats):
    h, a = team_stats.get(home_team), team_stats.get(away_team)
    if not h or not a:
        return None
    if len(h["corners_for"]) < MIN_STATS_SAMPLE or len(a["corners_for"]) < MIN_STATS_SAMPLE:
        return None

    def avg(lst):
        return sum(lst) / len(lst)

    exp_corners = (avg(h["corners_for"]) + avg(a["corners_against"])) / 2 + \
                  (avg(a["corners_for"]) + avg(h["corners_against"])) / 2
    exp_cards = avg(h["cards"]) + avg(a["cards"])

    def over_prob(exp_val, line, max_k=25):
        return sum(poisson_pmf(k, exp_val) for k in range(math.ceil(line), max_k))

    return {
        "exp_corners": round(exp_corners, 1), "exp_cards": round(exp_cards, 1),
        "corners_over": {str(l): round(over_prob(exp_corners, l) * 100, 1) for l in CORNERS_LINES},
        "cards_over": {str(l): round(over_prob(exp_cards, l) * 100, 1) for l in CARDS_LINES},
        "sample": min(len(h["corners_for"]), len(a["corners_for"])),
    }


def build_ticket_for_target(candidates, target):
    selection, cum_odd, cum_prob = [], 1.0, 1.0
    for m in candidates:
        if cum_odd >= target:
            break
        selection.append(m)
        cum_odd *= m["fair_odd"]
        cum_prob *= m["pick_pct"] / 100
    if not selection:
        return None
    return {
        "target_odd": target,
        "combined_odd": round(cum_odd, 2),
        "combined_probability_pct": round(cum_prob * 100, 1),
        "selections": [
            {"league": s["league"], "home": s["home"], "away": s["away"],
             "pick": s["pick_for_ticket"], "pct": s["pick_pct"]}
            for s in selection
        ],
    }


def build_tickets_and_challenge(matches):
    candidates = [m for m in matches if m.get("pick_pct") is not None
                  and m["pick_pct"] / 100 >= MIN_PICK_CONFIDENCE_FOR_TICKET]
    candidates.sort(key=lambda m: m["pick_pct"], reverse=True)

    challenge = build_ticket_for_target(candidates, CHALLENGE_TARGET_ODD)

    tickets = []
    for target in TICKET_TARGET_ODDS:
        t = build_ticket_for_target(candidates, target)
        if t and len(t["selections"]) >= 2:
            tickets.append(t)
    return challenge, tickets


def process_csv_content(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    processed, skipped_no_odds = [], 0
    existing_team_stats = _load_json(STATS_CACHE_FILE, None)

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
        betbuilder = []
        if league_code in TOP_LEAGUES and not pred.get("fara_pronostic"):
            betbuilder = compute_betbuilder(pred["exp_goals_home"], pred["exp_goals_away"])

        corners_cards = None
        if existing_team_stats:
            corners_cards = estimate_corners_cards(home, away, existing_team_stats)

        processed.append({
            "league": league_display_name(league_code), "league_code": league_code,
            "date": parse_uk_date(row.get("Date")), "time": (row.get("Time") or "").strip(),
            "home": home, "away": away,
            "betbuilder": betbuilder, "corners_cards": corners_cards,
            **pred,
        })

    processed.sort(key=lambda m: -(m.get("pick_pct") or 0))
    processed.sort(key=lambda m: m["date"])

    challenge, tickets = build_tickets_and_challenge([m for m in processed if not m.get("fara_pronostic")])
    return processed, tickets, challenge, skipped_no_odds


# ────────────────────────────── ROUTE-URI ──────────────────────────────

@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Niciun fisier incarcat!"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Fisier neselectat!"}), 400

    try:
        content = file.read().decode('utf-8', errors='ignore')
        processed_matches, tickets, challenge, skipped = process_csv_content(content)
        cache_data = {
            "uploaded_at": datetime.now().isoformat(),
            "matches": processed_matches,
            "tickets": tickets,
            "challenge": challenge,
            "skipped_no_odds": skipped,
            "stats_uploaded": os.path.exists(STATS_CACHE_FILE),
            "api_active": True,
        }
        _save_json(CACHE_FILE, cache_data)
        return jsonify({
            "status": "success", "count": len(processed_matches), "skipped": skipped,
            "tickets": len(tickets), "challenge": bool(challenge),
            "betbuilder_matches": sum(1 for m in processed_matches if m.get("betbuilder")),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/upload-stats-csv', methods=['POST'])
def upload_stats_csv():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Niciun fisier incarcat!"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Fisier neselectat!"}), 400

    try:
        content = file.read().decode('utf-8', errors='ignore')
        team_stats = process_stats_csv(content)
        _save_json(STATS_CACHE_FILE, team_stats)

        cache = _load_json(CACHE_FILE, None)
        matched = 0
        if cache and cache.get("matches"):
            for m in cache["matches"]:
                cc = estimate_corners_cards(m["home"], m["away"], team_stats)
                m["corners_cards"] = cc
                if cc:
                    matched += 1
            cache["stats_uploaded"] = True
            _save_json(CACHE_FILE, cache)

        return jsonify({"status": "success", "teams_recunoscute": len(team_stats), "meciuri_actualizate": matched})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    data = _load_json(CACHE_FILE, None)
    if not data:
        return jsonify({"matches": [], "tickets": [], "challenge": None, "stats_uploaded": False, "api_active": False})
    return jsonify(data)


# ────────────────────────────── INTERFAȚĂ FUTURISTĂ ──────────────────────────────

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XMTS AI · Predictive Engine</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-dark: #040711;
    --card-bg: rgba(15, 23, 42, 0.75);
    --card-border: rgba(255, 255, 255, 0.08);
    --accent-cyan: #06b6d4;
    --accent-blue: #3b82f6;
    --accent-purple: #8b5cf6;
    --accent-gold: #f59e0b;
    --accent-green: #10b981;
    --text-main: #f8fafc;
    --text-muted: #94a3b8;
    --glow-cyan: rgba(6, 182, 212, 0.25);
    --glow-gold: rgba(245, 158, 11, 0.25);
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  
  body {
    background-color: var(--bg-dark);
    background-image: 
      radial-gradient(circle at 15% 15%, rgba(59, 130, 246, 0.12) 0%, transparent 40%),
      radial-gradient(circle at 85% 85%, rgba(139, 92, 246, 0.12) 0%, transparent 40%),
      radial-gradient(circle at 50% 50%, rgba(6, 182, 212, 0.05) 0%, transparent 60%);
    background-attachment: fixed;
    color: var(--text-main);
    font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
    padding: 20px 12px;
    -webkit-font-smoothing: antialiased;
    min-height: 100vh;
  }

  .container { max-width: 560px; margin: 0 auto; }

  /* Top Navigation & Status */
  .header-box {
    text-align: center;
    margin-bottom: 24px;
    position: relative;
  }

  .brand-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(6, 182, 212, 0.1);
    border: 1px solid rgba(6, 182, 212, 0.3);
    padding: 4px 12px;
    border-radius: 99px;
    font-size: 11px;
    font-weight: 700;
    color: var(--accent-cyan);
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .pulse-dot {
    width: 6px; height: 6px;
    background-color: var(--accent-cyan);
    border-radius: 50%;
    box-shadow: 0 0 8px var(--accent-cyan);
    animation: pulse 1.8s infinite;
  }
  @keyframes pulse { 0%{ opacity: 0.3; } 50%{ opacity: 1; } 100%{ opacity: 0.3; } }

  .title-main {
    font-size: 26px;
    font-weight: 800;
    background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 50%, var(--accent-cyan) 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    letter-spacing: -0.5px;
  }
  .subtitle { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

  /* Modern Glass Cards */
  .glass-card {
    background: var(--card-bg);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid var(--card-border);
    border-radius: 20px;
    padding: 18px;
    margin-bottom: 14px;
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    transition: transform 0.2s ease, border-color 0.2s ease;
  }
  .glass-card:hover {
    border-color: rgba(255, 255, 255, 0.18);
  }

  /* Upload Zone */
  .upload-card {
    border: 1px dashed rgba(6, 182, 212, 0.4);
    background: rgba(6, 182, 212, 0.03);
    text-align: center;
  }
  .file-input { display: none; }
  .btn-upload {
    background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
    color: #fff;
    border: none;
    padding: 11px 22px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    box-shadow: 0 4px 14px var(--glow-cyan);
    transition: all 0.2s ease;
    display: inline-block;
  }
  .btn-upload:hover { transform: translateY(-1px); box-shadow: 0 6px 20px var(--glow-cyan); }
  .status-text { font-size: 12px; color: var(--text-muted); margin-top: 10px; line-height: 1.4; }

  /* Custom Futurist Navigation Tabs */
  .tabs-wrapper {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 12px;
    margin-bottom: 16px;
    scrollbar-width: none;
  }
  .tabs-wrapper::-webkit-scrollbar { display: none; }
  
  .tab-btn {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid var(--card-border);
    color: var(--text-muted);
    padding: 9px 16px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.2s ease;
  }
  .tab-btn.active {
    background: linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(59, 130, 246, 0.2));
    border-color: var(--accent-cyan);
    color: #fff;
    box-shadow: 0 0 15px var(--glow-cyan);
  }

  /* Challenge Specific Card */
  .challenge-card {
    border: 1px solid var(--accent-gold);
    background: radial-gradient(circle at top right, rgba(245, 158, 11, 0.15), var(--card-bg));
    box-shadow: 0 0 25px var(--glow-gold);
    position: relative;
    overflow: hidden;
  }
  .challenge-badge {
    position: absolute;
    top: 0; right: 0;
    background: linear-gradient(135deg, var(--accent-gold), #d97706);
    color: #000;
    font-weight: 800;
    font-size: 10px;
    padding: 4px 12px;
    border-bottom-left-radius: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  /* Cards Inner Layout */
  .card-header-line {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: var(--text-muted);
    margin-bottom: 8px;
    font-weight: 500;
  }
  .match-title {
    font-size: 16px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 12px;
  }
  
  .pred-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 12px;
    padding: 10px 12px;
    margin-bottom: 8px;
  }
  .pred-target { font-size: 13px; font-weight: 700; color: var(--accent-cyan); }
  .risk-tag {
    font-size: 10px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 6px;
    text-transform: uppercase;
  }
  .risk-Scazut { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
  .risk-Mediu { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
  .risk-Ridicat { background: rgba(239, 68, 68, 0.2); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.3); }

  .goals-estimate {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 6px;
    display: flex;
    gap: 12px;
  }

  /* Ticket Structure */
  .ticket-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--card-border);
  }
  .ticket-odd-display {
    font-size: 22px;
    font-weight: 800;
    color: var(--accent-gold);
    text-shadow: 0 0 10px var(--glow-gold);
  }
  .ticket-selection-item {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    padding: 8px 0;
    border-bottom: 1px dashed rgba(255, 255, 255, 0.05);
  }

  .disclaimer-box {
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid var(--card-border);
    border-radius: 14px;
    padding: 12px 14px;
    font-size: 11px;
    color: var(--text-muted);
    line-height: 1.5;
    margin-bottom: 16px;
  }

  .empty-state {
    text-align: center;
    padding: 36px 16px;
    color: var(--text-muted);
    font-size: 13px;
  }

  .footer-text {
    font-size: 10px;
    color: var(--text-muted);
    text-align: center;
    margin-top: 24px;
    opacity: 0.7;
    line-height: 1.4;
  }
</style>
</head>
<body>

<div class="container">

  <!-- Header Section -->
  <div class="header-box">
    <div class="brand-badge"><span class="pulse-dot"></span> XMTS ENGINE V2</div>
    <div class="title-main">Predictive Analytics</div>
    <div class="subtitle">Model statistic Poisson calibrat pe piața cotațiilor</div>
  </div>

  <!-- Upload Form -->
  <div class="glass-card upload-card">
    <div style="font-size: 13px; font-weight: 700; margin-bottom: 10px; color: #fff;">
      ⚡ Încarcă Fișier Fixtures (.CSV)
    </div>
    <label for="csvFileInput" class="btn-upload">Selectează CSV</label>
    <input type="file" id="csvFileInput" class="file-input" accept=".csv" onchange="uploadCSV()">
    <div class="status-text" id="upload-status">Așteaptă un fișier de pe football-data.co.uk</div>
  </div>

  <!-- Navigation Tabs -->
  <div class="tabs-wrapper">
    <button class="tab-btn active" onclick="switchTab('challenge', this)">🎯 Challenge 1.50</button>
    <button class="tab-btn" onclick="switchTab('sigure', this)">🔥 Selecții Sigure</button>
    <button class="tab-btn" onclick="switchTab('toate', this)">📋 Toate Meciurile</button>
    <button class="tab-btn" onclick="switchTab('betbuilder', this)">🧩 BetBuilder</button>
    <button class="tab-btn" onclick="switchTab('cartonase', this)">🟨 Cartonașe & Cornere</button>
    <button class="tab-btn" onclick="switchTab('bilete', this)">🎟 Bilete Cota 2.0+</button>
  </div>

  <!-- Dynamic Content Container -->
  <div id="tab-content">
    <div class="glass-card empty-state">Încarcă fișierul fixtures.csv pentru a rula modelul.</div>
  </div>

  <div class="footer-text">
    Informații cu caracter statistic. Nu constituie îndemn la pariere. Joacă responsabil.
  </div>

</div>

<script>
let cachedData = { matches: [], tickets: [], challenge: null, stats_uploaded: false };
let currentTab = 'challenge';

function matchCard(m) {
  const alt = m.alternativ ? `<div style="font-size: 11px; color: var(--text-muted);">Alternativ: <b>${m.alternativ}</b> (${m.alternativ_pct}%)</div>` : '';
  const noPick = m.fara_pronostic ? '<div style="font-size: 11px; color: var(--text-muted);">Meci echilibrat fără selecție clară</div>' : '';
  
  return `
    <div class="glass-card">
      <div class="card-header-line">
        <span>${m.league} · ${m.date} ${m.time ? '· ' + m.time : ''}</span>
        <span>${m.bookmaker || ''}</span>
      </div>
      <div class="match-title">${m.home} vs ${m.away}</div>
      <div class="pred-row">
        <span class="pred-target">${m.principal} (${m.principal_pct}%)</span>
        <span class="risk-tag risk-${m.risc}">${m.risc}</span>
      </div>
      ${alt}${noPick}
      <div class="goals-estimate">
        <span>xG Gazde: <b>${m.exp_goals_home}</b></span>
        <span>xG Oaspeți: <b>${m.exp_goals_away}</b></span>
      </div>
    </div>`;
}

function ticketBlock(t, isChallenge) {
  const legs = t.selections.map(s => `
    <div class="ticket-selection-item">
      <span><b>${s.home} vs ${s.away}</b><br><span style="color:var(--accent-cyan);">${s.pick}</span></span>
      <span style="font-weight:700;">${s.pct}%</span>
    </div>`).join('');
    
  return `
    <div class="glass-card ${isChallenge ? 'challenge-card' : ''}">
      ${isChallenge ? '<div class="challenge-badge">🎯 CHALLENGE COTA 1.50</div>' : ''}
      <div class="ticket-header">
        <div>
          <div style="font-size:11px; color:var(--text-muted);">TINTĂ COTA</div>
          <div style="font-size:13px; font-weight:700;">${t.target_odd}</div>
        </div>
        <div class="ticket-odd-display">@ ${t.combined_odd}</div>
      </div>
      ${legs}
      <div style="font-size:11px; color:var(--text-muted); margin-top:12px; font-weight:600;">
        Probabilitate teoretică cumulată: ${t.combined_probability_pct}%
      </div>
    </div>`;
}

function betbuilderCard(m) {
  const combos = m.betbuilder.map(b => `
    <div class="ticket-selection-item">
      <span>${b.combo}</span>
      <span style="font-weight:700; color:var(--accent-cyan);">${b.pct}%</span>
    </div>`).join('');
  return `
    <div class="glass-card">
      <div class="card-header-line"><span>${m.league} · ${m.date}</span></div>
      <div class="match-title">${m.home} vs ${m.away}</div>
      ${combos}
    </div>`;
}

function cornersCardsCard(m) {
  const cc = m.corners_cards;
  const corners = Object.entries(cc.corners_over).map(([line,pct]) => `
    <div class="ticket-selection-item"><span>Peste ${line} cornere</span><span style="font-weight:700;">${pct}%</span></div>`).join('');
  const cards = Object.entries(cc.cards_over).map(([line,pct]) => `
    <div class="ticket-selection-item"><span>Peste ${line} cartonașe</span><span style="font-weight:700;">${pct}%</span></div>`).join('');
  return `
    <div class="glass-card">
      <div class="card-header-line"><span>${m.league} · ${m.date}</span><span>Eșantion: ${cc.sample} meciuri</span></div>
      <div class="match-title">${m.home} vs ${m.away}</div>
      <div class="goals-estimate" style="margin-bottom:10px;">
        <span>Estimat Cornere: <b>${cc.exp_corners}</b></span>
        <span>Estimat Cartonașe: <b>${cc.exp_cards}</b></span>
      </div>
      ${corners}${cards}
    </div>`;
}

function render() {
  const content = document.getElementById('tab-content');
  const matches = cachedData.matches || [];

  if (matches.length === 0) {
    content.innerHTML = '<div class="glass-card empty-state">Nu există date încărcate. Adaugă un fișier CSV mai sus.</div>';
    return;
  }

  if (currentTab === 'challenge') {
    content.innerHTML = cachedData.challenge
      ? ticketBlock(cachedData.challenge, true) + `<div class="disclaimer-box">${TICKET_DISCLAIMER}</div>`
      : '<div class="glass-card empty-state">Nu sunt suficiente meciuri cu coeficient ridicat pentru un Challenge de cota 1.50 în acest fișier.</div>';
  } else if (currentTab === 'sigure') {
    const top = matches.filter(m => !m.fara_pronostic).slice(0, 10);
    content.innerHTML = top.length ? top.map(matchCard).join('') : '<div class="glass-card empty-state">Fără selecții peste pragul de încredere.</div>';
  } else if (currentTab === 'toate') {
    content.innerHTML = matches.map(matchCard).join('');
  } else if (currentTab === 'betbuilder') {
    const withCombos = matches.filter(m => m.betbuilder && m.betbuilder.length > 0);
    content.innerHTML = withCombos.length ? withCombos.map(betbuilderCard).join('')
      : '<div class="glass-card empty-state">Nu există combinații valide pentru ligile principale în fișier.</div>';
  } else if (currentTab === 'cartonase') {
    if (!cachedData.stats_uploaded) {
      content.innerHTML = `
        <div class="glass-card upload-card">
          <div style="font-size: 13px; font-weight: 700; margin-bottom: 8px; color: #fff;">📊 Încarcă fișierul cu Istoric (ex: E0.csv)</div>
          <div class="status-text" style="margin-bottom: 12px;">Fișierele normale de fixtures nu conțin datele de cornere/cartonașe. Descarcă fișierul complet al ligii pentru aceste calcule.</div>
          <label for="statsFileInput" class="btn-upload">Încarcă CSV Istoric</label>
          <input type="file" id="statsFileInput" class="file-input" accept=".csv" onchange="uploadStatsCSV()">
          <div class="status-text" id="stats-upload-status"></div>
        </div>`;
    } else {
      const withCC = matches.filter(m => m.corners_cards);
      content.innerHTML = withCC.length ? withCC.map(cornersCardsCard).join('')
        : '<div class="glass-card empty-state">Echipele din fișier nu au putut fi potrivite în istoricul încărcat.</div>';
    }
  } else {
    const tickets = cachedData.tickets || [];
    content.innerHTML = tickets.length
      ? `<div class="disclaimer-box">${TICKET_DISCLAIMER}</div>` + tickets.map(t => ticketBlock(t, false)).join('')
      : '<div class="glass-card empty-state">Nu există destule selecții valide pentru bilete combinate.</div>';
  }
}

const TICKET_DISCLAIMER = "Cota este calculată direct pe baza distribuției de probabilitate teoretică. Combinarea mai multor evenimente scade rata totală de succes a biletului.";

function switchTab(tab, btn) {
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  render();
}

async function init() {
  try {
    const res = await fetch('/api/predictions');
    cachedData = await res.json();
    render();
  } catch(err) {
    document.getElementById('tab-content').innerHTML = '<div class="glass-card empty-state">Eroare de conexiune cu serverul.</div>';
  }
}

async function uploadCSV() {
  const fileInput = document.getElementById('csvFileInput');
  if(fileInput.files.length === 0) return;
  const status = document.getElementById('upload-status');
  status.textContent = 'Procesare în curs...';
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  try {
    const res = await fetch('/api/upload-csv', { method: 'POST', body: formData });
    const data = await res.json();
    if(data.status === 'success') {
      status.textContent = `Procesat: ${data.count} meciuri validated.`;
      init();
    } else {
      status.textContent = 'Eroare: ' + data.message;
    }
  } catch(e) {
    status.textContent = 'Eroare la încărcare.';
  }
}

async function uploadStatsCSV() {
  const fileInput = document.getElementById('statsFileInput');
  if(!fileInput || fileInput.files.length === 0) return;
  const status = document.getElementById('stats-upload-status');
  status.textContent = 'Procesare istoric...';
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  try {
    const res = await fetch('/api/upload-stats-csv', { method: 'POST', body: formData });
    const data = await res.json();
    if(data.status === 'success') {
      status.textContent = `Preluat: ${data.teams_recunoscute} echipe.`;
      init();
    } else {
      status.textContent = 'Eroare: ' + data.message;
    }
  } catch(e) {
    status.textContent = 'Eroare la încărcare.';
  }
}

init();
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
PYEOF
echo "Fișier actualizat cu succes!"
