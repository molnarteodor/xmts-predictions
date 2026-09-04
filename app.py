import os
import json
import math
import csv
import io
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bucharest")
except Exception:
    TZ = None  # fallback la ora serverului daca zoneinfo/tzdata lipsesc


def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d") if TZ else datetime.now().strftime("%Y-%m-%d")


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
MIN_PICK_CONFIDENCE_FOR_TICKET = 0.55

TOP_LEAGUES = {"E0", "SP1", "I1", "D1", "F1"}  # "top 5" ligi europene
CORNERS_LINES = [8.5, 9.5, 10.5]
CARDS_LINES = [3.5, 4.5]
MIN_STATS_SAMPLE = 3

TICKET_DISCLAIMER = ("Cota afisata e cota corecta a modelului (1/probabilitate calculata), nu o cota "
                      "reala oferita de o casa de pariuri. Combinarea mai multor meciuri intr-un bilet "
                      "scade probabilitatea totala de succes.")

PINNACLE_1X2 = ("PSH", "PSD", "PSA")
BOOKMAKER_1X2_COLUMNS = [
    ("B365H", "B365D", "B365A", "Bet365"),
    ("BWH", "BWD", "BWA", "Bwin"),
    ("IWH", "IWD", "IWA", "Interwetten"),
    ("WHH", "WHD", "WHA", "William Hill"),
    ("VCH", "VCD", "VCA", "BetVictor"),
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


def _valid_odds_triplet(row, h_key, d_key, a_key):
    try:
        oh, od, oa = float(row.get(h_key) or 0), float(row.get(d_key) or 0), float(row.get(a_key) or 0)
        if oh > 1 and od > 1 and oa > 1:
            return oh, od, oa
    except (ValueError, TypeError):
        pass
    return None


def extract_1x2_odds(row):
    """
    Returneaza probabilitatile 1X2 deja curatate de marja casei (nu cotele brute).
    Prioritate: Pinnacle - recunoscuta in literatura de specialitate ca avand cele mai
    mici marje, un bun proxy pt. "pretul eficient" al pietei. Daca nu e disponibila,
    facem consens: eliminam marja fiecarei case gasite separat, apoi mediem
    probabilitatile rezultate - o medie a mai multor case reduce zgomotul unei singure
    surse ("wisdom of the crowd"). Ultima varianta: coloana "Avg" deja calculata de sursa.
    """
    pinnacle = _valid_odds_triplet(row, *PINNACLE_1X2)
    if pinnacle:
        ph, pd, pa = implied_probs(*pinnacle)
        return ph, pd, pa, "Pinnacle"

    probs = []
    for h_key, d_key, a_key, _label in BOOKMAKER_1X2_COLUMNS:
        triplet = _valid_odds_triplet(row, h_key, d_key, a_key)
        if triplet:
            probs.append(implied_probs(*triplet))

    if probs:
        n = len(probs)
        ph = sum(p[0] for p in probs) / n
        pd = sum(p[1] for p in probs) / n
        pa = sum(p[2] for p in probs) / n
        return ph, pd, pa, (f"Medie {n} case" if n > 1 else "1 casa")

    avg = _valid_odds_triplet(row, "AvgH", "AvgD", "AvgA")
    if avg:
        ph, pd, pa = implied_probs(*avg)
        return ph, pd, pa, "Medie case (sursa)"

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


def poisson_pmf(k, lam):
    lam = max(lam, 0.02)
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


# Corectie Dixon-Coles (Dixon & Coles, 1997, "Modelling Association Football Scores and
# Inefficiencies in the Football Betting Market"): modelul Poisson independent subestimeaza
# usor frecventa scorurilor mici corelate (0-0, 1-1) si o supraestimeaza usor pe cea a
# scorurilor 1-0/0-1. rho e de obicei un parametru estimat din date istorice de liga; noi nu
# avem volumul necesar pt. o estimare proprie, asa ca folosim o valoare fixa, moderata,
# reprezentativa pt. fotbalul profesionist (aprox. -0.08 in majoritatea studiilor publicate).
DIXON_COLES_RHO = -0.08


def dixon_coles_tau(x, y, lam, mu, rho):
    if x == 0 and y == 0:
        return 1 - (lam * mu * rho)
    elif x == 0 and y == 1:
        return 1 + (lam * rho)
    elif x == 1 and y == 0:
        return 1 + (mu * rho)
    elif x == 1 and y == 1:
        return 1 - rho
    return 1.0


def _match_probs_from_lambdas(lam_h, lam_a, max_g, rho=0.0):
    ph_list = [poisson_pmf(h, lam_h) for h in range(max_g)]
    pa_list = [poisson_pmf(a, lam_a) for a in range(max_g)]
    p_h = p_d = p_a = 0.0
    for h in range(max_g):
        for a in range(max_g):
            p = ph_list[h] * pa_list[a] * dixon_coles_tau(h, a, lam_h, lam_a, rho)
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
    # Plaja lărgită fata de versiunea initiala, ca sa acopere si favoritii foarte clari
    # (cote de tip 1.05-1.15), unde lambda gazdelor poate depasi usor 4.
    # max_g=9/10 (nu 6/7 ca initial) - la lambda mare, un plafon prea mic trunchiaza
    # semnificativ din masa de probabilitate si distorsioneaza cautarea (verificat: la
    # lambda=4.4, max_g=6 acopera doar 72% din probabilitate, in timp ce max_g=12 acopera 99.8%).
    best, best_err = None, None
    for lh in _frange(0.15, 4.4, 0.2):
        for la in _frange(0.15, 3.4, 0.2):
            ph, pd, pa = _match_probs_from_lambdas(lh, la, max_g=10, rho=DIXON_COLES_RHO)
            err = (ph - target_h) ** 2 + (pd - target_d) ** 2 + (pa - target_a) ** 2
            if best_err is None or err < best_err:
                best_err, best = err, (lh, la)

    lh0, la0 = best
    for lh in _frange(max(0.05, lh0 - 0.15), lh0 + 0.15, 0.03):
        for la in _frange(max(0.05, la0 - 0.15), la0 + 0.15, 0.03):
            ph, pd, pa = _match_probs_from_lambdas(lh, la, max_g=12, rho=DIXON_COLES_RHO)
            err = (ph - target_h) ** 2 + (pd - target_d) ** 2 + (pa - target_a) ** 2
            if err < best_err:
                best_err, best = err, (lh, la)
    return best


TARGET_ODD_MIN = 1.30
TARGET_ODD_MAX = 1.40


def pick_market_near_target(candidates, target_min=TARGET_ODD_MIN, target_max=TARGET_ODD_MAX):
    """
    Alege, dintre toate piata calculate la un meci, cea a carei cota corecta (1/probabilitate)
    e cea mai apropiata de intervalul tinta - NU neaparat cea mai probabila piata (asta e rolul
    lui 'principal'). Daca nicio piata nu cade exact in interval, alege cea mai apropiata si
    marcheaza clar asta (in_range: false), in loc sa ascunda meciul sau sa forteze un numar
    care nu exista in date.
    """
    scored = [(label, p, 1 / p) for label, p in candidates.items() if p > 0]
    in_range = [c for c in scored if target_min <= c[2] <= target_max]
    if in_range:
        label, p, odd = max(in_range, key=lambda c: c[1])  # cea mai sigura dintre cele din interval
        return {"pick": label, "pct": round(p * 100, 1), "odd": round(odd, 2), "in_range": True}
    mid = (target_min + target_max) / 2
    label, p, odd = min(scored, key=lambda c: abs(c[2] - mid))
    return {"pick": label, "pct": round(p * 100, 1), "odd": round(odd, 2), "in_range": False}


def predict_from_odds(row):
    odds_1x2 = extract_1x2_odds(row)
    if not odds_1x2:
        return None
    p_h, p_d, p_a, bookmaker = odds_1x2
    lam_h, lam_a = calibrate_lambdas(p_h, p_d, p_a)

    max_g = 12
    ph_list = [poisson_pmf(h, lam_h) for h in range(max_g)]
    pa_list = [poisson_pmf(a, lam_a) for a in range(max_g)]
    p_home = p_draw = p_away = p_btts = 0.0
    p_over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    for h in range(max_g):
        for a in range(max_g):
            p = ph_list[h] * pa_list[a] * dixon_coles_tau(h, a, lam_h, lam_a, DIXON_COLES_RHO)
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
    # pastram monotonia logica (Peste 1.5 >= Peste 2.5 >= Peste 3.5), chiar si dupa
    # suprascrierea liniei de 2.5 cu o cota reala de piata
    p_over[1.5] = max(p_over[1.5], p_over[2.5])
    p_over[3.5] = min(p_over[3.5], p_over[2.5])

    # "Peste 1.5 goluri" NU e in markets (piata principala) - e adevarata in ~75-85% din
    # meciuri indiferent cine joaca, deci ar castiga aproape mereu argmax-ul, facand
    # pronosticul principal repetitiv si cu cota mica. Ramane disponibila doar ca piata
    # de rezerva (fallback), acolo unde chiar isi are rostul: o varianta mai sigura cand
    # nimic mai specific nu trece pragul de incredere.
    markets = {
        "1 (Gazde)": p_home, "X (Egal)": p_draw, "2 (Oaspeti)": p_away,
        "Peste 2.5 goluri": p_over[2.5], "Peste 3.5 goluri": p_over[3.5],
        "Sub 2.5 goluri": 1 - p_over[2.5],
        "GG - Da": p_btts, "GG - Nu": 1 - p_btts,
    }
    fallback = [
        ("Sansa Dubla 1X", p_home + p_draw), ("Sansa Dubla X2", p_draw + p_away),
        ("Sansa Dubla 12", p_home + p_away),
        ("Peste 1.5 goluri", p_over[1.5]), ("Sub 3.5 goluri", 1 - p_over[3.5]),
    ]

    best_market, best_p = max(markets.items(), key=lambda kv: kv[1])
    all_candidates = dict(markets)
    for label, p in fallback:
        all_candidates.setdefault(label, p)

    result = {
        "principal": best_market, "principal_pct": round(best_p * 100, 1),
        "alternativ": None, "alternativ_pct": None,
        "exp_goals_home": round(lam_h, 2), "exp_goals_away": round(lam_a, 2),
        "bookmaker": bookmaker,
        "pick_for_ticket": None, "pick_pct": None, "fair_odd": None,
        "target_odd_pick": pick_market_near_target(all_candidates),
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


def compute_betbuilder(lam_h, lam_a, max_g=12, top_n=3, min_pct=0.30):
    ph_list = [poisson_pmf(h, lam_h) for h in range(max_g)]
    pa_list = [poisson_pmf(a, lam_a) for a in range(max_g)]
    scored = []
    for label, cond in BETBUILDER_COMBOS:
        p = sum(ph_list[h] * pa_list[a] * dixon_coles_tau(h, a, lam_h, lam_a, DIXON_COLES_RHO)
                for h in range(max_g) for a in range(max_g) if cond(h, a))
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
        "combined_probability_pct": round(cum_prob * 100, 4),
        "selections": [
            {"league": s["league"], "home": s["home"], "away": s["away"],
             "pick": s["pick_for_ticket"], "pct": s["pick_pct"]}
            for s in selection
        ],
    }


def build_challenge(matches):
    """Challenge = piesa fixa la cota ~1.5, folosind doar meciuri cu incredere de siguranta (>=55%)."""
    candidates = [m for m in matches if m.get("pick_pct") is not None
                  and m["pick_pct"] / 100 >= MIN_PICK_CONFIDENCE_FOR_TICKET]
    candidates.sort(key=lambda m: m["pick_pct"], reverse=True)
    return build_ticket_for_target(candidates, CHALLENGE_TARGET_ODD)


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

    challenge = build_challenge([m for m in processed if not m.get("fara_pronostic")])
    return processed, challenge, skipped_no_odds


@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "Niciun fisier incarcat!"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Fisier neselectat!"}), 400

    try:
        content = file.read().decode('utf-8', errors='ignore')
        processed_matches, challenge, skipped = process_csv_content(content)
        cache_data = {
            "uploaded_at": datetime.now().isoformat(),
            "upload_date": today_str(),
            "matches": processed_matches,
            "challenge": challenge,
            "skipped_no_odds": skipped,
            "stats_uploaded": os.path.exists(STATS_CACHE_FILE),
            "api_active": True,
        }
        _save_json(CACHE_FILE, cache_data)
        return jsonify({
            "status": "success", "count": len(processed_matches), "skipped": skipped,
            "challenge": bool(challenge),
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
        return jsonify({"matches": [], "challenge": None, "stats_uploaded": False, "api_active": False})
    return jsonify(data)


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
    --accent-gold: #f5c518;
    --accent-gold-deep: #d97706;
    --accent-green: #10b981;
    --text-main: #f8fafc;
    --text-muted: #94a3b8;
    --glow-cyan: rgba(6, 182, 212, 0.25);
    --glow-gold: rgba(245, 197, 24, 0.28);
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background-color: var(--bg-dark);
    background-image:
      radial-gradient(circle at 15% 15%, rgba(59, 130, 246, 0.10) 0%, transparent 40%),
      radial-gradient(circle at 85% 85%, rgba(139, 92, 246, 0.10) 0%, transparent 40%),
      radial-gradient(circle at 50% 50%, rgba(6, 182, 212, 0.04) 0%, transparent 60%);
    background-attachment: fixed;
    color: var(--text-main);
    font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
    padding: 20px 12px;
    -webkit-font-smoothing: antialiased;
    min-height: 100vh;
    position: relative;
  }

  .bg-orbs {
    position: fixed; inset: -10%; z-index: -2; pointer-events: none;
    background:
      radial-gradient(circle at 22% 20%, rgba(245, 197, 24, 0.12) 0%, transparent 32%),
      radial-gradient(circle at 78% 12%, rgba(59, 130, 246, 0.12) 0%, transparent 32%),
      radial-gradient(circle at 55% 92%, rgba(139, 92, 246, 0.10) 0%, transparent 38%);
    animation: bgDrift 16s ease-in-out infinite alternate;
    filter: blur(2px);
  }
  @keyframes bgDrift {
    0%   { transform: translate(0, 0) scale(1); }
    100% { transform: translate(-3%, 2.5%) scale(1.1); }
  }
  .bg-grid {
    position: fixed; inset: 0; z-index: -1; pointer-events: none; opacity: 0.5;
    background-image: repeating-linear-gradient(115deg, rgba(245,197,24,0.035) 0px, rgba(245,197,24,0.035) 1px, transparent 1px, transparent 90px);
  }

  /* ── Accesibilitate ── */
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.001ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.001ms !important;
      scroll-behavior: auto !important;
    }
  }
  button:focus-visible, input:focus-visible, a:focus-visible, label:focus-visible {
    outline: 2px solid var(--accent-gold);
    outline-offset: 2px;
  }
  .sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
  }

  .container { max-width: 560px; margin: 0 auto; }

  .header-box { text-align: center; margin-bottom: 24px; position: relative; }
  .brand-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(245, 197, 24, 0.1); border: 1px solid rgba(245, 197, 24, 0.3);
    padding: 4px 12px; border-radius: 99px; font-size: 11px; font-weight: 700;
    color: var(--accent-gold); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 8px;
  }
  .pulse-dot {
    width: 6px; height: 6px; background-color: var(--accent-gold); border-radius: 50%;
    box-shadow: 0 0 8px var(--accent-gold); animation: pulse 1.8s infinite;
  }
  @keyframes pulse { 0%{ opacity: 0.3; } 50%{ opacity: 1; } 100%{ opacity: 0.3; } }
  .title-main {
    font-size: 26px; font-weight: 800;
    background: linear-gradient(135deg, #ffffff 0%, #f3e3ad 45%, var(--accent-gold) 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent; letter-spacing: -0.5px;
  }
  .subtitle { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

  @keyframes cardIn { from{ opacity:0; transform:translateY(10px); } to{ opacity:1; transform:translateY(0); } }
  .glass-card {
    background: var(--card-bg); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
    border: 1px solid var(--card-border); border-radius: 20px; padding: 18px; margin-bottom: 14px;
    box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37); transition: transform 0.15s ease, border-color 0.2s ease;
    animation: cardIn 0.4s cubic-bezier(0.16,1,0.3,1) backwards;
  }
  .glass-card:hover { border-color: rgba(255, 255, 255, 0.18); }
  .glass-card:active { transform: scale(0.985); }
  .glass-card:nth-child(1){ animation-delay: 0s; }
  .glass-card:nth-child(2){ animation-delay: .05s; }
  .glass-card:nth-child(3){ animation-delay: .1s; }
  .glass-card:nth-child(4){ animation-delay: .15s; }
  .glass-card:nth-child(5){ animation-delay: .2s; }
  .glass-card:nth-child(n+6){ animation-delay: .22s; }

  .upload-card { border: 1px dashed rgba(245, 197, 24, 0.35); background: rgba(245, 197, 24, 0.03); text-align: center; }
  .file-input { display: none; }
  .btn-upload {
    background: linear-gradient(135deg, var(--accent-gold), var(--accent-gold-deep)); color: #0a0a0a; border: none;
    padding: 11px 22px; border-radius: 12px; font-size: 13px; font-weight: 800; cursor: pointer;
    box-shadow: 0 4px 14px var(--glow-gold); transition: all 0.15s ease; display: inline-block;
  }
  .btn-upload:hover { transform: translateY(-1px); box-shadow: 0 6px 20px var(--glow-gold); }
  .btn-upload:active { transform: scale(0.96); }
  .status-text { font-size: 12px; color: var(--text-muted); margin-top: 10px; line-height: 1.4; }

  .tabs-wrapper { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 12px; margin-bottom: 16px; scrollbar-width: none; }
  .tabs-wrapper::-webkit-scrollbar { display: none; }
  .tab-btn {
    background: rgba(15, 23, 42, 0.6); border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 12px 16px; min-height: 40px; border-radius: 12px; font-size: 12px; font-weight: 600; cursor: pointer;
    white-space: nowrap; transition: all 0.15s ease;
  }
  .tab-btn:active, .chip-btn:active, .filter-chip:active, .bb-toggle-btn:active { transform: scale(0.94); }
  .tab-btn.active {
    background: linear-gradient(135deg, rgba(245, 197, 24, 0.22), rgba(217, 119, 6, 0.22));
    border-color: var(--accent-gold); color: #fff; box-shadow: 0 0 15px var(--glow-gold);
  }

  .challenge-card {
    border: 1px solid var(--accent-gold);
    background: radial-gradient(circle at top right, rgba(245, 197, 24, 0.15), var(--card-bg));
    box-shadow: 0 0 25px var(--glow-gold); position: relative; overflow: hidden;
  }
  .challenge-badge {
    position: absolute; top: 0; right: 0; background: linear-gradient(135deg, var(--accent-gold), #d97706);
    color: #000; font-weight: 800; font-size: 10px; padding: 4px 12px; border-bottom-left-radius: 12px;
    text-transform: uppercase; letter-spacing: 0.5px;
  }

  .card-header-line { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); margin-bottom: 8px; font-weight: 500; }
  .match-title { font-size: 16px; font-weight: 700; color: #fff; margin-bottom: 12px; }
  .pred-row {
    display: flex; justify-content: space-between; align-items: center; background: rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 10px 12px; margin-bottom: 8px;
  }
  .pred-target { font-size: 13px; font-weight: 700; color: var(--accent-cyan); }
  .risk-tag { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 6px; text-transform: uppercase; }
  .risk-Scazut { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
  .risk-Mediu { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
  .risk-Ridicat { background: rgba(239, 68, 68, 0.2); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.3); }
  .goals-estimate { font-size: 11px; color: var(--text-muted); margin-top: 6px; display: flex; gap: 12px; }

  .ticket-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid var(--card-border); }
  .ticket-odd-display { font-size: 22px; font-weight: 800; color: var(--accent-gold); text-shadow: 0 0 10px var(--glow-gold); }
  .ticket-selection-item { display: flex; justify-content: space-between; font-size: 12px; padding: 8px 0; border-bottom: 1px dashed rgba(255, 255, 255, 0.05); }

  .disclaimer-box { background: rgba(15, 23, 42, 0.9); border: 1px solid var(--card-border); border-radius: 14px; padding: 12px 14px; font-size: 11px; color: var(--text-muted); line-height: 1.5; margin-bottom: 16px; }
  .empty-state { text-align: center; padding: 36px 16px; color: var(--text-muted); font-size: 13px; }
  .footer-text { font-size: 10px; color: var(--text-muted); text-align: center; margin-top: 24px; opacity: 0.7; line-height: 1.4; }

  .chip-row { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
  .chip-btn {
    background: rgba(6, 182, 212, 0.12); border: 1px solid rgba(6, 182, 212, 0.3); color: var(--accent-cyan);
    padding: 10px 15px; min-height: 38px; border-radius: 8px; font-size: 12px; font-weight: 700; cursor: pointer;
  }
  .chip-btn.gold { background: rgba(245, 158, 11, 0.12); border-color: rgba(245, 158, 11, 0.35); color: var(--accent-gold); }
  .odd-input-row { display: flex; gap: 8px; }
  .filter-chip {
    background: rgba(255,255,255,0.05); border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 10px 16px; min-height: 38px; border-radius: 10px; font-size: 12px; font-weight: 700; cursor: pointer;
  }
  .filter-chip[data-risk="Scazut"].active { background: rgba(16,185,129,0.18); border-color: #10b981; color:#34d399; }
  .filter-chip[data-risk="Mediu"].active { background: rgba(245,158,11,0.18); border-color: #f59e0b; color:#fbbf24; }
  .filter-chip[data-risk="Ridicat"].active { background: rgba(239,68,68,0.18); border-color: #ef4444; color:#fca5a5; }
  .bb-toggle-btn {
    display:block; width:100%; text-align:center; margin-top:10px; background: rgba(139,92,246,0.12);
    border:1px solid rgba(139,92,246,0.35); color: var(--accent-purple); padding: 11px 12px; min-height: 40px;
    border-radius: 10px; font-size: 12px; font-weight: 700; cursor:pointer;
  }
  .bb-panel { margin-top: 8px; }

  .section-label { font-size: 12px; font-weight: 800; color: var(--text-muted); letter-spacing: 0.5px; margin: 18px 0 10px; text-transform: uppercase; }
  .grade-btn {
    flex: 1; padding: 11px; min-height: 40px; border-radius: 10px; font-size: 12px; font-weight: 700; cursor: pointer;
  }
  .grade-win { background: rgba(16,185,129,0.15); border: 1px solid #10b981; color: #34d399; }
  .grade-loss { background: rgba(239,68,68,0.15); border: 1px solid #ef4444; color: #fca5a5; }
  .grade-win:active, .grade-loss:active { transform: scale(0.94); }

  /* ── Animatie "scanare" la generarea biletului ── */
  .scan-loader { display: flex; flex-direction: column; align-items: center; gap: 16px; padding: 34px 20px; }
  .scan-ring {
    width: 54px; height: 54px; border-radius: 50%;
    border: 3px solid rgba(245, 197, 24, 0.15); border-top-color: var(--accent-gold);
    animation: scanSpin 0.85s linear infinite;
    box-shadow: 0 0 18px rgba(245, 197, 24, 0.25);
  }
  @keyframes scanSpin { to { transform: rotate(360deg); } }
  .scan-text {
    font-size: 11px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
    color: var(--accent-gold); animation: scanPulse 1.4s ease-in-out infinite;
  }
  @keyframes scanPulse { 0%,100%{ opacity: 0.45; } 50%{ opacity: 1; } }
  .scan-bars { display: flex; gap: 4px; align-items: flex-end; height: 18px; }
  .scan-bars span {
    width: 4px; background: var(--accent-gold); border-radius: 2px;
    animation: scanBar 0.9s ease-in-out infinite;
  }
  .scan-bars span:nth-child(1){ animation-delay: 0s; }
  .scan-bars span:nth-child(2){ animation-delay: .12s; }
  .scan-bars span:nth-child(3){ animation-delay: .24s; }
  .scan-bars span:nth-child(4){ animation-delay: .36s; }
  .scan-bars span:nth-child(5){ animation-delay: .48s; }
  @keyframes scanBar { 0%,100%{ height: 5px; } 50%{ height: 18px; } }

  .odd-value.reveal-glow { animation: oddGlow 1s ease-out; }
  @keyframes oddGlow {
    0%   { text-shadow: 0 0 0 rgba(245,197,24,0); }
    35%  { text-shadow: 0 0 22px rgba(245,197,24,0.95); }
    100% { text-shadow: 0 0 10px var(--glow-gold); }
  }
  #target-odd-input {
    background: rgba(0, 0, 0, 0.3); border: 1px solid var(--card-border); color: #fff;
    border-radius: 10px; padding: 10px 12px; font-size: 14px; flex: 1; min-width: 0; font-family: inherit;
  }
</style>
</head>
<body>
<div class="bg-orbs"></div>
<div class="bg-grid"></div>

<div class="container">

  <div class="header-box">
    <div class="brand-badge"><span class="pulse-dot"></span> XMTS ENGINE V2</div>
    <div class="title-main">Predictive Analytics</div>
    <div class="subtitle">Model statistic Poisson calibrat pe piata cotatiilor</div>
  </div>

  <div class="glass-card upload-card">
    <div style="font-size: 13px; font-weight: 700; margin-bottom: 10px; color: #fff;">
      ⚡ Incarca fisier Fixtures (.CSV)
    </div>
    <label for="csvFileInput" class="btn-upload">Selecteaza CSV</label>
    <input type="file" id="csvFileInput" class="file-input" accept=".csv" onchange="uploadCSV()">
    <div class="status-text" id="upload-status">Asteapta un fisier de pe football-data.co.uk</div>
  </div>

  <div class="tabs-wrapper" role="tablist" aria-label="Sectiuni">
    <button class="tab-btn active" role="tab" aria-selected="true" onclick="switchTab('challenge', this)">🎯 Challenge 1.50</button>
    <button class="tab-btn" role="tab" aria-selected="false" onclick="switchTab('sigure', this)">🔥 Selectii Sigure</button>
    <button class="tab-btn" role="tab" aria-selected="false" onclick="switchTab('toate', this)">📋 Toate Meciurile</button>
    <button class="tab-btn" role="tab" aria-selected="false" onclick="switchTab('betbuilder', this)">🧩 BetBuilder</button>
    <button class="tab-btn" role="tab" aria-selected="false" onclick="switchTab('cartonase', this)">🟨 Cartonase & Cornere</button>
    <button class="tab-btn" role="tab" aria-selected="false" onclick="switchTab('bilete', this)">🎟 Generator Bilete</button>
    <button class="tab-btn" role="tab" aria-selected="false" onclick="switchTab('weekend', this)">🔥 Bilet Weekend</button>
    <button class="tab-btn" role="tab" aria-selected="false" onclick="switchTab('targetodd', this)">🎯 Cota 1.30-1.40</button>
    <button class="tab-btn" role="tab" aria-selected="false" onclick="switchTab('rezultate', this)">📊 Rezultate</button>
    <button class="tab-btn" role="tab" aria-selected="false" onclick="switchTab('ajutor', this)">🆘 Ajutor</button>
  </div>

  <div id="tab-content">
    <div class="glass-card empty-state">Incarca fisierul fixtures.csv pentru a rula modelul.</div>
  </div>

  <div class="footer-text">
    Informatii cu caracter statistic. Nu constituie indemn la pariere. Joaca responsabil.
  </div>

</div>

<script>
let cachedData = { matches: [], challenge: null, stats_uploaded: false };
let currentTab = 'challenge';
let activeRiskFilters = new Set(['Scazut', 'Mediu', 'Ridicat']);
const MAX_TICKET_LEGS = 10;
const CHALLENGE_TARGET_ODD = 1.5;
const TICKET_DISCLAIMER = "Cota este calculata direct pe baza distributiei de probabilitate teoretica. Combinarea mai multor evenimente scade rata totala de succes a biletului.";

const AJUTOR_HTML = `
  <div class="glass-card" style="border-color:var(--accent-gold);">
    <div style="font-size:15px;font-weight:800;margin-bottom:10px;color:#fff;">⚠️ Citeste asta intai</div>
    <div style="font-size:13px;line-height:1.6;color:var(--text-muted);">
      Aplicatia calculeaza pronosticuri pornind chiar de la cotele caselor de pariuri. Asta inseamna
      ca, in medie, pe termen lung, urmarirea acestor pronosticuri nu poate produce profit constant -
      reproduce (minus marja casei) ceea ce piata deja crede despre fiecare meci. Nu exista o versiune
      de algoritm care schimba asta - e o proprietate matematica a modului in care functioneaza
      cotele, nu un defect de cod. Trateaza aplicatia ca pe un instrument de analiza si organizare,
      nu ca pe o sursa de venit.
    </div>
  </div>

  <div class="glass-card">
    <div style="font-size:14px;font-weight:800;margin-bottom:10px;color:#fff;">📖 Cum citesti aplicatia</div>
    <div style="font-size:13px;line-height:1.8;color:var(--text-muted);">
      <b style="color:#fff;">Pronostic Principal</b> - piata cu cea mai mare probabilitate calculata pentru acel meci.<br>
      <b style="color:#fff;">Alternativ</b> - apare doar cand niciun pronostic standard nu trece pragul de incredere; e o piata secundara, mai sigura prin constructie matematica.<br>
      <b style="color:#fff;">Risc Scazut / Mediu / Ridicat</b> - cat de departe e procentul calculat fata de pragurile interne. Nu e o garantie - e doar increderea modelului in propria estimare.<br>
      <b style="color:#fff;">Cota 1.30-1.40</b> - piata cea mai apropiata de acel interval, nu neaparat cea mai probabila piata a meciului.<br>
      <b style="color:#fff;">BetBuilder</b> - probabilitatea REALA a mai multor conditii simultan la acelasi meci (nu produsul a doua procente separate - ar fi gresit matematic).
    </div>
  </div>

  <div class="glass-card">
    <div style="font-size:14px;font-weight:800;margin-bottom:10px;color:#fff;">💰 Daca tot decizi sa participi</div>
    <div style="font-size:13px;line-height:1.8;color:var(--text-muted);">
      <b style="color:#fff;">1. Bankroll separat.</b> O suma pe care ti-o poti permite sa o pierzi integral, complet separata de bugetul de zi cu zi.<br><br>
      <b style="color:#fff;">2. Miza procentuala, nu fixa.</b> 1-3% din bankroll per pariu. Daca bankroll-ul scade, miza scade automat cu el - nu mari miza ca sa "recuperezi".<br><br>
      <b style="color:#fff;">3. Niciodata nu urmari pierderile.</b> O miza mai mare dupa o pierdere, ca sa compensezi, e reactia care goleste bankroll-ul cel mai repede.<br><br>
      <b style="color:#fff;">4. Limita de pierdere stabilita INAINTE.</b> Zilnica sau saptamanala. Cand o atingi, te opresti, indiferent cum "simti" ca merge ziua.<br><br>
      <b style="color:#fff;">5. Judeca modelul pe esantioane mari.</b> 5-10 rezultate nu spun nimic statistic. Un pronostic de 65% ar trebui sa iasa corect de-aproximativ 65 de ori din 100, nu de fiecare data - abia pe 50-100+ meciuri poti vedea daca procentele chiar se confirma.
    </div>
  </div>

  <div class="glass-card">
    <div style="font-size:14px;font-weight:800;margin-bottom:10px;color:#fff;">🛑 Cand te opresti de tot</div>
    <div style="font-size:13px;line-height:1.8;color:var(--text-muted);">
      Opreste-te si cere ajutor daca recunosti oricare dintre astea:<br>
      • Pariezi bani pe care nu-ti poti permite sa-i pierzi, sau imprumuti ca sa pariezi.<br>
      • Maresti miza ca sa recuperezi pierderi.<br>
      • Ascunzi de familie sau apropiati cat pariezi sau cat ai pierdut.<br>
      • Pariezi ca sa scapi de stres, plictiseala sau tristete.<br>
      • Ai incercat sa te opresti sau sa reduci si nu ai reusit.
    </div>
  </div>

  <div class="glass-card" style="border-color:rgba(16,185,129,0.4);">
    <div style="font-size:14px;font-weight:800;margin-bottom:10px;color:#fff;">🤝 Resurse (Romania)</div>
    <div style="font-size:13px;line-height:1.9;color:var(--text-muted);">
      <b style="color:#fff;">Joc Responsabil</b> - linie telefonica gratuita si anonima, consiliere psihologica:<br>
      📞 <b style="color:#34d399;">0800 800 099</b> · jocresponsabil.ro<br><br>
      <b style="color:#fff;">Autoexcludere nationala</b> - prin ONJN (Oficiul National pentru Jocuri de Noroc) sau prin orice operator licentiat, te poti bloca legal de pe toate platformele licentiate din Romania.<br><br>
      Interzis sub 18 ani.
    </div>
  </div>
`;

function formatOdd(o){ return o >= 100 ? Math.round(o).toString() : o.toFixed(2); }
function formatPct(p){
  if(p >= 1) return p.toFixed(1);
  if(p >= 0.01) return p.toFixed(2);
  return p.toFixed(4);
}

function riskFilterBar(){
  const risks = ['Scazut','Mediu','Ridicat'];
  const labels = {Scazut:'🟢 Scazut', Mediu:'🟡 Mediu', Ridicat:'🔴 Ridicat'};
  return '<div class="chip-row">' + risks.map(r =>
    `<button class="filter-chip ${activeRiskFilters.has(r) ? 'active' : ''}" data-risk="${r}" onclick="toggleRiskFilter('${r}')">${labels[r]}</button>`
  ).join('') + '</div>';
}

function toggleRiskFilter(risk){
  if(activeRiskFilters.has(risk)) activeRiskFilters.delete(risk); else activeRiskFilters.add(risk);
  render();
}

/* ── BetBuilder pe cerere, pt. orice meci (nu doar top 5 ligi) ──
   Foloseste exp_goals_home/exp_goals_away, deja calculate pt. fiecare meci,
   ca sa calculeze aceleasi combinatii ca la meciurile importante, direct in browser. */
function factorial(n){ let r = 1; for(let i=2;i<=n;i++) r *= i; return r; }
function poissonPmf(k, lam){
  lam = Math.max(lam, 0.02);
  return Math.exp(-lam) * Math.pow(lam, k) / factorial(k);
}
const DIXON_COLES_RHO = -0.08;
function dixonColesTau(x, y, lam, mu, rho){
  if(x===0 && y===0) return 1 - (lam*mu*rho);
  if(x===0 && y===1) return 1 + (lam*rho);
  if(x===1 && y===0) return 1 + (mu*rho);
  if(x===1 && y===1) return 1 - rho;
  return 1.0;
}
const BETBUILDER_COMBOS_JS = [
  ["1 & Peste 1.5 goluri", (h,a) => h>a && (h+a)>1.5],
  ["1 & GG Da", (h,a) => h>a && h>0 && a>0],
  ["2 & Peste 1.5 goluri", (h,a) => h<a && (h+a)>1.5],
  ["2 & GG Da", (h,a) => h<a && h>0 && a>0],
  ["X & Sub 2.5 goluri", (h,a) => h===a && (h+a)<2.5],
  ["GG Da & Peste 2.5 goluri", (h,a) => h>0 && a>0 && (h+a)>2.5],
  ["Sansa Dubla 1X & Sub 3.5 goluri", (h,a) => h>=a && (h+a)<3.5],
  ["Sansa Dubla X2 & Sub 3.5 goluri", (h,a) => h<=a && (h+a)<3.5],
];
function computeBetbuilderJS(lamH, lamA, maxG=12, topN=3, minPct=0.30){
  const phList = [], paList = [];
  for(let i=0;i<maxG;i++){ phList.push(poissonPmf(i, lamH)); paList.push(poissonPmf(i, lamA)); }
  const scored = BETBUILDER_COMBOS_JS.map(([label, cond]) => {
    let p = 0;
    for(let h=0;h<maxG;h++) for(let a=0;a<maxG;a++) if(cond(h,a)) p += phList[h]*paList[a]*dixonColesTau(h,a,lamH,lamA,DIXON_COLES_RHO);
    return [label, p];
  });
  scored.sort((x,y) => y[1]-x[1]);
  return scored.slice(0, topN).filter(([,p]) => p >= minPct).map(([label,p]) => ({combo:label, pct: Math.round(p*1000)/10}));
}
function toggleBetbuilderPanel(btn, lamH, lamA){
  const panel = btn.nextElementSibling;
  if(panel.style.display === 'block'){ panel.style.display = 'none'; return; }
  if(!panel.dataset.filled){
    const combos = computeBetbuilderJS(lamH, lamA);
    panel.innerHTML = combos.length
      ? combos.map(c => `<div class="ticket-selection-item"><span>${c.combo}</span><span style="font-weight:700;color:var(--accent-cyan);">${c.pct}%</span></div>`).join('')
      : '<div style="font-size:11px;color:var(--text-muted);padding:8px 0;">Nicio combinatie cu sansa suficienta (peste 30%) la acest meci.</div>';
    panel.dataset.filled = '1';
  }
  panel.style.display = 'block';
}

const RISK_ICONS = { Scazut: '●', Mediu: '▲', Ridicat: '■' };

/* ── Notare rezultate + calibrare reala (verde/rosu) ──
   Separat de cache-ul zilnic de meciuri: "pending" tine meciurile care asteapta sa fie
   notate (persista cateva zile, ca sa poti nota si mai tarziu), "history" tine notarile
   definitive, pe termen nelimitat - din ele calculam precizia reala a modelului. */
const PENDING_KEY = 'xmts_pending_grades_v1';
const HISTORY_KEY = 'xmts_prediction_history_v1';

function matchGradeKey(m){ return m.date + '|' + m.home + '|' + m.away; }

function loadPending(){ try{ return JSON.parse(localStorage.getItem(PENDING_KEY) || '[]'); } catch(e){ return []; } }
function savePending(list){ try{ localStorage.setItem(PENDING_KEY, JSON.stringify(list)); } catch(e){} }
function loadHistory(){ try{ return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); } catch(e){ return []; } }
function saveHistory(list){ try{ localStorage.setItem(HISTORY_KEY, JSON.stringify(list)); } catch(e){} }

function mergeIntoPending(matches){
  const pending = loadPending();
  const history = loadHistory();
  const known = new Set([...pending, ...history].map(matchGradeKey));
  for(const m of matches || []){
    if(m.fara_pronostic) continue;
    const key = matchGradeKey(m);
    if(known.has(key)) continue;
    pending.push({
      date: m.date, league: m.league, home: m.home, away: m.away,
      pick: m.pick_for_ticket || m.principal,
      pct: m.pick_pct != null ? m.pick_pct : m.principal_pct,
      risc: m.risc,
    });
    known.add(key);
  }
  const cutoff = new Date(); cutoff.setDate(cutoff.getDate() - 5);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  savePending(pending.filter(p => p.date >= cutoffStr));
}

function gradeMatchByIndex(index, result){
  const pending = loadPending();
  if(index < 0 || index >= pending.length) return;
  const item = pending[index];
  item.result = result;
  item.graded_at = new Date().toISOString();
  pending.splice(index, 1);
  const history = loadHistory();
  history.push(item);
  savePending(pending);
  saveHistory(history);
  render();
}

function clearHistory(){
  if(!confirm('Sigur vrei sa stergi tot istoricul de notari? Nu se poate anula.')) return;
  localStorage.removeItem(HISTORY_KEY);
  localStorage.removeItem(PENDING_KEY);
  render();
}

function computeAccuracyStats(history){
  const byRisk = { Scazut: [], Mediu: [], Ridicat: [] };
  for(const h of history){ if(byRisk[h.risc]) byRisk[h.risc].push(h); }
  const total = history.length;
  const wins = history.filter(h => h.result === 'win').length;
  const rows = ['Scazut','Mediu','Ridicat'].map(r => {
    const list = byRisk[r];
    const w = list.filter(h => h.result === 'win').length;
    return {
      risc: r, n: list.length,
      hitRate: list.length ? (w / list.length * 100) : null,
      avgPct: list.length ? (list.reduce((s,h) => s + h.pct, 0) / list.length) : null,
    };
  });
  return { total, wins, overallRate: total ? (wins / total * 100) : null, rows };
}

function resultsSummaryCard(history){
  if(history.length === 0){
    return '<div class="glass-card empty-state">Inca nu ai notat niciun rezultat. Noteaza meciurile de mai jos dupa ce se termina, ca sa vezi aici cat de bine se potrivesc procentele calculate cu ce s-a intamplat in realitate.</div>';
  }
  const s = computeAccuracyStats(history);
  const rows = s.rows.filter(r => r.n > 0).map(r => `
    <div class="ticket-selection-item">
      <span>${RISK_ICONS[r.risc]} ${r.risc} (${r.n} notate)</span>
      <span style="font-weight:700;">${r.hitRate.toFixed(1)}% reale · ${r.avgPct.toFixed(1)}% estimat</span>
    </div>`).join('');
  const rateColor = s.overallRate >= 55 ? '#34d399' : (s.overallRate >= 40 ? '#fbbf24' : '#fca5a5');
  return `
    <div class="glass-card">
      <div style="font-size:14px;font-weight:800;margin-bottom:10px;color:#fff;">📊 Precizia modelului (${s.total} notate)</div>
      <div style="text-align:center;margin-bottom:12px;">
        <span style="font-size:32px;font-weight:800;color:${rateColor};">${s.overallRate.toFixed(1)}%</span>
        <div style="font-size:11px;color:var(--text-muted);">${s.wins} din ${s.total} corecte</div>
      </div>
      ${rows}
      <div style="font-size:11px;color:var(--text-muted);margin-top:10px;">"Estimat" = increderea medie data de model la momentul predictiei. Daca "reale" e apropiat de "estimat", modelul e bine calibrat. Sub 20-30 de notari, cifrele astea inca nu spun mare lucru statistic.</div>
    </div>`;
}

function pendingCardByIndex(p, i){
  return `
    <div class="glass-card">
      <div class="card-header-line"><span>${p.league} · ${p.date}</span></div>
      <div class="match-title">${p.home} vs ${p.away}</div>
      <div class="pred-row">
        <span class="pred-target">${p.pick} (${p.pct}%)</span>
        <span class="risk-tag risk-${p.risc}">${RISK_ICONS[p.risc] || ''} ${p.risc}</span>
      </div>
      <div style="display:flex;gap:8px;margin-top:10px;">
        <button class="grade-btn grade-win" onclick="gradeMatchByIndex(${i}, 'win')">✅ A iesit</button>
        <button class="grade-btn grade-loss" onclick="gradeMatchByIndex(${i}, 'loss')">❌ N-a iesit</button>
      </div>
    </div>`;
}

function historyLogItem(h){
  const color = h.result === 'win' ? '#10b981' : '#ef4444';
  const icon = h.result === 'win' ? '✅' : '❌';
  return `
    <div class="ticket-selection-item" style="border-left:3px solid ${color};padding-left:10px;">
      <span>${icon} ${h.home} vs ${h.away} - ${h.pick}</span>
      <span style="font-weight:700;">${h.pct}%</span>
    </div>`;
}

function renderResultsTab(){
  const pending = loadPending();
  const history = loadHistory();
  const summary = resultsSummaryCard(history);
  const pendingHtml = pending.length
    ? `<div class="section-label">DE NOTAT (${pending.length})</div>` + pending.map((p, i) => pendingCardByIndex(p, i)).join('')
    : '<div class="section-label">DE NOTAT</div><div class="glass-card empty-state">Niciun meci in asteptare de notare.</div>';
  const recent = [...history].reverse().slice(0, 20);
  const historyHtml = recent.length
    ? `<div class="section-label">ISTORIC RECENT</div><div class="glass-card">${recent.map(historyLogItem).join('')}</div>
       <button class="btn-upload" style="background:linear-gradient(135deg,#ef4444,#b91c1c);margin-top:6px;width:100%;text-align:center;" onclick="clearHistory()">🗑️ Sterge istoricul</button>`
    : '';
  return summary + pendingHtml + historyHtml;
}

const MAX_WEEKEND_LEGS = 15;

function renderWeekendTab(){
  const allMatches = cachedData.matches || [];
  if(allMatches.length === 0){
    return '<div class="glass-card empty-state">Nu exista date incarcate. Adauga un fisier CSV mai sus.</div>';
  }
  const wDates = weekendDates();
  const wMatches = weekendMatches();
  if(wMatches.length === 0){
    const otherDates = [...new Set(allMatches.map(m => m.date))].sort();
    return `<div class="glass-card empty-state">Fisierul incarcat nu are meciuri pentru weekend-ul urmator (${wDates.join(', ')}).<br><br>Acopera: ${otherDates.join(', ')}.<br><br>Incarca un fixtures.csv mai recent cand apare.</div>`;
  }
  return `
    <div class="glass-card">
      <div style="font-size:14px;font-weight:800;margin-bottom:6px;color:#fff;">🔥 Bilet Weekend - cota mare</div>
      <div class="status-text" style="margin-bottom:10px;">Acopera ${wDates.join(', ')} · ${wMatches.length} meciuri disponibile in fisier</div>
      <div class="chip-row">
        <button class="chip-btn gold" onclick="setWeekendTargetOdd(10)">10x</button>
        <button class="chip-btn gold" onclick="setWeekendTargetOdd(25)">25x</button>
        <button class="chip-btn gold" onclick="setWeekendTargetOdd(50)">50x</button>
        <button class="chip-btn gold" onclick="setWeekendTargetOdd(100)">100x</button>
        <button class="chip-btn gold" onclick="setWeekendTargetOdd(500)">500x</button>
      </div>
      <div class="odd-input-row">
        <label for="weekend-odd-input" class="sr-only">Cota tinta weekend</label>
        <input type="number" id="weekend-odd-input" min="1.1" max="1000" step="0.1" value="25" aria-label="Cota tinta weekend">
        <button class="btn-upload" onclick="generateWeekendTicket()">Genereaza</button>
      </div>
      <div class="status-text">Maxim ${MAX_WEEKEND_LEGS} meciuri - foloseste tot poolul din weekend (nu doar azi), ca sa ajunga la cote mari fara sa fie nevoie de zeci de mize riscante.</div>
    </div>
    <div id="weekend-ticket-result"></div>`;
}

function setWeekendTargetOdd(v){
  document.getElementById('weekend-odd-input').value = v;
  generateWeekendTicket();
}

async function generateWeekendTicket(){
  const input = document.getElementById('weekend-odd-input');
  let target = parseFloat(input.value);
  if(isNaN(target) || target < 1.1) target = 1.1;
  if(target > 1000) target = 1000;
  input.value = target;

  const result = document.getElementById('weekend-ticket-result');
  result.innerHTML = `
    <div class="glass-card scan-loader">
      <div class="scan-ring"></div>
      <div class="scan-bars"><span></span><span></span><span></span><span></span><span></span></div>
      <div class="scan-text">Se calculeaza combinatia optima...</div>
    </div>`;

  const pool = weekendMatches();
  const ticket = await new Promise(resolve =>
    setTimeout(() => resolve(buildCustomTicket(target, pool, MAX_WEEKEND_LEGS)), 600)
  );

  if(!ticket){
    result.innerHTML = '<div class="glass-card empty-state">Nu exista meciuri valide in weekend pentru a construi un bilet.</div>';
    return;
  }

  result.innerHTML = ticketBlock(ticket, false)
    + `<div class="disclaimer-box">${TICKET_DISCLAIMER} La cote foarte mari, probabilitatea reala a intregului bilet devine foarte mica, chiar daca fiecare piesa are sens statistic - e afisata mai sus, nu ascunsa.</div>`;

  const oddEl = result.querySelector('.odd-value');
  if(oddEl){
    oddEl.classList.add('reveal-glow');
    const decimals = ticket.combined_odd >= 100 ? 0 : 2;
    animateOddValue(oddEl, 1.00, ticket.combined_odd, 750, decimals);
  }
}

function matchCard(m) {
  const alt = m.alternativ ? `<div style="font-size: 11px; color: var(--text-muted);">Alternativ: <b>${m.alternativ}</b> (${m.alternativ_pct}%)</div>` : '';
  const noPick = m.fara_pronostic ? '<div style="font-size: 11px; color: var(--text-muted);">Meci echilibrat fara selectie clara</div>' : '';
  return `
    <div class="glass-card">
      <div class="card-header-line">
        <span>${m.league} · ${m.date} ${m.time ? '· ' + m.time : ''}</span>
        <span>${m.bookmaker || ''}</span>
      </div>
      <div class="match-title">${m.home} vs ${m.away}</div>
      <div class="pred-row">
        <span class="pred-target">${m.principal} (${m.principal_pct}%)</span>
        <span class="risk-tag risk-${m.risc}">${RISK_ICONS[m.risc] || ''} ${m.risc}</span>
      </div>
      ${alt}${noPick}
      <div class="goals-estimate">
        <span>xG Gazde: <b>${m.exp_goals_home}</b></span>
        <span>xG Oaspeti: <b>${m.exp_goals_away}</b></span>
      </div>
      <button class="bb-toggle-btn" onclick="toggleBetbuilderPanel(this, ${m.exp_goals_home}, ${m.exp_goals_away})" aria-label="Calculeaza combinatii BetBuilder pentru ${m.home} vs ${m.away}">🧩 Vreau o cota mai mare (BetBuilder)</button>
      <div class="bb-panel" style="display:none;"></div>
    </div>`;
}

function ticketBlock(t, isChallenge) {
  const legs = t.selections.map(s => `
    <div class="ticket-selection-item">
      <span><b>${s.home} vs ${s.away}</b><br><span style="color:var(--accent-cyan);">${s.pick}</span></span>
      <span style="font-weight:700;">${s.pct}%</span>
    </div>`).join('');

  const shortfallNote = (t.combined_odd < t.target_odd * 0.95)
    ? `<div style="font-size:11px;color:var(--accent-gold);margin-top:8px;">Cota tinta nu a putut fi atinsa cu meciurile disponibile - aceasta e cea mai apropiata combinatie posibila (max. ${MAX_TICKET_LEGS} meciuri).</div>`
    : '';

  return `
    <div class="glass-card ${isChallenge ? 'challenge-card' : ''}">
      ${isChallenge ? '<div class="challenge-badge">🎯 CHALLENGE COTA 1.50</div>' : ''}
      <div class="ticket-header">
        <div>
          <div style="font-size:11px; color:var(--text-muted);">TINTA COTA</div>
          <div style="font-size:13px; font-weight:700;">${t.target_odd}</div>
        </div>
        <div class="ticket-odd-display">@ <span class="odd-value">${formatOdd(t.combined_odd)}</span></div>
      </div>
      ${legs}
      <div style="font-size:11px; color:var(--text-muted); margin-top:12px; font-weight:600;">
        Probabilitate teoretica cumulata: ${formatPct(t.combined_probability_pct)}%
      </div>
      ${shortfallNote}
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

function targetOddCard(m) {
  const t = m.target_odd_pick;
  if(!t) return '';
  const note = t.in_range ? '' : `<div style="font-size:11px;color:var(--accent-gold);margin-top:8px;">Nicio piata nu a cazut exact in 1.30-1.40 la acest meci - varianta cea mai apropiata disponibila.</div>`;
  return `
    <div class="glass-card">
      <div class="card-header-line">
        <span>${m.league} · ${m.date} ${m.time ? '· ' + m.time : ''}</span>
        <span>${m.bookmaker || ''}</span>
      </div>
      <div class="match-title">${m.home} vs ${m.away}</div>
      <div class="pred-row">
        <span class="pred-target">${t.pick} (${t.pct}%)</span>
        <span style="font-weight:800;color:var(--accent-gold);font-size:16px;">@ ${t.odd}</span>
      </div>
      ${note}
    </div>`;
}

function cornersCardsCard(m) {
  const cc = m.corners_cards;
  const corners = Object.entries(cc.corners_over).map(([line,pct]) => `
    <div class="ticket-selection-item"><span>Peste ${line} cornere</span><span style="font-weight:700;">${pct}%</span></div>`).join('');
  const cards = Object.entries(cc.cards_over).map(([line,pct]) => `
    <div class="ticket-selection-item"><span>Peste ${line} cartonase</span><span style="font-weight:700;">${pct}%</span></div>`).join('');
  return `
    <div class="glass-card">
      <div class="card-header-line"><span>${m.league} · ${m.date}</span><span>Esantion: ${cc.sample} meciuri</span></div>
      <div class="match-title">${m.home} vs ${m.away}</div>
      <div class="goals-estimate" style="margin-bottom:10px;">
        <span>Estimat Cornere: <b>${cc.exp_corners}</b></span>
        <span>Estimat Cartonase: <b>${cc.exp_cards}</b></span>
      </div>
      ${corners}${cards}
    </div>`;
}

/* ── Generator de bilete personalizat (client-side) ──
   Faza 1: cele mai sigure variante disponibile, cate una per meci, max MAX_TICKET_LEGS.
   Faza 2: daca tot n-am atins tinta, completam cu variantele cu cota individuala cea mai mare
   (piete mai riscante SAU combinatii BetBuilder ale aceluiasi meci) - tot cate una per meci,
   niciodata doua variante din acelasi meci (ar fi evenimente corelate, nu independente). */
function buildCustomTicket(target, matches, maxLegs){
  maxLegs = maxLegs || MAX_TICKET_LEGS;
  const pool = [];
  for(const m of (matches || [])){
    const key = m.home + '|' + m.away;
    const pct = m.pick_pct != null ? m.pick_pct : m.principal_pct;
    const pick = m.pick_for_ticket || m.principal;
    if(pct && pct > 0){
      pool.push({ key, home:m.home, away:m.away, league:m.league, pick, pct, fairOdd: 100/pct });
    }
    if(m.betbuilder){
      for(const b of m.betbuilder){
        if(b.pct > 0){
          pool.push({ key, home:m.home, away:m.away, league:m.league, pick:b.combo, pct:b.pct, fairOdd: 100/b.pct });
        }
      }
    }
  }

  const usedMatches = new Set();
  let sel = [], cumOdd = 1, cumProb = 1;

  const safest = [...pool].sort((a,b) => b.pct - a.pct);
  for(const opt of safest){
    if(cumOdd >= target || sel.length >= maxLegs) break;
    if(usedMatches.has(opt.key)) continue;
    sel.push(opt); usedMatches.add(opt.key);
    cumOdd *= opt.fairOdd; cumProb *= opt.pct / 100;
  }

  if(cumOdd < target){
    const riskiest = pool.filter(o => !usedMatches.has(o.key)).sort((a,b) => b.fairOdd - a.fairOdd);
    for(const opt of riskiest){
      if(cumOdd >= target || sel.length >= maxLegs) break;
      sel.push(opt); usedMatches.add(opt.key);
      cumOdd *= opt.fairOdd; cumProb *= opt.pct / 100;
    }
  }

  if(sel.length === 0) return null;
  return { target_odd: target, combined_odd: cumOdd, combined_probability_pct: cumProb * 100, selections: sel };
}

function setTargetOdd(v){
  document.getElementById('target-odd-input').value = v;
  generateCustomTicket();
}

function animateOddValue(el, from, to, duration, decimals){
  const start = performance.now();
  function step(now){
    const t = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = (from + (to - from) * eased).toFixed(decimals);
    if(t < 1) requestAnimationFrame(step);
    else el.textContent = decimals === 0 ? Math.round(to).toString() : to.toFixed(decimals);
  }
  requestAnimationFrame(step);
}

async function generateCustomTicket(){
  const input = document.getElementById('target-odd-input');
  let target = parseFloat(input.value);
  if(isNaN(target) || target < 1.1) target = 1.1;
  if(target > 1000) target = 1000;
  input.value = target;

  const result = document.getElementById('custom-ticket-result');
  result.innerHTML = `
    <div class="glass-card scan-loader">
      <div class="scan-ring"></div>
      <div class="scan-bars"><span></span><span></span><span></span><span></span><span></span></div>
      <div class="scan-text">Se calculeaza combinatia optima...</div>
    </div>`;

  const ticket = await new Promise(resolve => setTimeout(() => resolve(buildCustomTicket(target, todayMatches())), 600));

  if(!ticket){
    result.innerHTML = '<div class="glass-card empty-state">Nu exista meciuri valide in acest CSV pentru a construi un bilet.</div>';
    return;
  }

  result.innerHTML = ticketBlock(ticket, false) + `<div class="disclaimer-box">${TICKET_DISCLAIMER} La cote foarte mari, probabilitatea reala a intregului bilet devine foarte mica, chiar daca fiecare piesa are sens statistic - e afisata mai sus, nu ascunsa.</div>`;

  const oddEl = result.querySelector('.odd-value');
  if(oddEl){
    oddEl.classList.add('reveal-glow');
    const decimals = ticket.combined_odd >= 100 ? 0 : 2;
    animateOddValue(oddEl, 1.00, ticket.combined_odd, 750, decimals);
  }
}

function render() {
  const content = document.getElementById('tab-content');

  if (currentTab === 'ajutor') {
    content.innerHTML = AJUTOR_HTML;
    return;
  }

  if (currentTab === 'rezultate') {
    content.innerHTML = renderResultsTab();
    return;
  }

  if (currentTab === 'weekend') {
    content.innerHTML = renderWeekendTab();
    return;
  }

  const allMatches = cachedData.matches || [];

  if (allMatches.length === 0) {
    content.innerHTML = '<div class="glass-card empty-state">Nu exista date incarcate. Adauga un fisier CSV mai sus.</div>';
    return;
  }

  const matches = todayMatches();

  if (matches.length === 0) {
    const otherDates = [...new Set(allMatches.map(m => m.date))].sort();
    content.innerHTML = `<div class="glass-card empty-state">Fisierul incarcat nu are meciuri pentru azi (${localTodayStr()}).<br><br>Acopera: ${otherDates.join(', ')}.<br><br>Incarca un fixtures.csv mai recent cand apare (de obicei de 2 ori/saptamana).</div>`;
    return;
  }

  const todayChallenge = buildCustomTicket(CHALLENGE_TARGET_ODD, matches);

  if (currentTab === 'challenge') {
    content.innerHTML = todayChallenge
      ? ticketBlock(todayChallenge, true) + `<div class="disclaimer-box">${TICKET_DISCLAIMER}</div>`
      : '<div class="glass-card empty-state">Nu sunt suficiente meciuri cu coeficient ridicat pentru un Challenge de cota 1.50 azi.</div>';
  } else if (currentTab === 'sigure') {
    const top = matches.filter(m => !m.fara_pronostic).slice(0, 10);
    content.innerHTML = top.length ? top.map(matchCard).join('') : '<div class="glass-card empty-state">Fara selectii peste pragul de incredere.</div>';
  } else if (currentTab === 'toate') {
    const filtered = matches.filter(m => activeRiskFilters.has(m.risc));
    content.innerHTML = riskFilterBar() + (filtered.length
      ? filtered.map(matchCard).join('')
      : '<div class="glass-card empty-state">Niciun meci cu riscul selectat mai sus.</div>');
  } else if (currentTab === 'targetodd') {
    content.innerHTML = `<div class="disclaimer-box">Pentru fiecare meci, aleg piata (din toate cele calculate) a carei cota corecta e cea mai apropiata de 1.30-1.40 - nu neaparat cea mai probabila piata. Cand niciuna nu cade exact in interval, arat cea mai apropiata varianta disponibila.</div>`
      + matches.map(targetOddCard).join('');
  } else if (currentTab === 'betbuilder') {
    const withCombos = matches.filter(m => m.betbuilder && m.betbuilder.length > 0);
    content.innerHTML = withCombos.length ? withCombos.map(betbuilderCard).join('')
      : '<div class="glass-card empty-state">Nu exista combinatii valide pentru ligile principale in fisier.</div>';
  } else if (currentTab === 'cartonase') {
    if (!cachedData.stats_uploaded) {
      content.innerHTML = `
        <div class="glass-card upload-card">
          <div style="font-size: 13px; font-weight: 700; margin-bottom: 8px; color: #fff;">📊 Incarca fisierul cu Istoric (ex: E0.csv)</div>
          <div class="status-text" style="margin-bottom: 12px;">Fisierele normale de fixtures nu contin datele de cornere/cartonase. Descarca fisierul complet al ligii pentru aceste calcule.</div>
          <label for="statsFileInput" class="btn-upload">Incarca CSV Istoric</label>
          <input type="file" id="statsFileInput" class="file-input" accept=".csv" onchange="uploadStatsCSV()">
          <div class="status-text" id="stats-upload-status"></div>
        </div>`;
    } else {
      const withCC = matches.filter(m => m.corners_cards);
      content.innerHTML = withCC.length ? withCC.map(cornersCardsCard).join('')
        : '<div class="glass-card empty-state">Echipele din fisier nu au putut fi potrivite in istoricul incarcat.</div>';
    }
  } else {
    content.innerHTML = `
      <div class="glass-card">
        <div style="font-size:13px;font-weight:700;margin-bottom:10px;color:#fff;">🎟 Alege cota tinta (1.1 - 1000)</div>
        <div class="chip-row">
          <button class="chip-btn" onclick="setTargetOdd(2)">2x</button>
          <button class="chip-btn" onclick="setTargetOdd(5)">5x</button>
          <button class="chip-btn" onclick="setTargetOdd(10)">10x</button>
          <button class="chip-btn gold" onclick="setTargetOdd(50)">50x</button>
          <button class="chip-btn gold" onclick="setTargetOdd(100)">100x</button>
          <button class="chip-btn gold" onclick="setTargetOdd(1000)">1000x</button>
        </div>
        <div class="odd-input-row">
          <label for="target-odd-input" class="sr-only">Cota tinta (1.1 - 1000)</label>
          <input type="number" id="target-odd-input" min="1.1" max="1000" step="0.1" value="2.0" aria-label="Cota tinta">
          <button class="btn-upload" onclick="generateCustomTicket()">Genereaza</button>
        </div>
        <div class="status-text">Maxim ${MAX_TICKET_LEGS} meciuri per bilet. La cote mari, modelul foloseste automat piete cu sansa mai mica (inclusiv combinatii BetBuilder), nu zeci de meciuri sigure.</div>
      </div>
      <div id="custom-ticket-result"></div>`;
    generateCustomTicket();
  }
}

function switchTab(tab, btn) {
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-selected', 'false'); });
  if(btn){ btn.classList.add('active'); btn.setAttribute('aria-selected', 'true'); }
  render();
}

const LOCAL_STORAGE_KEY = 'xmts_predictions_v1';

function localTodayStr(){
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function saveToLocalStorage(data){
  try{
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(data));
  } catch(e){
    console.warn('Nu am putut salva local:', e);
  }
}

function loadFromLocalStorage(){
  try{
    const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
    if(!raw) return null;
    return JSON.parse(raw);
  } catch(e){
    return null;
  }
}

function todayMatches(){
  const today = localTodayStr();
  return (cachedData.matches || []).filter(m => m.date === today);
}

function _fmtDate(d){
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function weekendDates(){
  // urmatoarele (sau curentele) zile de vineri/sambata/duminica, incepand de azi -
  // daca azi e deja sambata, nu mai include vinerea trecuta.
  const dates = [];
  const base = new Date();
  base.setHours(0, 0, 0, 0);
  for(let i = 0; i < 10; i++){
    const cur = new Date(base);
    cur.setDate(cur.getDate() + i);
    const dow = cur.getDay(); // 0=Duminica, 5=Vineri, 6=Sambata
    if(dow === 5 || dow === 6 || dow === 0){
      dates.push(_fmtDate(cur));
      if(dow === 0) break;
    }
  }
  return dates;
}

function weekendMatches(){
  const dates = new Set(weekendDates());
  return (cachedData.matches || []).filter(m => dates.has(m.date));
}

async function refreshAndCache(){
  try {
    const res = await fetch('/api/predictions');
    const data = await res.json();
    cachedData = data;
    if(data.matches && data.matches.length > 0){
      saveToLocalStorage(data);
      mergeIntoPending(data.matches);
    }
    render();
  } catch(err) {
    document.getElementById('tab-content').innerHTML = '<div class="glass-card empty-state">Eroare de conexiune cu serverul.</div>';
  }
}

async function init() {
  const cached = loadFromLocalStorage();
  if(cached){
    cachedData = cached;
    mergeIntoPending(cached.matches || []);
    render();
    return; // avem deja datele de azi, salvate in telefon - nu mai batem serverul
  }
  await refreshAndCache();
}

async function uploadCSV() {
  const fileInput = document.getElementById('csvFileInput');
  if(fileInput.files.length === 0) return;
  const status = document.getElementById('upload-status');
  status.textContent = 'Procesare in curs...';
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  try {
    const res = await fetch('/api/upload-csv', { method: 'POST', body: formData });
    const data = await res.json();
    if(data.status === 'success') {
      status.textContent = `Procesat: ${data.count} meciuri, ${data.skipped} sarite, ${data.betbuilder_matches} cu BetBuilder${data.challenge ? ', Challenge disponibil' : ''}.`;
      await refreshAndCache();
    } else {
      status.textContent = 'Eroare: ' + data.message;
    }
  } catch(e) {
    status.textContent = 'Eroare la incarcare.';
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
      status.textContent = `Preluat: ${data.teams_recunoscute} echipe, ${data.meciuri_actualizate} meciuri actualizate.`;
      await refreshAndCache();
    } else {
      status.textContent = 'Eroare: ' + data.message;
    }
  } catch(e) {
    status.textContent = 'Eroare la incarcare.';
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
