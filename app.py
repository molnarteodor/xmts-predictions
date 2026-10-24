import os
from flask import Flask, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XMTS AI · Instant Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-dark: #0a0a0a; --card-bg: #151515; --card-border: #282828;
    --accent-cyan: #06b6d4; --accent-gold: #eab308; --accent-orange: #f97316;
    --text-main: #f8fafc; --text-muted: #94a3b8; --bar-green: #22c55e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
  body { background: var(--bg-dark); color: var(--text-main); padding: 10px; }
  .container { max-width: 600px; margin: 0 auto; }

  .header-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
  .sync-btn {
    background: #1f1f1f; border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 6px 10px; border-radius: 8px; font-size: 11px; font-weight: 700; cursor: pointer;
  }
  .sync-btn:hover { border-color: var(--accent-gold); color: #fff; }

  .tabs-wrapper { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 8px; scrollbar-width: none; }
  .tabs-wrapper::-webkit-scrollbar { display: none; }
  .tab-btn {
    background: #1c1c1c; border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 9px 13px; border-radius: 10px; font-weight: 700; white-space: nowrap; cursor: pointer; font-size: 12px;
  }
  .tab-btn.active { background: rgba(234, 179, 8, 0.16); border-color: var(--accent-gold); color: #fff; }

  .league-filter-bar { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 10px; scrollbar-width: none; }
  .league-filter-bar::-webkit-scrollbar { display: none; }
  .league-chip {
    background: #141414; border: 1px solid #2a2a2a; color: #cbd5e1;
    padding: 5px 10px; border-radius: 8px; font-size: 11px; font-weight: 600; white-space: nowrap; cursor: pointer;
  }
  .league-chip.active { background: var(--accent-gold); color: #000; border-color: var(--accent-gold); font-weight: 800; }

  .date-picker-bar { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 12px; scrollbar-width: none; scroll-behavior: smooth; }
  .date-picker-bar::-webkit-scrollbar { display: none; }
  .date-chip {
    background: #1f1f1f; border: 1px solid var(--card-border); color: var(--text-muted);
    padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: bold; white-space: nowrap; cursor: pointer;
  }
  .date-chip.active { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }

  .league-section { margin-bottom: 20px; }
  .league-section-header {
    display: flex; justify-content: space-between; align-items: center;
    background: linear-gradient(90deg, rgba(234,179,8,0.16) 0%, rgba(22,22,22,0.95) 100%);
    border-left: 4px solid var(--accent-gold); border-radius: 10px;
    padding: 10px 14px; margin-bottom: 10px; font-weight: 800; font-size: 13px; color: #fff;
  }
  .league-badge-count {
    font-size: 11px; color: var(--accent-gold); background: rgba(0,0,0,0.5);
    padding: 3px 8px; border-radius: 6px; font-weight: 700;
  }

  .glass-card {
    background: var(--card-bg); border: 1px solid var(--card-border);
    border-radius: 16px; padding: 15px; margin-bottom: 10px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.45);
  }

  .match-basic { display:flex; flex-direction:column; gap:8px; }
  .pred-row { display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.45); border-radius: 10px; padding: 10px; }
  .risk-tag { font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 6px; text-transform: uppercase; }
  .risk-Scăzut { background: rgba(16,185,129,0.2); color: #34d399; }
  .risk-Mediu { background: rgba(245,158,11,0.2); color: #fbbf24; }
  .risk-Ridicat { background: rgba(239,68,68,0.2); color: #fca5a5; }

  .btn-expand {
    width: 100%; background: #1f1f1f; border: 1px solid #eab308; color: #fff;
    padding: 9px; border-radius: 10px; font-weight: bold; cursor: pointer; margin-top: 8px; font-size: 12px;
  }

  .golden-panel { display: none; margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--card-border); }
  .golden-header { text-align: center; color: var(--accent-gold); font-size: 15px; font-weight: 800; margin-bottom: 12px; text-transform
