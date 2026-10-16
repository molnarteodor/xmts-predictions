import os
import re
import json
import math
import csv
import io
import hashlib
import urllib.request
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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
MAX_ROWS_PER_FILE = 800

FIXTURES_CSV_URL = os.environ.get("FIXTURES_CSV_URL", "")
TARGET_STATS_FILES = [
    "E0.csv", "SP1.csv", "I1.csv", "D1.csv", "F1.csv",
    "E1.csv", "SP2.csv", "I2.csv", "D2.csv", "N1.csv", "P1.csv",
    "CL.csv", "EL.csv"
]

CONFIDENCE_THRESHOLD = 0.52
LOW_RISK_THRESHOLD = 0.64

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
OU25_PRIORITY = [("B365>2.5", "B365<2.5"), ("P>2.5", "P<2.5"), ("Avg>2.5", "Avg<2.5")]

LEAGUE_NAMES = {
    "E0": "Premier League", "E1": "Championship",
    "E2": "League One", "E3": "League Two",
    "EC": "National League", "SC0": "Premiership (Scoția)",
    "SC1": "Championship (Scoția)", "SP1": "La Liga",
    "SP2": "La Liga 2", "D1": "Bundesliga",
    "D2": "Bundesliga 2", "I1": "Serie A",
    "I2": "Serie B", "F1": "Ligue 1",
    "F2": "Ligue 2", "N1": "Eredivisie",
    "B1":
