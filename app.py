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
MAX_ROWS = 300  # plafon de siguranta pt. un CSV neobisnuit de mare

# Praguri de incredere - aceleasi folosite in tot proiectul, pt. consistenta
CONFIDENCE_THRESHOLD = 0.65
LOW_RISK_THRESHOLD = 0.75
FALLBACK_MIN_CONFIDENCE = 0.55

TICKET_TARGET_ODDS = [1.5, 2.0, 3.0, 5.0]
MIN_PICK_CONFIDENCE_FOR_TICKET = 0.55


# ────────────────────────────── COTE -> PROBABILITATI REALE ──────────────────────────────
# football-data.co.uk pune cote de la mai multe case; incercam in ordine de prioritate,
# ca sa avem mereu o cota valida chiar daca Bet365 lipseste pt. un anumit meci/liga.
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

# Coduri de liga football-data.co.uk -> nume afisat. Lista neexhaustiva - ce lipseste
# se afiseaza cu codul brut din CSV.
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
    """Incearca bookmakerii in ordine de prioritate, returneaza primul set valid de cote 1X2."""
    for h_key, d_key, a_key, label in BOOKMAKER_1X2_PRIORITY:
        try:
            oh, od, oa = float(row.get(h_key) or 0), float(row.get(d_key) or 0), float(row.get(a_key) or 0)
            if oh > 1 and od > 1 and oa > 1:
                return oh, od, oa, label
        except (ValueError, TypeError):
            continue
    return None


def extract_ou25_odds(row):
    """Cote reale Peste/Sub 2.5, daca exista in CSV (nu toate fisierele le au)."""
    for over_key, under_key in OU25_PRIORITY:
        try:
            o_over, o_under = float(row.get(over_key) or 0), float(row.get(under_key) or 0)
            if o_over > 1 and o_under > 1:
                return o_over, o_under
        except (ValueError, TypeError):
            continue
    return None


def implied_probs(oh, od, oa):
    """Elimina marja casei (suma 1/cota e mereu >1) - rezulta probabilitati reale, normalizate."""
    raw_h, raw_d, raw_a = 1 / oh, 1 / od, 1 / oa
    total = raw_h + raw_d + raw_a
    return raw_h / total, raw_d / total, raw_a / total


# ────────────────────────────── MODEL POISSON CALIBRAT PE COTE ──────────────────────────────

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
    """
    Cauta (lambda_gazde, lambda_oaspeti) a caror distributie Poisson reproduce cat mai
    fidel probabilitatile reale implicite din cote (target_h/d/a). Nu exista o formula
    inversa directa pt. modelul Poisson bivariat, asa ca folosim o cautare pe grila,
    in doua faze (grosiera, apoi rafinata in jurul celui mai bun punct gasit).
    """
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
    """
    Foloseste cotele reale 1X2 (cu marja casei eliminata) pt. a calibra un model Poisson,
    din care se calculeaza toate piata standard. Piata cu probabilitatea cea mai mare devine
    pronostic principal; sub pragul de incredere, se cauta o piata secundara mai sigura prin
    constructie (Sansa Dubla etc.); daca nici aceea nu ajunge la un prag minim, nu se
    recomanda nimic pt. acel meci (nu intra in bilete).
    """
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

    # daca CSV-ul are si cote reale Peste/Sub 2.5, le preferam fata de estimarea Poisson
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


# ────────────────────────────── PROCESARE CSV ──────────────────────────────

def process_csv_content(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    processed, skipped_no_odds = [], 0

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

        processed.append({
            "league": league_display_name((row.get("Div") or "").strip()),
            "league_code": (row.get("Div") or "").strip(),
            "date": parse_uk_date(row.get("Date")),
            "time": (row.get("Time") or "").strip(),
            "home": home, "away": away,
            **pred,
        })

    # grupare pe data (crescator), iar in cadrul aceleiasi date, cele mai sigure primele
    processed.sort(key=lambda m: -(m.get("pick_pct") or 0))
    processed.sort(key=lambda m: m["date"])

    tickets = build_tickets([m for m in processed if not m.get("fara_pronostic")])
    return processed, tickets, skipped_no_odds


def build_tickets(matches):
    """
    Combina pick-urile individuale cele mai sigure in bilete, tintind cateva cote totale.
    Cota fiecarui pick = cota corecta a modelului (1/probabilitate) - vezi disclaimer in UI.
    """
    candidates = [m for m in matches if m.get("pick_pct") is not None
                  and m["pick_pct"] / 100 >= MIN_PICK_CONFIDENCE_FOR_TICKET]
    candidates.sort(key=lambda m: m["pick_pct"], reverse=True)

    tickets = []
    for target in TICKET_TARGET_ODDS:
        selection, cum_odd, cum_prob = [], 1.0, 1.0
        for m in candidates:
            if cum_odd >= target:
                break
            selection.append(m)
            cum_odd *= m["fair_odd"]
            cum_prob *= m["pick_pct"] / 100
        if len(selection) >= 2:
            tickets.append({
                "target_odd": target,
                "combined_odd": round(cum_odd, 2),
                "combined_probability_pct": round(cum_prob * 100, 1),
                "selections": [
                    {"league": s["league"], "home": s["home"], "away": s["away"],
                     "pick": s["pick_for_ticket"], "pct": s["pick_pct"]}
                    for s in selection
                ],
            })
    return tickets


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
        processed_matches, tickets, skipped = process_csv_content(content)
        cache_data = {
            "uploaded_at": datetime.now().isoformat(),
            "matches": processed_matches,
            "tickets": tickets,
            "skipped_no_odds": skipped,
            "api_active": True,
        }
        _save_json(CACHE_FILE, cache_data)
        return jsonify({"status": "success", "count": len(processed_matches),
                         "skipped": skipped, "tickets": len(tickets)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    data = _load_json(CACHE_FILE, None)
    if not data:
        return jsonify({"matches": [], "tickets": [], "api_active": False})
    return jsonify(data)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XMTS AI Predictive Analytics</title>
<style>
  :root{--bg:#080e1e;--card:#0f172a;--border:#1e293b;--accent:#38bdf8;--muted:#94a3b8;}
  *{box-sizing:border-box;}
  body{background:var(--bg);color:#fff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0;padding:16px;}
  .container{max-width:520px;margin:0 auto;}
  .header{text-align:center;font-size:20px;font-weight:800;color:var(--accent);margin:8px 0 4px;}
  .subheader{text-align:center;font-size:12px;color:var(--muted);margin-bottom:16px;}
  .upload-area{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center;margin-bottom:16px;}
  .upload-title{font-size:13px;font-weight:700;margin-bottom:10px;}
  input[type="file"]{display:none;}
  .file-label{background:#0284c7;color:#fff;padding:10px 15px;border-radius:8px;font-weight:600;cursor:pointer;font-size:13px;display:inline-block;}
  .upload-status{font-size:12px;color:var(--muted);margin-top:8px;}
  .nav-tabs{display:flex;gap:8px;overflow-x:auto;padding-bottom:12px;}
  .tab-btn{background:#111a2e;color:var(--muted);border:1px solid var(--border);padding:9px 13px;border-radius:10px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;}
  .tab-btn.active{background:#0284c7;color:#fff;border-color:var(--accent);}
  .card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px;margin-bottom:12px;}
  .card.risc-scazut{border-color:#16a34a;} .card.risc-mediu{border-color:#ca8a04;} .card.risc-ridicat{border-color:#dc2626;}
  .card-top{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:6px;}
  .match-title{font-size:15px;font-weight:700;margin-bottom:10px;}
  .pred-row{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;}
  .pred-main{font-size:13px;font-weight:700;background:#0284c7;padding:5px 10px;border-radius:6px;}
  .pred-alt{font-size:12px;color:var(--muted);}
  .risc-badge{font-size:11px;font-weight:700;padding:3px 9px;border-radius:10px;white-space:nowrap;}
  .risc-badge.Scazut{background:#14532d;color:#86efac;} .risc-badge.Mediu{background:#713f12;color:#fde68a;} .risc-badge.Ridicat{background:#7f1d1d;color:#fca5a5;}
  .exp-goals{font-size:11px;color:var(--muted);margin-top:6px;}
  .ticket-header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;}
  .ticket-target{font-size:13px;color:var(--muted);}
  .ticket-odd{font-size:18px;font-weight:800;color:#fde68a;}
  .ticket-leg{display:flex;justify-content:space-between;font-size:12px;padding:6px 0;border-top:1px solid var(--border);}
  .ticket-prob{font-size:11px;color:var(--muted);margin-top:8px;}
  .disclaimer{background:#1e293b;border:1px solid var(--border);border-radius:10px;padding:10px 14px;font-size:11px;color:var(--muted);margin-bottom:14px;line-height:1.5;}
  .empty-state{text-align:center;padding:24px 15px;color:var(--muted);font-size:14px;}
  .footer-note{font-size:11px;color:var(--muted);text-align:center;margin-top:16px;line-height:1.5;}
</style>
</head>
<body>
<div class="container">
  <div class="header">⚽ XMTS AI Analytics</div>
  <div class="subheader">Model Poisson calibrat pe cotele reale din CSV</div>

  <div class="upload-area">
    <div class="upload-title">📂 Incarca fixtures.csv (football-data.co.uk)</div>
    <label for="csvFileInput" class="file-label">Alege fisierul CSV</label>
    <input type="file" id="csvFileInput" accept=".csv" onchange="uploadCSV()">
    <div class="upload-status" id="upload-status"></div>
  </div>

  <div class="nav-tabs">
    <button class="tab-btn active" onclick="switchTab('sigure', this)">🔥 Cele mai sigure</button>
    <button class="tab-btn" onclick="switchTab('toate', this)">Toate meciurile</button>
    <button class="tab-btn" onclick="switchTab('bilete', this)">🎟️ Bilete</button>
  </div>

  <div id="tab-content"><div class="empty-state">Incarca un fisier CSV ca sa incepi.</div></div>
  <div class="footer-note">Estimari statistice pe baza cotelor reale la momentul incarcarii - nu constituie garantie de rezultat sau recomandare de pariere. Daca folosesti aceste informatii pentru pariuri, joaca responsabil.</div>
</div>

<script>
let cachedData = { matches: [], tickets: [], api_active: false };
let currentTab = 'sigure';

function riskClass(r){ return {"Scazut":"risc-scazut","Mediu":"risc-mediu","Ridicat":"risc-ridicat"}[r] || ""; }

function matchCard(m){
  const alt = m.alternativ ? `<div class="pred-alt">Alternativ: ${m.alternativ} (${m.alternativ_pct}%)</div>` : '';
  const noPick = m.fara_pronostic ? '<div class="pred-alt">Fara pronostic clar - meci echilibrat</div>' : '';
  return `
    <div class="card ${riskClass(m.risc)}">
      <div class="card-top"><span>${m.league} · ${m.date}${m.time ? ' ' + m.time : ''}</span><span>${m.bookmaker || ''}</span></div>
      <div class="match-title">${m.home} vs ${m.away}</div>
      <div class="pred-row">
        <span class="pred-main">${m.principal} (${m.principal_pct}%)</span>
        <span class="risc-badge ${m.risc}">${m.risc}</span>
      </div>
      ${alt}${noPick}
      <div class="exp-goals">Goluri estimate: ${m.exp_goals_home} - ${m.exp_goals_away}</div>
    </div>`;
}

function ticketCard(t){
  const legs = t.selections.map(s => `
    <div class="ticket-leg"><span>${s.home} vs ${s.away} - ${s.pick}</span><span>${s.pct}%</span></div>
  `).join('');
  return `
    <div class="card">
      <div class="ticket-header">
        <span class="ticket-target">Bilet ~cota ${t.target_odd}</span>
        <span class="ticket-odd">${t.combined_odd}</span>
      </div>
      ${legs}
      <div class="ticket-prob">Probabilitate estimata ca bileul intreg sa iasa: ${t.combined_probability_pct}%</div>
    </div>`;
}

function render(){
  const content = document.getElementById('tab-content');
  const matches = cachedData.matches || [];
  const tickets = cachedData.tickets || [];

  if(matches.length === 0){
    content.innerHTML = '<div class="empty-state">Nu exista meciuri. Incarca fisierul <b>fixtures.csv</b> mai sus.</div>';
    return;
  }

  if(currentTab === 'sigure'){
    const top = matches.filter(m => !m.fara_pronostic).slice(0, 10);
    content.innerHTML = top.length ? top.map(matchCard).join('') : '<div class="empty-state">Niciun meci cu incredere suficienta in acest CSV.</div>';
  } else if(currentTab === 'toate'){
    content.innerHTML = matches.map(matchCard).join('');
  } else {
    if(tickets.length === 0){
      content.innerHTML = '<div class="empty-state">Nu sunt destule meciuri sigure pentru a construi bilete.</div>';
    } else {
      const disclaimer = `<div class="disclaimer">Cota afisata e cota <b>corecta a modelului</b> (1/probabilitate calculata), nu o cota reala oferita de o casa de pariuri - o casa reala ar da o cota mai mica, din cauza marjei proprii. Combinarea mai multor meciuri intr-un bilet scade probabilitatea totala de succes, chiar daca fiecare meci in parte pare sigur.</div>`;
      content.innerHTML = disclaimer + tickets.map(ticketCard).join('');
    }
  }
}

function switchTab(tab, btn){
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  render();
}

async function init(){
  try{
    const res = await fetch('/api/predictions');
    cachedData = await res.json();
    render();
  } catch(err){
    document.getElementById('tab-content').innerHTML = '<div class="empty-state">Eroare la conectarea cu serverul.</div>';
  }
}

async function uploadCSV(){
  const fileInput = document.getElementById('csvFileInput');
  if(fileInput.files.length === 0) return;
  const status = document.getElementById('upload-status');
  status.textContent = 'Se proceseaza...';

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  try{
    const res = await fetch('/api/upload-csv', { method: 'POST', body: formData });
    const data = await res.json();
    if(data.status === 'success'){
      status.textContent = `${data.count} meciuri analizate, ${data.skipped} sarite (fara cote valide), ${data.tickets} bilete generate.`;
      init();
    } else {
      status.textContent = 'Eroare: ' + data.message;
    }
  } catch(e){
    status.textContent = 'Eroare la incarcarea fisierului.';
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
