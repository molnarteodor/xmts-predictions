import os
import json
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

PROJECT_FILE = "jack_500_state.json"

DEFAULT_PROJECT = {
    "initial_bankroll": 500.0,
    "target_bankroll": 800.0,
    "bankroll": 500.0,
    "bets": []
}

def load_project():
    try:
        if os.path.exists(PROJECT_FILE):
            with open(PROJECT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return dict(DEFAULT_PROJECT)

def save_project(data):
    try:
        with open(PROJECT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

@app.route("/api/project", methods=["GET", "POST"])
def api_project():
    if request.method == "POST":
        body = request.get_json(silent=True)
        if body and "bankroll" in body and "bets" in body:
            save_project(body)
            return jsonify(body)
    return jsonify(load_project())

HTML_PAGE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>JACK 500 · Cyber HUD</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #030508;
    --surface: rgba(13, 18, 30, 0.75);
    --surface2: rgba(22, 30, 48, 0.85);
    --border: rgba(6, 182, 212, 0.18);
    --border-glow: rgba(6, 182, 212, 0.45);
    --gold: #f59e0b;
    --gold-glow: rgba(245, 158, 11, 0.35);
    --cyan: #06b6d4;
    --cyan-glow: rgba(6, 182, 212, 0.35);
    --green: #10b981;
    --red: #ef4444;
    --text: #f1f5f9;
    --muted: #64748b;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; -webkit-tap-highlight-color: transparent; }
  html, body { height: 100%; width: 100%; background: var(--bg); color: var(--text); overflow: hidden; }
  
  /* Cyber Background Grid Effect */
  body::before {
    content: ""; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background-image: linear-gradient(rgba(6,182,212,0.03) 1px, transparent 1px),
                      linear-gradient(90deg, rgba(6,182,212,0.03) 1px, transparent 1px);
    background-size: 24px 24px; z-index: -1; pointer-events: none;
  }

  .app-shell { display: flex; flex-direction: column; height: 100dvh; max-width: 520px; margin: 0 auto; background: var(--bg); position: relative; }

  /* TOP HUD BAR */
  .top-bar {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 16px; background: rgba(3, 5, 8, 0.88);
    backdrop-filter: blur(16px); border-bottom: 1px solid var(--border); z-index: 20;
  }
  .brand { display: flex; align-items: center; gap: 10px; }
  .brand-logo {
    width: 36px; height: 36px; border-radius: 10px;
    background: linear-gradient(135deg, var(--cyan), var(--gold));
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; color: #000; font-size: 16px; box-shadow: 0 0 14px var(--cyan-glow);
  }
  .brand-title { font-size: 15px; font-weight: 800; letter-spacing: 0.5px; background: linear-gradient(90deg, #fff, var(--cyan)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .brand-sub { font-size: 10px; color: var(--green); font-weight: 700; display: block; text-shadow: 0 0 8px rgba(16,185,129,0.4); }
  
  .bank-pill {
    background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.4);
    color: #34d399; padding: 7px 13px; border-radius: 12px; font-size: 13px; font-weight: 800;
    cursor: pointer; display: flex; align-items: center; gap: 6px; box-shadow: 0 0 12px rgba(16,185,129,0.2);
    transition: 0.2s;
  }
  .bank-pill:active { transform: scale(0.96); }

  /* SUB-BARS */
  .sub-bars { background: rgba(13, 18, 30, 0.6); border-bottom: 1px solid var(--border); padding: 8px 12px 6px; backdrop-filter: blur(8px); }
  .h-scroll { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; padding-bottom: 4px; }
  .h-scroll::-webkit-scrollbar { display: none; }
  .chip {
    background: var(--surface2); border: 1px solid var(--border); color: var(--muted);
    padding: 6px 12px; border-radius: 10px; font-size: 11px; font-weight: 700;
    white-space: nowrap; cursor: pointer; transition: 0.2s;
  }
  .chip.active { background: var(--cyan); color: #000; border-color: var(--cyan); font-weight: 800; box-shadow: 0 0 10px var(--cyan-glow); }
  .chip-gold.active { background: var(--gold); color: #000; border-color: var(--gold); box-shadow: 0 0 10px var(--gold-glow); }

  /* SCROLL VIEWPORT */
  .viewport { flex: 1; overflow-y: auto; padding: 12px; padding-bottom: 88px; -webkit-overflow-scrolling: touch; }

  .sec-head {
    display: flex; justify-content: space-between; align-items: center;
    background: linear-gradient(90deg, rgba(6,182,212,0.12), rgba(13,18,30,0.8));
    border-left: 3px solid var(--cyan); border-radius: 10px;
    padding: 8px 12px; margin: 12px 0 8px; font-size: 12px; font-weight: 800;
  }

  /* GLASS CARD */
  .card {
    background: var(--surface); border: 1px solid var(--border);
    backdrop-filter: blur(12px); border-radius: 16px; padding: 14px; margin-bottom: 10px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5); transition: 0.2s;
  }
  .card:hover { border-color: var(--border-glow); }
  .card-top { display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--muted
