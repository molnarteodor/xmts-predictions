import os
import json
import math
import csv
import io
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

def today_str():
    if TZ:
        return datetime.now(TZ).strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")

app = Flask(__name__)
CORS(app)

CACHE_FILE = "matches_cache.json"
STATS_CACHE_FILE = "team_stats_cache.json"
MAX_ROWS = 1000

FIXTURES_CSV_URL = os.environ.get("FIXTURES_CSV_URL", "")
TARGET_STATS_FILES = ["E0.csv", "SP1.csv", "I1.csv", "D1.csv", "F1.csv", "E1.csv", "SP2.csv", "I2.csv", "D2.csv", "CL.csv", "EL.csv"]

CONFIDENCE_THRESHOLD = 0.50
LOW_RISK_THRESHOLD = 0.65

CORNERS_LINES = [8.5, 9.5, 10.5]
CARDS_LINES = [3.5, 4.5, 5.5]

PINNACLE_1X2 = ("PSH", "PSD", "PSA")
BOOKMAKER_1X2_COLUMNS = [
    ("B365H", "B365D", "B365A", "Bet365"),
    ("BWH", "BWD", "BWA", "Bwin"),
    ("IWH", "IWD", "IWA", "Interwetten"),
    ("WHH", "WHD", "WHA", "William Hill"),
    ("VCH", "VCD", "VCA", "BetVictor"),
]
OU25_PRIORITY = [("B365>2.5", "B365<2.5"), ("Avg>2.5", "Avg<2.5")]

LEAGUE_NAMES = {
    "E0": "Premier League (Anglia)", "E1": "Championship (Anglia)",
    "E2": "League One (Anglia)", "E3": "League Two (Anglia)", 
    "EC": "National League", "SC0": "Premiership (Scoția)", 
    "SC1": "Championship (Scoția)", "SP1": "La Liga (Spania)", 
    "SP2": "La Liga 2", "D1": "Bundesliga (Germania)", 
    "D2": "Bundesliga 2", "I1": "Serie A (Italia)", 
    "I2": "Serie B (Italia)", "F1": "Ligue 1 (Franța)", 
    "F2": "Ligue 2 (Franța)", "N1": "Eredivisie (Olanda)", 
    "B1": "Jupiler League (Belgia)", "P1": "Primeira Liga (Por)", 
    "T1": "Super Lig (Turcia)", "G1": "Super League (Grecia)",
    "CL": "UEFA Champions League", "EL": "UEFA Europa League"
}

DIXON_COLES_RHO_BASE = -0.08

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
    if " " in date_str and ":" in date_str:
        date_str = date_str.split(" ")[0]
        
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str

def parse_uk_time(date_str):
    date_str = (date_str or "").strip()
    if " " in date_str and ":" in date_str:
        try:
            dt = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
            return dt.strftime("%H:%M")
        except ValueError:
            pass
    return ""

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

def implied_probs_sq(oh, od, oa):
    raw_h = math.sqrt(1.0 / oh)
    raw_d = math.sqrt(1.0 / od)
    raw_a = math.sqrt(1.0 / oa)
    total = raw_h + raw_d + raw_a
    return raw_h / total, raw_d / total, raw_a / total

def extract_1x2_odds(row):
    pinnacle = _valid_odds_triplet(row, *PINNACLE_1X2)
    if pinnacle:
        ph, pd, pa = implied_probs_sq(*pinnacle)
        oh, od, oa = pinnacle
        return ph, pd, pa, "Pinnacle", oh, od, oa

    for h_key, d_key, a_key, _label in BOOKMAKER_1X2_COLUMNS:
        triplet = _valid_odds_triplet(row, h_key, d_key, a_key)
        if triplet:
            ph, pd, pa = implied_probs_sq(*triplet)
            oh, od, oa = triplet
            return ph, pd, pa, _label, oh, od, oa

    avg = _valid_odds_triplet(row, "AvgH", "AvgD", "AvgA")
    if avg:
        ph, pd, pa = implied_probs_sq(*avg)
        oh, od, oa = avg
        return ph, pd, pa, "Medie Globală", oh, od, oa

    return 0.38, 0.
