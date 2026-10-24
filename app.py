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
<title>XMTS · Neural HUD</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #020408;
    --card-bg: rgba(10, 15, 28, 0.7);
    --card-border: rgba(0, 243, 255, 0.2);
    --card-border-hover: rgba(0, 243, 255, 0.6);
    --neon-cyan: #00f3ff;
    --neon-gold: #ffb703;
    --neon-green: #06d6a0;
    --neon-red: #ef476f;
    --text-main: #f8fafc;
    --text-muted: #64748b;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; -webkit-tap-highlight-color: transparent; }
  html, body { height: 100%; width: 100%; background: var(--bg); color: var(--text-main); overflow: hidden; }

  /* Cybernetic Background Glows */
  body::before {
    content: ""; position: fixed; top: -50%; left: -50%; width: 200%; height: 200%;
    background: radial-gradient(circle at 50% 30%, rgba(0,243,255,0.04) 0%, transparent 60%),
                radial-gradient(circle at 80% 80%, rgba(255,183,3,0.03) 0%, transparent 50%);
    z-index: -2; pointer-events: none;
  }
  body::after {
    content: ""; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.03), rgba(0, 255, 0, 0.01), rgba(0, 0, 255, 0.03));
    background-size: 100% 3px, 3px 100%; z-index: -1; pointer-events: none; opacity: 0.3;
  }

  .app-shell { display: flex; flex-direction: column; height: 100dvh; max-width: 520px; margin: 0 auto; position: relative; }

  /* FUTURISTIC TOP BAR */
  .top-hud {
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px 18px; background: rgba(2, 4, 8, 0.85);
    backdrop-filter: blur(20px); border-bottom: 1px solid var(--card-border); z-index: 20;
  }
  .hud-brand { display: flex; align-items: center; gap: 10px; }
  .hud-logo {
    width: 38px; height: 38px; border-radius: 12px;
    background: linear-gradient(135deg, var(--neon-cyan), var(--neon-gold));
    display: flex; align-items: center; justify-content: center;
    font-family: 'Orbitron', sans-serif; font-weight: 900; color: #020408; font-size: 16px;
    box-shadow: 0 0 15px rgba(0,243,255,0.4);
  }
  .hud-title { font-family: 'Orbitron', sans-serif; font-size: 14px; font-weight: 900; letter-spacing: 1px; color: #fff; }
  .hud-status { font-size: 10px; color: var(--neon-green); font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }

  .hud-bank {
    background: rgba(6, 214, 160, 0.1); border: 1px solid rgba(6, 214, 160, 0.4);
    color: var(--neon-green); padding: 8px 14px; border-radius: 14px; font-family: 'Orbitron', sans-serif;
    font-size: 13px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 6px;
    box-shadow: 0 0 15px rgba(6, 214, 160, 0.15); transition: 0.2s;
  }
  .hud-bank:active { transform: scale(0.95); }

  /* SUB-BARS */
  .sub-bars { background: rgba(5, 9, 18, 0.6); border-bottom: 1px solid var(--card-border); padding: 10px 14px 8px; backdrop-filter: blur(10px); }
  .h-scroll { display: flex; gap: 8px; overflow-x: auto; scrollbar-width: none; padding-bottom: 2px; }
  .h-scroll::-webkit-scrollbar { display: none; }
  
  .cyber-chip {
    background: rgba(15, 23, 42, 0.8); border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 7px 14px; border-radius: 10px; font-size: 11px; font-weight: 700;
    white-space: nowrap; cursor: pointer; transition: 0.2s;
  }
  .cyber-chip.active {
    background: var(--neon-cyan); color: #020408; border-color: var(--neon-cyan);
    font-weight: 800; box-shadow: 0 0 12px rgba(0, 243, 255, 0.4);
  }
  .cyber-chip-gold.active {
    background: var(--neon-gold); color: #020408; border-color: var(--neon-gold);
    box-shadow: 0 0 12px rgba(255, 183, 3, 0.4);
  }

  /* VIEWPORT */
  .viewport { flex: 1; overflow-y: auto; padding: 14px; padding-bottom: 90px; -webkit-overflow-scrolling: touch; }

  /* SECTION HEADER */
  .cyber-sec-head {
    display: flex; justify-content: space-between; align-items: center;
    background: linear-gradient(90deg, rgba(0,243,255,0.1), rgba(10,15,28,0.6));
    border-left: 3px solid var(--neon-cyan); border-radius: 8px;
    padding: 9px 14px; margin: 14px 0 10px; font-family: 'Orbitron', sans-serif;
    font-size: 11px; font-weight: 700; letter-spacing: 0.5px; color: var(--neon-cyan);
  }

  /* CYBER GLASS CARD */
  .cyber-card {
    background: var(--card-bg); border: 1px solid var(--card-border);
    backdrop-filter: blur(16px); border-radius: 18px; padding: 16px; margin-bottom: 12px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.6); transition: 0.25s; position: relative; overflow: hidden;
  }
  .cyber-card:hover { border-color: var(--card-border-hover); box-shadow: 0 10px 35px rgba(0,243,255,0.15); }
  
  .card-top { display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--text-muted); margin-bottom: 10px; }
  .status-badge { padding: 3px 9px; border-radius: 6px; font-weight: 800; font-size: 9px; font-family: 'Orbitron', sans-serif; letter-spacing: 0.5px; }
  .st-live { background: rgba(239,71,111,0.2); color: var(--neon-red); border: 1px solid var(--neon-red); box-shadow: 0 0 10px rgba(239,71,111,0.3); }
  .st-ft { background: rgba(6,214,160,0.2); color: var(--neon-green); border: 1px solid var(--neon-green); }
  .st-ns { background: rgba(255,255,255,0.05); color: #cbd5e1; border: 1px solid rgba(255,255,255,0.1); }

  .teams-container { display: flex; justify-content: space-between; align
