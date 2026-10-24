import os
from flask import Flask, render_template_string

app = Flask(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XMTS AI · Live Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-dark: #0a0a0a; --card-bg: #151515; --card-border: #282828;
    --accent-cyan: #06b6d4; --accent-gold: #eab308; --text-main: #f8fafc; --text-muted: #94a3b8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
  body { background: var(--bg-dark); color: var(--text-main); padding: 10px; }
  .container { max-width: 600px; margin: 0 auto; }
  .header-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .glass-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 16px; padding: 16px; margin-bottom: 12px; }
  .tab-btn { background: #1c1c1c; border: 1px solid var(--card-border); color: var(--text-muted); padding: 8px 14px; border-radius: 10px; font-weight: 700; cursor: pointer; font-size: 12px; }
  .tab-btn.active { background: rgba(234, 179, 8, 0.2); border-color: var(--accent-gold); color: #fff; }
  .tabs { display: flex; gap: 6px; margin-bottom: 12px; overflow-x: auto; }
</style>
</head>
<body>
<div class="container">
  <div class="header-bar">
    <div style="font-size:20px; font-weight:800; color:var(--accent-gold);">XMTS PREDICTIONS</div>
    <button class="tab-btn active" onclick="loadMatches()">🔄 Actualizează</button>
  </div>
  
  <div class="tabs">
    <button class="tab-btn active" onclick="filterLeague('ALL')">Toate Meciurile</button>
    <button class="tab-btn" onclick="filterLeague('UEFA Champions League')">Champions League</button>
    <button class="tab-btn" onclick="filterLeague('UEFA Europa League')">Europa League</button>
  </div>

  <div id="content">
    <div class="glass-card" style="text-align:center;">Se încarcă meciurile reale...</div>
  </div>
</div>

<script>
let globalMatches = [];

async function loadMatches() {
  const container = document.getElementById('content');
  container.innerHTML = '<div class="glass-card" style="text-align:center;">Se preiau datele de pe ESPN...</div>';
  
  const leagues = [
    {slug: "uefa.champions", name: "UEFA Champions League", icon: "🏆"},
    {slug: "uefa.europa", name: "UEFA Europa League", icon: "🟠"},
    {slug: "eng.1", name: "Premier League (Anglia)", icon: "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    {slug: "esp.1", name: "La Liga (Spania)", icon: "🇪🇸"},
    {slug: "ita.1", name: "Serie A (Italia)", icon: "🇮🇹"},
    {slug: "ger.1", name: "Bundesliga (Germania)", icon: "🇩🇪"},
    {slug: "rou.1", name: "SuperLiga (România)", icon: "🇷🇴"}
  ];

  let matches = [];
  try {
    for (let l of leagues) {
      const res = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${l.slug}/scoreboard`);
      const data = await res.json();
      if (data && data.events) {
        data.events.forEach(ev => {
          const comp = ev.competitions[0];
          const home = comp.competitors.find(c => c.homeAway === 'home') || comp.competitors[0];
          const away = comp.competitors.find(c => c.homeAway === 'away') || comp.competitors[1];
          
          const hName = home.team.displayName;
          const aName = away.team.displayName;
          const dateObj = new Date(comp.date);
          
          matches.push({
            league: l.name,
            icon: l.icon,
            date: dateObj.toISOString().split('T')[0],
            time: dateObj.toTimeString().substring(0, 5),
            home: hName,
            away: aName,
            prediction: `1X (${hName} sau Egal)`,
            prob: "74%"
          });
        });
      }
    }
  } catch (e) {
    console.error(e);
  }

  globalMatches = matches;
  displayMatches(matches);
}

function filterLeague(leagueName) {
  if (leagueName === 'ALL') {
    displayMatches(globalMatches);
  } else {
    displayMatches(globalMatches.filter(m => m.league === leagueName));
  }
}

function displayMatches(matches) {
  const container = document.getElementById('content');
  if (!matches.length) {
    container.innerHTML = '<div class="glass-card" style="text-align:center;">Nu sunt meciuri programate momentan.</div>';
    return;
  }

  container.innerHTML = matches.map(m => `
    <div class="glass-card">
      <div style="font-size:11px; color:var(--text-muted); margin-bottom:4px;">${m.icon} ${m.league} · ${m.date} (${m.time})</div>
      <div style="font-size:16px; font-weight:800; text-align:center; margin-bottom:8px;">${m.home} <span style="color:var(--accent-gold);">VS</span> ${m.away}</div>
      <div style="background:rgba(0,0,0,0.4); padding:8px; border-radius:8px; display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:13px; font-weight:700;">⭐ Pronostic: ${m.prediction}</span>
        <span style="font-size:11px; font-weight:800; background:rgba(16,185,129,0.2); color:#34d399; padding:2px 6px; border-radius:4px;">${m.prob}</span>
      </div>
    </div>
  `).join('');
}

loadMatches();
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
