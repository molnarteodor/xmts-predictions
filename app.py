import os
import json
import math
import csv
import io
import requests
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Bucharest")
except Exception:
    TZ = None

def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d") if TZ else datetime.now().strftime("%Y-%m-%d")

app = Flask(__name__)
CORS(app)

CACHE_FILE = "matches_cache.json"
MAX_ROWS = 600

FIXTURES_CSV_URL = os.environ.get("FIXTURES_CSV_URL", "")

CONFIDENCE_THRESHOLD = 0.65
LOW_RISK_THRESHOLD = 0.75
FALLBACK_MIN_CONFIDENCE = 0.55

CHALLENGE_TARGET_ODD = 1.50

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
        if oh > 1.01 and od > 1.01 and oa > 1.01:
            return oh, od, oa
    except (ValueError, TypeError):
        pass
    return None

def implied_probs_square_root(oh, od, oa):
    raw_h, raw_d, raw_a = math.sqrt(1 / oh), math.sqrt(1 / od), math.sqrt(1 / oa)
    total = raw_h + raw_d + raw_a
    return raw_h / total, raw_d / total, raw_a / total

def extract_1x2_odds(row):
    pinnacle = _valid_odds_triplet(row, *PINNACLE_1X2)
    if pinnacle:
        ph, pd, pa = implied_probs_square_root(*pinnacle)
        return ph, pd, pa, "Pinnacle"

    probs = []
    for h_key, d_key, a_key, _label in BOOKMAKER_1X2_COLUMNS:
        triplet = _valid_odds_triplet(row, h_key, d_key, a_key)
        if triplet:
            probs.append(implied_probs_square_root(*triplet))

    if probs:
        n = len(probs)
        return sum(p[0] for
