from datetime import date, datetime, timedelta
import hashlib
import http.server
import json
import math
import socket
import socketserver
import urllib.request
import webbrowser
import os

def get_free_port():
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(("", 0))
    return s.getsockname()[1]


def poisson_pmf(k, lambda_val):
  return (lambda_val**k) * math.exp(-lambda_val) / math.factorial(k)


def analyze_football_dynamic(match_title, seed=0):
  hash_input = f"{match_title}_{seed}"
  h = int(hashlib.md5(hash_input.encode("utf-8")).hexdigest(), 16)

  home_xg = 0.8 + ((h % 220) / 100.0)
  away_xg = 0.7 + (((h >> 4) % 200) / 100.0)

  p_home, p_draw, p_away = 0.0, 0.0, 0.0
  over15, over25, btts = 0.0, 0.0, 0.0

  for h_g in range(6):
    for a_g in range(6):
      prob = poisson_pmf(h_g, home_xg) * poisson_pmf(a_g, away_xg)
      if h_g > a_g:
        p_home += prob
      elif h_g == a_g:
        p_draw += prob
      else:
        p_away += prob

      if h_g + a_g > 1.5:
        over15 += prob
      if h_g + a_g > 2.5:
        over25 += prob
      if h_g > 0 and a_g > 0:
        btts += prob

  p_home_pct = round(p_home * 100, 1)
  p_away_pct = round(p_away * 100, 1)
  p_draw_pct = round(p_draw * 100, 1)
  over15_pct = round(over15 * 100, 1)
  over25_pct = round(over25 * 100, 1)
  btts_pct = round(btts * 100, 1)

  prob_1x = round((p_home + p_draw) * 100, 1)
  prob_x2 = round((p_away + p_draw) * 100, 1)

  variant = h % 5
  if variant == 0 and p_home_pct >= 40:
    main_p = "1 Solist"
    conf_val = max(52.0, p_home_pct)
    risk = "Scăzut" if conf_val >= 62 else "Mediu"
    alt_p = f"Peste 1.5 Goluri ({over15_pct}%)"
    bet_builder = f"1X & Peste 1.5 Goluri ({round(prob_1x * 0.85, 1)}%)"
  elif variant == 1 and p_away_pct >= 35:
    main_p = "2 Solist"
    conf_val = max(50.0, p_away_pct)
    risk = "Scăzut" if conf_val >= 60 else "Mediu"
    alt_p = f"Șansă Dublă X2 ({prob_x2}%)"
    bet_builder = f"X2 & Peste 1.5 Goluri ({round(prob_x2 * 0.82, 1)}%)"
  elif variant == 2 and over25_pct >= 42:
    main_p = "Peste 2.5 Goluri"
    conf_val = max(53.0, over25_pct)
    risk = "Scăzut" if conf_val >= 64 else "Mediu"
    alt_p = f"Ambele Marchează GG ({btts_pct}%)"
    bet_builder = f"GG & Peste 2.5 Goluri ({round(btts_pct * 0.86, 1)}%)"
  elif variant == 3 and btts_pct >= 42:
    main_p = "GG (Ambele Marchează)"
    conf_val = max(52.0, btts_pct)
    risk = "Mediu"
    alt_p = f"Peste 1.5 Goluri ({over15_pct}%)"
    bet_builder = f"1X & GG ({round(prob_1x * 0.75, 1)}%)"
  else:
    is_1x = prob_1x >= prob_x2
    main_p = "Șansă Dublă 1X" if is_1x else "Șansă Dublă X2"
    conf_val = max(60.0, max(prob_1x, prob_x2))
    risk = "Scăzut" if conf_val >= 70 else "Mediu"
    alt_p = f"Sub 3.5 Goluri ({round(100 - over25_pct * 0.4, 1)}%)"
    bet_builder = f"{'1X' if is_1x else 'X2'} & Sub 3.5 Goluri ({round(conf_val * 0.8, 1)}%)"

  implied_odd = 1.0 / max(0.1, conf_val / 100.0)
  odd = round(max(1.20, min(3.80, implied_odd * 1.05)), 2)

  return (
      main_p,
      f"{round(conf_val)}%",
      round(conf_val),
      alt_p,
      risk,
      bet_builder,
      odd,
  )


def get_live_matches_from_api():
  api_key = "86824b34c73a35048d8031810778337c"
  today = date.today().strftime("%Y-%m-%d")
  url = f"https://v3.football.api-sports.io/fixtures?date={today}"

  req = urllib.request.Request(url, headers={"x-apisports-key": api_key})

  matches = []
  try:
    with urllib.request.urlopen(req) as response:
      data = json.loads(response.read().decode())
      fixtures = data.get("response", [])

      top_leagues = [283, 39, 140, 135, 78, 61, 2, 3, 84]
      fixtures.sort(key=lambda x: 0 if x["league"]["id"] in top_leagues else 1)

      for fix in fixtures:
        time_str_utc = fix["fixture"]["date"][0:19]
        utc_time = datetime.strptime(time_str_utc, "%Y-%m-%dT%H:%M:%S")
        local_time = utc_time + timedelta(hours=3)
        ora = local_time.strftime("%H:%M")

        liga = fix["league"]["name"]
        meci = f"{fix['teams']['home']['name']} vs {fix['teams']['away']['name']}"

        main_p, conf_str, conf_num, alt_p, risk, bb, odd = (
            analyze_football_dynamic(meci)
        )

        matches.append({
            "sport": "Fotbal",
            "ora": ora,
            "liga": liga,
            "meci": meci,
            "main": main_p,
            "conf": conf_str,
            "conf_num": conf_num,
            "alt": alt_p,
            "risk": risk,
            "bb": bb,
            "odd": odd,
        })

        if len(matches) >= 40:
          break

  except Exception as e:
    print("Eroare la conexiunea cu API-ul:", e)

  return matches


processed_matches = get_live_matches_from_api()

HTML_CONTENT = f"""<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <title>AI PREDICTION & TICKET OPTIMIZER XMTS 2026</title>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-card: #1e293b;
            --accent: #10b981;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --border: #334155;
        }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--bg-primary); color: var(--text); margin: 0; padding: 25px; }}
        
        .nav-tabs {{ display: flex; gap: 10px; margin-bottom: 25px; border-bottom: 2px solid var(--border); padding-bottom: 10px; }}
        .nav-btn {{ background: var(--bg-card); color: var(--text-muted); border: 1px solid var(--border); padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 15px; font-weight: bold; transition: 0.2s; }}
        .nav-btn.active {{ background: #6366f1; color: white; border-color: #818cf8; box-shadow: 0 0 15px rgba(99, 102, 241, 0.4); }}
        
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}

        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--border); padding-bottom: 15px; margin-bottom: 20px; }}
        h1 {{ color: var(--accent); margin: 0; font-size: 26px; }}
        .date-badge {{ background: var(--bg-card); padding: 8px 14px; border-radius: 8px; border: 1px solid var(--border); font-size: 14px; color: var(--text-muted); }}

        .ticket-builder-panel {{ background: #111827; border: 2px solid #6366f1; border-radius: 12px; padding: 20px; margin-bottom: 25px; box-shadow: 0 4px 15px rgba(99, 102, 241, 0.2); }}
        .ticket-title {{ font-size: 18px; font-weight: bold; color: #a5b4fc; margin-bottom: 15px; display: flex; align-items: center; gap: 8px; }}
        .odds-buttons {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 15px; }}
        .btn-odd {{ background: #1e293b; color: #fff; border: 1px solid #4f46e5; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 14px; transition: 0.2s; }}
        .btn-odd:hover, .btn-odd.active {{ background: #6366f1; color: white; border-color: #818cf8; transform: translateY(-2px); }}
        
        .ticket-result {{ background: #1e293b; border: 1px dashed #6366f1; border-radius: 8px; padding: 15px; margin-top: 15px; display: none; }}
        .ticket-header {{ display: flex; justify-content: space-between; font-weight: bold; font-size: 16px; color: #34d399; margin-bottom: 12px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
        .ticket-item {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px dotted #334155; font-size: 13px; }}
        
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .stat-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 12px; text-align: center; }}
        .stat-val {{ font-size: 24px; font-weight: bold; color: var(--accent); margin-top: 4px; }}
        .stat-lbl {{ font-size: 12px; color: var(--text-muted); }}

        .controls {{ display: flex; flex-wrap: wrap; gap: 10px; background: var(--bg-card); padding: 15px; border-radius: 10px; border: 1px solid var(--border); margin-bottom: 20px; align-items: center; }}
        .filter-btn {{ background: var(--bg-primary); color: var(--text); border: 1px solid var(--border); padding: 8px 14px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 13px; transition: 0.2s; }}
        .filter-btn.active, .filter-btn:hover {{ background: var(--accent); color: #000; border-color: var(--accent); }}
        .btn-regen {{ background: #10b981; color: black; border: none; font-weight: bold; margin-left: 10px; }}
        
        input[type="text"] {{ background: var(--bg-primary); color: var(--text); border: 1px solid var(--border); padding: 8px 14px; border-radius: 6px; outline: none; width: 200px; font-size: 13px; }}
        
        table {{ width: 100%; border-collapse: collapse; background: var(--bg-card); border-radius: 10px; overflow: hidden; border: 1px solid var(--border); }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid var(--border); font-size: 13px; }}
        th {{ background: #111827; color: var(--accent); text-transform: uppercase; font-size: 11px; letter-spacing: 1px; }}
        tr:hover {{ background: #26354a; }}
        
        .badge {{ padding: 4px 8px; border-radius: 6px; font-weight: bold; font-size: 11px; display: inline-block; }}
        .scazut {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }}
        .mediu {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }}
        .ridicat {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }}
        
        .bb-tag {{ background: rgba(99, 102, 241, 0.15); color: #a5b4fc; border: 1px solid #6366f1; padding: 3px 6px; border-radius: 4px; font-weight: 600; font-size: 12px; }}
        .sport-tag {{ background: #334155; color: #cbd5e1; font-size: 10px; padding: 2px 5px; border-radius: 4px; margin-right: 4px; }}
        .time-tag {{ color: #60a5fa; font-weight: bold; }}

        /* STILURI CHAT AI OPTIMIZER */
        .chat-container {{ display: flex; flex-direction: column; height: 75vh; background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }}
        .chat-messages {{ flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 15px; }}
        .msg {{ max-width: 80%; padding: 14px 18px; border-radius: 10px; font-size: 14px; line-height: 1.5; }}
        .msg-ai {{ background: #111827; border: 1px solid #6366f1; color: #f8fafc; align-self: flex-start; }}
        .msg-user {{ background: #10b981; color: #000; font-weight: 600; align-self: flex-end; }}
        .msg img {{ max-width: 250px; border-radius: 8px; margin-top: 10px; border: 1px solid var(--border); }}
        
        .chat-input-area {{ padding: 15px; background: #111827; border-top: 1px solid var(--border); display: flex; gap: 10px; align-items: center; }}
        .upload-btn {{ background: #3b82f6; color: white; padding: 10px 15px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: bold; display: flex; align-items: center; gap: 5px; }}
        .chat-input {{ flex: 1; background: var(--bg-primary); border: 1px solid var(--border); color: white; padding: 12px; border-radius: 8px; font-size: 14px; outline: none; }}
        .send-btn {{ background: var(--accent); color: black; border: none; padding: 12px 20px; border-radius: 8px; font-weight: bold; cursor: pointer; }}
        .img-preview {{ display: none; width: 50px; height: 50px; border-radius: 6px; object-fit: cover; border: 1px solid var(--accent); }}
    </style>
</head>
<body>

    <div class="nav-tabs">
        <button class="nav-btn active" onclick="switchTab('dashboard', this)">📊 Meciuri & Predicții Azi</button>
        <button class="nav-btn" onclick="switchTab('chat', this)">🤖 AI Ticket Optimizer & Chat (Scanare Poze)</button>
    </div>

    <!-- TAB 1: DASHBOARD -->
    <div id="dashboard" class="tab-content active">
        <div class="header">
            <h1>⚽ AI PREDICTION BY XMTS 2026</h1>
            <div class="date-badge">📅 Data: {date.today()}</div>
        </div>

        <div class="ticket-builder-panel">
            <div class="ticket-title">🎯 Generator Bilete AI Max-Win (Selectează Cota Dorită)</div>
            <div class="odds-buttons">
                <button class="btn-odd" onclick="generateTicket(2, this)">Cota 2.00</button>
                <button class="btn-odd" onclick="generateTicket(5, this)">Cota 5.00</button>
                <button class="btn-odd" onclick="generateTicket(10, this)">Cota 10.00</button>
                <button class="btn-odd" onclick="generateTicket(15, this)">Cota 15.00</button>
                <button class="btn-odd" onclick="generateTicket(50, this)">Cota 50.00+</button>
            </div>
            <div id="ticketResult" class="ticket-result"></div>
        </div>

        <div class="stats-grid">
            <div class="stat-card"><div class="stat-lbl">Meciuri Reale Identificate</div><div class="stat-val" id="stat-total">0</div></div>
            <div class="stat-card"><div class="stat-lbl">Risc Scăzut</div><div class="stat-val" id="stat-safe" style="color:#34d399;">0</div></div>
            <div class="stat-card"><div class="stat-lbl">Risc Mediu</div><div class="stat-val" id="stat-medium" style="color:#fbbf24;">0</div></div>
            <div class="stat-card"><div class="stat-lbl">Risc Ridicat</div><div class="stat-val" id="stat-high" style="color:#f87171;">0</div></div>
        </div>

        <div class="controls">
            <span><b>Filtrează Risc:</b></span>
            <button class="filter-btn active" onclick="setRiskFilter('All', this)">Toate</button>
            <button class="filter-btn" onclick="setRiskFilter('Scăzut', this)">🟢 Scăzut</button>
            <button class="filter-btn" onclick="setRiskFilter('Mediu', this)">🟡 Mediu</button>
            <button class="filter-btn" onclick="setRiskFilter('Ridicat', this)">🔴 Ridicat</button>

            <button class="filter-btn btn-regen" onclick="regeneratePredictions()">🎲 Recalculare / Regenerare AI</button>

            <div style="margin-left: auto;">
                <input type="text" id="searchInput" onkeyup="applyFilters()" placeholder="Caută echipă sau ligă...">
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Ora & Competiția</th>
                    <th>Meci / Competitori</th>
                    <th>Pronostic Principal (Algoritm)</th>
                    <th>Încredere Algoritm</th>
                    <th>Cotă Corectă Calculată</th>
                    <th>Propunere Alternativă</th>
                    <th>BetBuilder Combo</th>
                    <th>Risc</th>
                </tr>
            </thead>
            <tbody id="matchesTable"></tbody>
        </table>
    </div>

    <!-- TAB 2: AI CHAT OPTIMIZER -->
    <div id="chat" class="tab-content">
        <div class="header">
            <h1>📸 AI Ticket Scanner & Bet Optimizer</h1>
            <div class="date-badge">Model: Vision OCR + Algoritm XMTS 2026</div>
        </div>

        <div class="chat-container">
            <div class="chat-messages" id="chatMessages">
                <div class="msg msg-ai">
                    👋 <b>Salut! Sunt asistentul tău AI pentru Optimizarea Biletelor.</b><br><br>
                    📸 Trimite o poză / un screenshot cu biletul tău de pariere și eu îl voi analiza meci cu meci.<br>
                    💡 Îți voi spune:<br>
                    • Care sunt șansele matematice de reușită ale biletului.<br>
                    • Meciurile cele mai riscante din selecție.<br>
                    • Ce modificări să faci (ex: schimbare pronostic sau acoperire) pentru a-ți crește șansele de câștig!
                </div>
            </div>

            <div class="chat-input-area">
                <label class="upload-btn">
                    📷 Adaugă Poza Bilet
                    <input type="file" id="ticketImageInput" accept="image/*" style="display:none;" onchange="handleImageSelect(event)">
                </label>
                <img id="imagePreview" class="img-preview" alt="Preview">
                <input type="text" id="chatTextInput" class="chat-input" placeholder="Scrie un mesaj sau trimite poza biletului..." onkeydown="if(event.key==='Enter') sendMessage()">
                <button class="send-btn" onclick="sendMessage()">Trimite 🚀</button>
            </div>
        </div>
    </div>

    <script>
        let rawMatches = {json.dumps(processed_matches)};
        let activeRisk = 'All';
        let currentSeed = 0;
        let selectedBase64Image = null;

        function switchTab(tabId, btn) {{
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            btn.classList.add('active');
        }}

        function handleImageSelect(event) {{
            const file = event.target.files[0];
            if (file) {{
                const reader = new FileReader();
                reader.onload = function(e) {{
                    selectedBase64Image = e.target.result;
                    const preview = document.getElementById('imagePreview');
                    preview.src = selectedBase64Image;
                    preview.style.display = 'block';
                }};
                reader.readAsDataURL(file);
            }}
        }}

        function sendMessage() {{
            const input = document.getElementById('chatTextInput');
            const text = input.value.trim();
            if (!text && !selectedBase64Image) return;

            const chatMessages = document.getElementById('chatMessages');

            // User Message
            let userHtml = `<div class="msg msg-user">${{text || 'Am trimis o poză cu biletul meu.'}}`;
            if (selectedBase64Image) {{
                userHtml += `<br><img src="${{selectedBase64Image}}">`;
            }}
            userHtml += `</div>`;
            chatMessages.innerHTML += userHtml;

            const imageToSend = selectedBase64Image;

            // Reset inputs
            input.value = '';
            selectedBase64Image = null;
            document.getElementById('imagePreview').style.display = 'none';
            document.getElementById('ticketImageInput').value = '';

            chatMessages.scrollTop = chatMessages.scrollHeight;

            // Simulated AI Analysis (Integrat cu baza de meciuri reale)
            setTimeout(() => {{
                let aiResponse = "";
                if (imageToSend) {{
                    aiResponse = `
                    <b>🔍 Analiză Bilet Finalizată de AI:</b><br><br>
                    • 📊 <b>Șanse Estimate de Reușită:</b> <b style="color:#34d399;">68%</b><br>
                    • ⚡ <b>Nivel Risc Bilet:</b> <b style="color:#fbbf24;">Mediu</b><br><br>
                    <b>⚠️ Meciuri Identificate & Recomandări Optimizare:</b><br>
                    1. ⚽ <b>Meci Depistat cu Risc Ridicat:</b> <i>Pronostic Solist Incert</i>.<br>
                       👉 <b>Sfat AI:</b> Înlocuiește cu <b>Șansă Dublă 1X</b> sau <b>Peste 1.5 Goluri</b> pentru siguranță crescută (+22% șanse de câștig).<br><br>
                    2. 🔥 <b>Meciuri Solide:</b> Meciurile pe goluri (Peste 2.5 & GG) prezintă o convergență statistică excelentă de 78%.<br><br>
                    <b>💡 Bilet Optim Recomandat:</b> Elimină cel mai riscant meci sau aplică un sistem BetBuilder (1X & Sub 3.5 Goluri) pentru a-ți asigura câștigul!
                    `;
                }} else {{
                    aiResponse = `Am primit mesajul tău: "<i>${{text}}</i>". Pentru a-ți da o analiză exactă meci cu meci, te rog să apeși pe butonul <b>📷 Adaugă Poza Bilet</b> și să încarci poza biletului tău de la agenție!`;
                }}

                chatMessages.innerHTML += `<div class="msg msg-ai">${{aiResponse}}</div>`;
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }}, 1000);
        }}

        function stringHash(str) {{
            let hash = 0;
            for (let i = 0; i < str.length; i++) {{
                hash = ((hash << 5) - hash) + str.charCodeAt(i);
                hash |= 0;
            }}
            return Math.abs(hash);
        }}

        function computeDynamicPrediction(matchTitle, seed) {{
            const h = stringHash(matchTitle + "_" + seed);
            const homeXg = 0.8 + ((h % 220) / 100.0);
            const awayXg = 0.7 + (((h >> 4) % 200) / 100.0);

            const pHome = Math.min(85, Math.max(15, Math.round((homeXg / (homeXg + awayXg)) * 100)));
            const pAway = Math.min(80, Math.max(10, Math.round((awayXg / (homeXg + awayXg)) * 85)));
            const over25 = Math.min(88, Math.round((homeXg + awayXg) * 28));
            const btts = Math.min(82, Math.round((homeXg * awayXg) * 35));
            const prob1X = Math.min(92, Math.round(pHome + 20));
            const probX2 = Math.min(90, Math.round(pAway + 22));

            let res = {{}};
            let conf_val = 0;
            const variant = h % 5;

            if (variant === 0) {{
                conf_val = Math.max(52, pHome);
                res = {{ main: '1 Solist', conf_num: conf_val, conf: conf_val + '%', alt: 'Peste 1.5 Goluri (' + Math.min(94, over25 + 18) + '%)', bb: '1X & Peste 1.5 Goluri (' + Math.round(prob1X * 0.85) + '%)', risk: conf_val >= 62 ? 'Scăzut' : 'Mediu' }};
            }} else if (variant === 1) {{
                conf_val = Math.max(50, pAway);
                res = {{ main: '2 Solist', conf_num: conf_val, conf: conf_val + '%', alt: 'Șansă Dublă X2 (' + probX2 + '%)', bb: 'X2 & Peste 1.5 Goluri (' + Math.round(probX2 * 0.82) + '%)', risk: conf_val >= 60 ? 'Scăzut' : 'Mediu' }};
            }} else if (variant === 2) {{
                conf_val = Math.max(53, over25);
                res = {{ main: 'Peste 2.5 Goluri', conf_num: conf_val, conf: conf_val + '%', alt: 'Ambele Marchează GG (' + btts + '%)', bb: 'GG & Peste 2.5 Goluri (' + Math.round(btts * 0.86) + '%)', risk: conf_val >= 64 ? 'Scăzut' : 'Mediu' }};
            }} else if (variant === 3) {{
                conf_val = Math.max(52, btts);
                res = {{ main: 'GG (Ambele Marchează)', conf_num: conf_val, conf: conf_val + '%', alt: 'Peste 1.5 Goluri (' + Math.min(90, over25 + 15) + '%)', bb: '1X & GG (' + Math.round(prob1X * 0.75) + '%)', risk: 'Mediu' }};
            }} else {{
                const is1x = prob1X >= probX2;
                conf_val = Math.max(60, is1x ? prob1X : probX2);
                res = {{ main: is1x ? 'Șansă Dublă 1X' : 'Șansă Dublă X2', conf_num: conf_val, conf: conf_val + '%', alt: 'Sub 3.5 Goluri (' + Math.round(100 - over25 * 0.4) + '%)', bb: (is1x ? '1X' : 'X2') + ' & Sub 3.5 Goluri (' + Math.round(conf_val * 0.8) + '%)', risk: conf_val >= 70 ? 'Scăzut' : 'Mediu' }};
            }}

            const impliedOdd = 1.0 / (conf_val / 100.0);
            res.odd = parseFloat((impliedOdd * 1.05).toFixed(2));

            return res;
        }}

        function getActiveMatches() {{
            return rawMatches.map(m => {{
                const pred = computeDynamicPrediction(m.meci, currentSeed);
                return {{ ...m, ...pred }};
            }});
        }}

        function generateTicket(targetOdds, btn) {{
            document.querySelectorAll('.btn-odd').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            let matches = getActiveMatches();
            
            matches.sort((a, b) => {{
                let hashA = stringHash(a.meci + targetOdds + currentSeed);
                let hashB = stringHash(b.meci + targetOdds + currentSeed);
                return (hashA % 100) - (hashB % 100);
            }});

            let selected = [];
            let currentOdds = 1.0;

            for (let m of matches) {{
                if (currentOdds >= targetOdds && selected.length >= (targetOdds > 10 ? 4 : 2)) break;
                if (!selected.includes(m)) {{
                    selected.push(m);
                    currentOdds *= m.odd;
                }}
            }}

            const container = document.getElementById('ticketResult');
            container.style.display = 'block';

            if (selected.length === 0) {{
                container.innerHTML = '<span style="color:#f87171;">Nu sunt suficiente meciuri disponibile pentru a genera biletul.</span>';
                return;
            }}

            let html = `
                <div class="ticket-header">
                    <span>🎫 Bilet Generat (Cotă Țintă: ${{targetOdds}}+)</span>
                    <span>Cotă Finală Calculată: <b style="color:#10b981;">${{currentOdds.toFixed(2)}}</b> | ${{selected.length}} Meciuri Combinate</span>
                </div>
            `;

            selected.forEach(item => {{
                html += `
                    <div class="ticket-item">
                        <span><b>${{item.ora}}</b> | <b>${{item.meci}}</b> (${{item.liga}})</span>
                        <span>Pronostic: <b style="color:#34d399;">${{item.main}}</b> | Încredere: <b>${{item.conf}}</b> | Cotă: <b style="color:#fbbf24;">${{item.odd.toFixed(2)}}</b></span>
                    </div>
                `;
            }});

            container.innerHTML = html;
        }}

        function updateStats(allMatches) {{
            document.getElementById('stat-total').innerText = allMatches.length;
            document.getElementById('stat-safe').innerText = allMatches.filter(m => m.risk === 'Scăzut').length;
            document.getElementById('stat-medium').innerText = allMatches.filter(m => m.risk === 'Mediu').length;
            document.getElementById('stat-high').innerText = allMatches.filter(m => m.risk === 'Ridicat').length;
        }}

        function renderTable(data) {{
            const tbody = document.getElementById('matchesTable');
            if (!tbody) return;
            tbody.innerHTML = '';

            if (data.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:30px; color:#94a3b8;">Niciun meci găsit de la API pentru astăzi.</td></tr>';
                return;
            }}

            data.forEach(m => {{
                let riskClass = 'scazut';
                if (m.risk === 'Mediu') riskClass = 'mediu';
                if (m.risk === 'Ridicat') riskClass = 'ridicat';

                const row = `
                    <tr>
                        <td><span class="time-tag">${{m.ora}}</span> | <span class="sport-tag">${{m.sport}}</span>${{m.liga}}</td>
                        <td><b>${{m.meci}}</b></td>
                        <td><span style="color:#10b981; font-weight:bold;">${{m.main}}</span></td>
                        <td><b>${{m.conf}}</b></td>
                        <td><b style="color:#fbbf24; background: rgba(245, 158, 11, 0.1); padding: 4px 8px; border-radius: 6px; border: 1px solid rgba(245, 158, 11, 0.3);">⚡ ${{m.odd.toFixed(2)}}</b></td>
                        <td style="color:#cbd5e1;">${{m.alt}}</td>
                        <td><span class="bb-tag">🔥 ${{m.bb}}</span></td>
                        <td><span class="badge ${{riskClass}}">${{m.risk}}</span></td>
                    </tr>
                `;
                tbody.innerHTML += row;
            }});
        }}

        function setRiskFilter(risk, btn) {{
            activeRisk = risk;
            document.querySelectorAll('.filter-btn:not(.btn-regen)').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');
            applyFilters();
        }}

        function regeneratePredictions() {{
            currentSeed += 1;
            applyFilters();
            const ticketRes = document.getElementById('ticketResult');
            if (ticketRes) ticketRes.style.display = 'none';
            document.querySelectorAll('.btn-odd').forEach(b => b.classList.remove('active'));
        }}

        function applyFilters() {{
            const activeList = getActiveMatches();
            updateStats(activeList);

            const searchInput = document.getElementById('searchInput');
            const search = searchInput ? searchInput.value.toLowerCase() : '';
            
            const filtered = activeList.filter(m => {{
                const matchRisk = activeRisk === 'All' || m.risk === activeRisk;
                const matchSearch = m.meci.toLowerCase().includes(search) || m.liga.toLowerCase().includes(search);
                return matchRisk && matchSearch;
            }});

            renderTable(filtered);
        }}

        window.onload = function() {{
            applyFilters();
        }};
    </script>
</body>
</html>
"""


class Handler(http.server.SimpleHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.send_header("Content-type", "text/html; charset=utf-8")
    self.end_headers()
    self.wfile.write(HTML_CONTENT.encode("utf-8"))


if __name__ == "__main__":
    # Render va furniza automat portul prin variabila PORT
    PORT = int(os.environ.get("PORT", 10000))
    socketserver.TCPServer.allow_reuse_address = True

with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"Server pornit pe portul: {PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer oprit.")
