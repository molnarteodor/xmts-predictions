import os
import json
import time
import math
import threading
from datetime import datetime

import requests
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bucharest")
except Exception:
    TZ = None  # fallback la ora serverului daca zoneinfo/tzdata lipsesc

# ────────────────────────────── CONFIG ──────────────────────────────

# ATENTIE: cheia e hardcodata aici la cererea ta explicita, pt. ca repo-ul e privat.
# Daca repo-ul devine vreodata public / e clonat / fork-uit, cheia asta se considera
# expusa si trebuie regenerata din dashboard.api-football.com.
API_TOKEN = os.getenv("API_TOKEN", "bd0e84dbde9660ece4ce8910c881c36b")
API_BASE = "https://v3.football.api-sports.io"

CACHE_FILE = "predictions_cache.json"
TEAM_CACHE_FILE = "team_history_cache.json"
TEAM_CACHE_TTL_SECONDS = 72 * 3600  # 3 zile - formatia unei echipe nu se schimba des

# Praguri de incredere pentru pronostic
CONFIDENCE_THRESHOLD = 0.65
LOW_RISK_THRESHOLD = 0.75
FALLBACK_MIN_CONFIDENCE = 0.55

FORM_LAST_N = 15  # ultimele N meciuri per echipa, folosite pt. forma
FINISHED_STATUSES = {"FT", "AET", "PEN"}

# Optional: restrange analiza la anumite ligi (ID-uri API-Football), separate prin virgula.
# Ex: LEAGUE_IDS=39,140,135,78,61,283  (Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Liga 1 Romania)
# Verifica ID-urile exacte in docs API-Football - se pot schimba. Lasa gol = toate ligile.
def _parse_league_ids(raw):
    if not raw:
        return None
    try:
        return {int(x.strip()) for x in raw.split(",") if x.strip()}
    except ValueError:
        return None

LEAGUE_IDS = _parse_league_ids(os.getenv("LEAGUE_IDS", ""))

# Plafon de siguranta pentru cota API: fiecare meci analizat costa 2 cereri
# (istoric gazde + istoric oaspeti), pe langa cererea initiala de fixtures.
# Redus la 10 (nu 25) pentru ca pe Render free, discul se sterge la fiecare
# repaus/trezire a serviciului - deci recalcularea completa se poate intampla
# de mai multe ori pe zi, iar cota API-Football gratuita e doar 100/zi.
MAX_MATCHES_PER_DAY = int(os.getenv("MAX_MATCHES_PER_DAY", "10"))


def now_local():
    return datetime.now(TZ) if TZ else datetime.now()


def to_local_time(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str)
        if TZ:
            dt = dt.astimezone(TZ)
        return dt.strftime("%H:%M")
    except Exception:
        return (iso_str or "")[11:16]


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


# ────────────────────────────── ACCES API-FOOTBALL ──────────────────────────────

def api_get(endpoint, params):
    if not API_TOKEN:
        print("[EROARE] Lipseste API_TOKEN.")
        return None
    try:
        r = requests.get(
            f"{API_BASE}/{endpoint}",
            headers={"x-apisports-key": API_TOKEN},  # doar acest header - fara x-rapidapi-host
            params=params, timeout=15,
        )
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        print(f"[EROARE API] {endpoint} {params}: {e}")
        return None
    if payload.get("errors"):
        print(f"[EROARE API] {endpoint} {params}: {payload['errors']}")
        return None
    return payload.get("response", [])


def fetch_fixtures_for_date(date_str):
    return api_get("fixtures", {"date": date_str}) or []


def fetch_team_last_matches(team_id, last_n):
    """Istoricul recent al unei echipe, cu cache de 3 zile ca sa nu consumam cota degeaba."""
    cache = _load_json(TEAM_CACHE_FILE, {})
    key = str(team_id)
    entry = cache.get(key)
    if entry and (time.time() - entry.get("fetched_at", 0)) < TEAM_CACHE_TTL_SECONDS:
        return entry["data"]

    data = api_get("fixtures", {"team": team_id, "last": last_n})
    if data is None:
        # cota depasita sau eroare - folosim cache-ul vechi daca exista, in loc sa pierdem meciul
        return entry["data"] if entry else None

    cache[key] = {"fetched_at": time.time(), "data": data}
    _save_json(TEAM_CACHE_FILE, cache)
    return data


# ────────────────────────────── STATISTICI ──────────────────────────────

def extract_form(fixtures, team_id):
    scored, conceded = [], []
    scored_home, conceded_home = [], []
    scored_away, conceded_away = [], []

    for fx in fixtures or []:
        status = ((fx.get("fixture") or {}).get("status") or {}).get("short")
        if status not in FINISHED_STATUSES:
            continue
        goals = fx.get("goals") or {}
        hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None:
            continue
        home_id = fx["teams"]["home"]["id"]
        away_id = fx["teams"]["away"]["id"]
        if home_id == team_id:
            scored.append(hg); conceded.append(ag)
            scored_home.append(hg); conceded_home.append(ag)
        elif away_id == team_id:
            scored.append(ag); conceded.append(hg)
            scored_away.append(ag); conceded_away.append(hg)

    def avg(lst, default):
        return sum(lst) / len(lst) if lst else default

    overall_scored = avg(scored, 1.25)
    overall_conceded = avg(conceded, 1.25)
    return {
        "avg_scored_home": avg(scored_home, overall_scored),
        "avg_conceded_home": avg(conceded_home, overall_conceded),
        "avg_scored_away": avg(scored_away, overall_scored),
        "avg_conceded_away": avg(conceded_away, overall_conceded),
        "n": len(scored),
    }


# ────────────────────────────── MODEL DE PREDICTIE (Poisson, Python pur) ──────────────────────────────

def poisson_pmf(k, lam):
    lam = max(lam, 0.05)
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def predict_football(home_form, away_form):
    """
    xG estimat = media dintre atacul unei echipe (in venue-ul respectiv) si apararea
    adversarului (in venue-ul respectiv), cu un mic ajustaj pt. avantajul terenului propriu.
    Din distributia Poisson rezultata se calculeaza probabilitati pentru toate piata standard;
    se alege cea mai mare ca pronostic principal. Sub pragul de incredere, se cauta o piata
    secundara care e matematic mai seigura (Sansa Dubla, linii mai largi de goluri) - nu se
    inventeaza un procent daca nici aceea nu ajunge la un prag minim.
    """
    exp_home = max(0.15, (home_form["avg_scored_home"] + away_form["avg_conceded_away"]) / 2 * 1.08)
    exp_away = max(0.15, (away_form["avg_scored_away"] + home_form["avg_conceded_home"]) / 2 * 0.96)

    max_g = 7
    p_home = p_draw = p_away = p_btts = 0.0
    p_over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    for hg in range(max_g):
        ph = poisson_pmf(hg, exp_home)
        for ag in range(max_g):
            p = ph * poisson_pmf(ag, exp_away)
            if hg > ag:
                p_home += p
            elif hg == ag:
                p_draw += p
            else:
                p_away += p
            total = hg + ag
            for line in p_over:
                if total > line:
                    p_over[line] += p
            if hg > 0 and ag > 0:
                p_btts += p

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
        "exp_goals_home": round(exp_home, 2), "exp_goals_away": round(exp_away, 2),
    }
    if best_p >= CONFIDENCE_THRESHOLD:
        result["risc"] = "Scazut" if best_p >= LOW_RISK_THRESHOLD else "Mediu"
        return result

    alt_market, alt_p = max(fallback, key=lambda kv: kv[1])
    if alt_p >= FALLBACK_MIN_CONFIDENCE:
        result["alternativ"] = alt_market
        result["alternativ_pct"] = round(alt_p * 100, 1)
        result["risc"] = "Mediu" if alt_p >= 0.65 else "Ridicat"
        return result

    result["risc"] = "Ridicat"
    result["fara_pronostic"] = True
    return result


# ────────────────────────────── PIPELINE ZILNIC ──────────────────────────────

_build_lock = threading.Lock()
_build_thread = None
_last_build_error = None


def build_daily_predictions():
    global _last_build_error
    date_str = now_local().strftime("%Y-%m-%d")
    print(f"[{now_local()}] Se construiesc predictiile pentru {date_str}...")

    if not API_TOKEN:
        _last_build_error = "Lipseste API_TOKEN."
        _save_json(CACHE_FILE, {"date": date_str, "generated_at": now_local().isoformat(),
                                 "matches": [], "error": _last_build_error})
        return

    try:
        fixtures = fetch_fixtures_for_date(date_str)
        if LEAGUE_IDS:
            fixtures = [f for f in fixtures if (f.get("league") or {}).get("id") in LEAGUE_IDS]

        total_found = len(fixtures)
        truncated = total_found > MAX_MATCHES_PER_DAY
        fixtures = fixtures[:MAX_MATCHES_PER_DAY]

        results = []
        for fx in fixtures:
            try:
                home, away = fx["teams"]["home"], fx["teams"]["away"]
                home_hist = fetch_team_last_matches(home["id"], FORM_LAST_N)
                away_hist = fetch_team_last_matches(away["id"], FORM_LAST_N)
                if not home_hist or not away_hist:
                    continue  # cota API depasita/eroare - sarim peste meci, nu inventam date

                pred = predict_football(extract_form(home_hist, home["id"]),
                                         extract_form(away_hist, away["id"]))
                results.append({
                    "league": fx["league"]["name"], "country": fx["league"].get("country", ""),
                    "time": to_local_time(fx["fixture"]["date"]),
                    "home": home["name"], "away": away["name"],
                    **pred,
                })
            except Exception as e:
                print(f"[EROARE] meci sarit: {e}")
                continue

        payload = {
            "date": date_str, "generated_at": now_local().isoformat(),
            "matches": results, "total_meciuri_gasite": total_found,
        }
        if total_found > 0 and len(results) == 0:
            payload["notice"] = (f"S-au gasit {total_found} meciuri azi, dar niciunul dintre cele "
                                  f"{min(total_found, MAX_MATCHES_PER_DAY)} verificate nu a putut fi "
                                  f"analizat - foarte probabil cota API-Football s-a epuizat azi. "
                                  f"Verifica cota ramasa pe dashboard.api-football.com.")
        elif total_found == 0:
            payload["notice"] = "Nu s-a gasit niciun meci de fotbal in raspunsul API pentru data de azi."
        elif truncated:
            payload["notice"] = (f"S-au analizat primele {MAX_MATCHES_PER_DAY} din {total_found} "
                                  f"meciuri gasite azi (limita zilnica de cereri API).")
        _save_json(CACHE_FILE, payload)
        _last_build_error = None
        print(f"[SUCCESS] {len(results)} meciuri analizate pentru {date_str}.")
    except Exception as e:
        _last_build_error = f"Eroare la generarea predictiilor: {e}"
        print(f"[EROARE FATALA] {_last_build_error}")


def get_predictions_payload():
    """
    Intoarce cache-ul de azi. Daca lipseste sau e din alta zi, porneste o reconstructie
    in fundal (non-blocant) - functioneaza corect si daca serviciul Render tocmai s-a
    trezit dintr-un repaus de inactivitate, spre deosebire de un cron intern clasic.
    """
    global _build_thread
    today = now_local().strftime("%Y-%m-%d")
    cached = _load_json(CACHE_FILE, None)

    if cached and cached.get("date") == today:
        return {"status": "ready", **cached}

    with _build_lock:
        just_started = False
        if _build_thread is None or not _build_thread.is_alive():
            _build_thread = threading.Thread(target=build_daily_predictions, daemon=True)
            _build_thread.start()
            just_started = True

    if cached:
        return {"status": "computing", "date": today, "matches": cached.get("matches", []), "stale": True}
    if not just_started and _last_build_error:
        return {"status": "error", "date": today, "matches": [], "message": _last_build_error}
    return {"status": "computing", "date": today, "matches": []}


# ────────────────────────────── INTERFATA WEB ──────────────────────────────

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Predictie2 - Analiza Fotbal</title>
<style>
  :root{--bg:#080e1e;--card:#0f172a;--border:#1e293b;--accent:#38bdf8;--muted:#94a3b8;}
  *{box-sizing:border-box;}
  body{background:var(--bg);color:#fff;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;margin:0;padding:16px;}
  .container{max-width:520px;margin:0 auto;}
  .header{text-align:center;font-size:20px;font-weight:800;color:var(--accent);margin:8px 0 4px;}
  .subheader{text-align:center;font-size:12px;color:var(--muted);margin-bottom:16px;}
  .banner{background:#1e293b;border:1px solid var(--border);border-radius:10px;padding:10px 14px;font-size:13px;color:var(--muted);margin-bottom:14px;text-align:center;}
  .banner.error{border-color:#7f1d1d;color:#fca5a5;}
  .controls{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;}
  select{background:#111a2e;color:#fff;border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:13px;}
  .checkbox-label{display:flex;align-items:center;gap:6px;cursor:pointer;background:#111a2e;border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:13px;}
  .card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px;margin-bottom:12px;}
  .card.risc-scazut{border-color:#16a34a;}
  .card.risc-mediu{border-color:#ca8a04;}
  .card.risc-ridicat{border-color:#dc2626;}
  .card-top{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:6px;}
  .match-title{font-size:15px;font-weight:700;margin-bottom:10px;}
  .pred-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;gap:8px;}
  .pred-main{font-size:13px;font-weight:700;background:#0284c7;padding:5px 10px;border-radius:6px;}
  .pred-alt{font-size:12px;color:var(--muted);}
  .risc-badge{font-size:11px;font-weight:700;padding:3px 9px;border-radius:10px;white-space:nowrap;}
  .risc-badge.Scazut{background:#14532d;color:#86efac;}
  .risc-badge.Mediu{background:#713f12;color:#fde68a;}
  .risc-badge.Ridicat{background:#7f1d1d;color:#fca5a5;}
  .exp-goals{font-size:11px;color:var(--muted);margin-top:6px;}
  .empty-state{text-align:center;padding:30px 15px;color:var(--muted);font-size:14px;}
  .footer-note{font-size:11px;color:var(--muted);text-align:center;margin-top:16px;line-height:1.5;}
</style>
</head>
<body>
<div class="container">
  <div class="header">⚽ Predictie2</div>
  <div class="subheader">Analiza statistica (model Poisson) pe formatul recent al echipelor</div>
  <div id="banner-area"></div>
  <div class="controls">
    <select id="league-filter"><option value="">Toate ligile</option></select>
    <label class="checkbox-label"><input type="checkbox" id="only-safe"> Doar risc scazut</label>
  </div>
  <div id="content"><div class="empty-state">Se incarca...</div></div>
  <div class="footer-note">Estimari statistice pe baza istoricului recent - nu constituie garantie de rezultat sau recomandare de pariere. Daca folosesti aceste informatii pentru pariuri, joaca responsabil.</div>
</div>
<script>
let allMatches = [];
let pollTimer = null;

function riskClass(r){ return {"Scazut":"risc-scazut","Mediu":"risc-mediu","Ridicat":"risc-ridicat"}[r] || ""; }

function renderMatches(){
  const league = document.getElementById('league-filter').value;
  const onlySafe = document.getElementById('only-safe').checked;
  let list = allMatches;
  if(league) list = list.filter(m => m.league === league);
  if(onlySafe) list = list.filter(m => m.risc === 'Scazut');

  const content = document.getElementById('content');
  if(list.length === 0){
    content.innerHTML = '<div class="empty-state">Niciun meci nu corespunde filtrului curent.</div>';
    return;
  }
  content.innerHTML = list.map(m => {
    const alt = m.alternativ ? `<div class="pred-alt">Alternativ AI: ${m.alternativ} (${m.alternativ_pct}%)</div>` : '';
    const noPick = m.fara_pronostic ? '<div class="pred-alt">Fara pronostic clar - meci echilibrat</div>' : '';
    return `
      <div class="card ${riskClass(m.risc)}">
        <div class="card-top"><span>${m.league} · ${m.country || ''}</span><span>${m.time}</span></div>
        <div class="match-title">${m.home} vs ${m.away}</div>
        <div class="pred-row">
          <span class="pred-main">${m.principal} (${m.principal_pct}%)</span>
          <span class="risc-badge ${m.risc}">${m.risc}</span>
        </div>
        ${alt}${noPick}
        <div class="exp-goals">Goluri estimate: ${m.exp_goals_home} - ${m.exp_goals_away}</div>
      </div>`;
  }).join('');
}

function populateLeagueFilter(){
  const sel = document.getElementById('league-filter');
  const current = sel.value;
  const leagues = [...new Set(allMatches.map(m => m.league))].sort();
  sel.innerHTML = '<option value="">Toate ligile</option>' + leagues.map(l => `<option value="${l}">${l}</option>`).join('');
  if(leagues.includes(current)) sel.value = current;
}

function showBanner(html, isError){
  document.getElementById('banner-area').innerHTML = html ? `<div class="banner ${isError?'error':''}">${html}</div>` : '';
}

async function load(){
  try{
    const res = await fetch('/api/predictions');
    const data = await res.json();

    if(data.status === 'error'){
      showBanner('Eroare la generarea predictiilor: ' + (data.message || ''), true);
      document.getElementById('content').innerHTML = '<div class="empty-state">Incearca sa reincarci pagina peste cateva minute.</div>';
      return;
    }

    allMatches = data.matches || [];
    populateLeagueFilter();
    renderMatches();

    if(data.status === 'computing'){
      showBanner(data.stale ? 'Se recalculeaza predictiile pentru azi - se afiseaza date de ieri pana atunci...' : 'Se genereaza predictiile pentru azi, te rog asteapta (poate dura 1-2 minute)...');
      if(!pollTimer) pollTimer = setTimeout(() => { pollTimer = null; load(); }, 6000);
    } else {
      showBanner(data.notice || '');
      if(pollTimer){ clearTimeout(pollTimer); pollTimer = null; }
    }
  } catch(err){
    document.getElementById('content').innerHTML = '<div class="empty-state">Eroare la conectarea cu serverul.</div>';
  }
}

document.getElementById('league-filter').addEventListener('change', renderMatches);
document.getElementById('only-safe').addEventListener('change', renderMatches);
load();
</script>
</body>
</html>
"""

app = Flask(__name__)
CORS(app)


@app.route("/api/predictions")
def api_predictions():
    return jsonify(get_predictions_payload())


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE)


# Precalculare in fundal la incarcarea modulului - functioneaza si sub gunicorn pe Render,
# nu doar cand rulezi "python app.py" direct. Nu blocheaza pornirea serverului.
get_predictions_payload()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
