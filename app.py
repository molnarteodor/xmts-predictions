import os
import json
import math
import csv
import io
import requests
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS

# 1. Configurare Timezone si Date
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bucharest")
except Exception:
    TZ = None

def today_str():
    if TZ:
        return datetime.now(TZ).strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")

# 2. Configurare Flask
app = Flask(__name__)
CORS(app)

CACHE_FILE = "matches_cache.json"
MAX_ROWS = 600
FIXTURES_CSV_URL = os.environ.get("FIXTURES_CSV_URL", "")

CONFIDENCE_THRESHOLD = 0.65
LOW_RISK_THRESHOLD = 0.75
FALLBACK_MIN_CONFIDENCE = 0.55
CHALLENGE_TARGET_ODD = 1.50

# 3. Ligi si Cote
TOP_LEAGUES = {"E0", "E1", "E2", "SP1", "SP2", "I1", "I2", "D1", "D2", "F1", "F2", "N1", "B1", "P1", "SC0", "T1", "G1"}

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
    "SC0": "Premiership (Scoția)", "SC1": "Championship (Scoția)",
    "SP1": "La Liga (Spania)", "SP2": "La Liga 2 (Spania)",
    "D1": "Bundesliga (Germania)", "D2": "Bundesliga 2 (Germania)",
    "I1": "Serie A (Italia)", "I2": "Serie B (Italia)",
    "F1": "Ligue 1 (Franța)", "F2": "Ligue 2 (Franța)",
    "N1": "Eredivisie (Olanda)", "B1": "Jupiler Pro League (Belgia)",
    "P1": "Primeira Liga (Portugalia)", "T1": "Super Lig (Turcia)", "G1": "Super League (Grecia)",
}

# 4. Utilities File System
def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[WARN] Eroare la citirea {path}: {e}")
    return default

def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[EROARE] Cache scriere eșuată la {path}: {e}")

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
        oh = float(row.get(h_key) or 0)
        od = float(row.get(d_key) or 0)
        oa = float(row.get(a_key) or 0)
        if oh > 1.01 and od > 1.01 and oa > 1.01:
            return oh, od, oa
    except (ValueError, TypeError):
        pass
    return None

def implied_probs_square_root(oh, od, oa):
    raw_h = math.sqrt(1.0 / oh)
    raw_d = math.sqrt(1.0 / od)
    raw_a = math.sqrt(1.0 / oa)
    total = raw_h + raw_d + raw_a
    return raw_h / total, raw_d / total, raw_a / total

# CORECTAT: Aici aparea SyntaxError din cauza parantezelor in versiunea anterioara.
def extract_1x2_odds(row):
    pinnacle = _valid_odds_triplet(row, *PINNACLE
