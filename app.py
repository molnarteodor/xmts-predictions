import http.server
import json
import os
import random
import socketserver
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta

PORT = int(os.environ.get("PORT", 10000))
API_KEY = "86824b34c73a35048d8031810778337c"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# In-memory DB
USERS_DB = {
    "XMTS": {
        "password": "rusauto",
        "expires_at": None,
        "is_admin": True
    }
}

INVITE_CODES = {}
SESSIONS = {}
SAVED_TICKETS = {}

TOP_LEAGUES_MATCH = [
    "premier league", "la liga", "serie a", "bundesliga", "ligue 1", 
    "ucl", "champions league", "europa league", "conference league", 
    "superliga", "liga 1", "eredivisie", "primeira liga", "jupiler pro league", 
    "championship", "copa libertadores", "copa sudamericana", "mls"
]

EXCLUDED_KEYWORDS = [
    "u19", "u21", "u20", "u23", "reserve", "liga 3", "league 3", "3. liga", 
    "amateur", "women", "feminin", "next pro", "armenia", "bhutan", "regional"
]

def check_is_popular(league_name, country_name=""):
    full_name = f"{country_name} {league_name}".lower()
    if any(ex in full_name for ex in EXCLUDED_KEYWORDS):
        return False
    if "premier league" in full_name:
        return "england" in full_name or country_name.lower() == "england"
    return any(pop in full_name for pop in TOP_LEAGUES_MATCH)

def fetch_football_data(date_str):
    matches = []
    if API_KEY:
        try:
            url = f"https://v3.football.api-sports.io/fixtures?date={date_str}"
            req = urllib.request.Request(url, headers={
                'x-rapidapi-key': API_KEY,
                'x-rapidapi-host': 'v3.football.api-sports.io'
            })
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                fixtures = data.get("response", [])
                for f in fixtures:
                    league_name = f["league"]["name"]
                    country_name = f["league"].get("country", "")
                    home = f["teams"]["home"]["name"]
                    away = f["teams"]["away"]["name"]
                    status = f["fixture"]["status"]["short"]
                    goals_home = f["goals"]["home"]
                    goals_away = f["goals"]["away"]
                    score_str = f"{goals_home} - {goals_away}" if goals_home is not None else "VS"
                    is_popular = check_is_popular(league_name, country_name)
                    display_league = f"{country_name}: {league_name}" if country_name else league_name
                    matches.append({
                        "id": f["fixture"]["id"], "name": f"{home} vs {away}", "league": display_league,
                        "status": status, "score": score_str, "is_popular": is_popular,
                        "home_team": home, "away_team": away
                    })
        except Exception as e:
            print(f"Eroare API Football: {e}")

    if not matches:
        matches = [
            {"id": 101, "name": "Real Madrid vs Barcelona", "league": "Spain: La Liga", "status": "NS", "score": "VS", "is_popular": True},
            {"id": 102, "name": "Manchester City vs Liverpool", "league": "England: Premier League", "status": "NS", "score": "VS", "is_popular": True},
            {"id": 103, "name": "Inter vs AC Milan", "league": "Italy: Serie A", "status": "NS", "score": "VS", "is_popular": True},
            {"id": 104, "name": "Universitatea Craiova vs FCSB", "league": "Romania: SuperLiga", "status": "NS", "score": "VS", "is_popular": True}
        ]
    return matches

def generate_prediction(match):
    seed = sum(ord(c) for c in match["name"]) + int(match["id"])
    random.seed(seed)
    if match["status"] in ["FT", "AET", "PEN"]:
        return {"prediction": f"Scor Final: {match['score']}", "confidence": "Finalizat"}

    markets = [
        {"name": "Peste 1.5 Goluri", "weight": 92},
        {"name": "Peste 7.5 Cornere", "weight": 88},
        {"name": "Peste 2.5 Cartonașe", "weight": 90},
        {"name": "GG (Ambele Marchează)", "weight": 84},
        {"name": "Șansă Dublă 1X", "weight": 87}
    ]
    selected = random.choice(markets)
    conf = selected["weight"] + random.randint(-2, 3)
    return {"prediction": selected["name"], "confidence": f"{conf}%"}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ro">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XMTS AI Predictions</title>
    <style>
        body { font-family: sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 12px; }
        h1 { text-align: center; color: #38bdf8; font-size: 1.5rem; margin-bottom: 15px; }
        .container { max-width: 850px; margin: 0 auto; }
        .user-bar { display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 10px; border-radius: 8px; margin-bottom: 12px; }
        .auth-inputs { display: flex; gap: 6px; flex-wrap: wrap; }
        .auth-input { background: #0f172a; border: 1px solid #475569; color: white; padding: 6px; border-radius: 6px; font-size: 0.85rem; width: 95px; }
        .nav-tabs { display: flex; gap: 6px; margin-bottom: 15px; }
        .tab-btn { flex: 1; background: #1e293b; color: #94a3b8; border: 1px solid #334155; padding: 10px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 0.85rem; text-align: center; }
        .tab-btn.active { background: #0284c7; color: #fff; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 12px; margin-bottom: 10px; }
        .match-card { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 8px; }
        .btn-action { background: #334155; color: #38bdf8; border: 1px solid #0284c7; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: bold; }
        .btn-green { background: #16a34a; color: white; border: none; }
        .btn-red { background: #dc2626; color: white; border: none; }
        .admin-box { background: #1e293b; border: 1px solid #eab308; padding: 12px; border-radius: 8px; margin-bottom: 15px; }
        .badge { background: #0284c7; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>XMTS AI Predictions</h1>
        
        <div class="user-bar">
            <div id="user-display" style="font-weight:bold; color:#38bdf8;">Neconectat</div>
            <div id="auth-controls" class="auth-inputs">
                <input type="text" id="username" class="auth-input" placeholder="User">
                <input type="password" id="password" class="auth-input" placeholder="Parolă">
                <input type="text" id="invite_code" class="auth-input" placeholder="Cod">
                <button class="btn-action" onclick="login()">Login</button>
                <button class="btn-action btn-green" onclick="register()">Register</button>
            </div>
            <button id="logout-btn" class="btn-action btn-red" style="display:none;" onclick="logout()">Logout</button>
        </div>

        <div id="admin-panel" class="admin-box" style="display:none;">
            <h3 style="margin:0 0 10px 0; color:#eab308; font-size:1rem;">👑 Admin Panel (XMTS)</h3>
            <div style="display:flex; gap:8px; align-items:center;">
                <label style="font-size:0.85rem;">Valabilitate cont:</label>
                <select id="code-duration" class="auth-input" style="width:110px;">
                    <option value="7">7 Zile</option>
                    <option value="30">30 Zile</option>
                    <option value="90">3 Luni</option>
                    <option value="365">1 An</option>
                    <option value="0">Permanent</option>
                </select>
                <button class="btn-action btn-green" onclick="generateCode()">Generează Cod</button>
            </div>
            <div id="generated-code-result" style="margin-top:8px; font-weight:bold; color:#22c55e; font-size:0.85rem;"></div>
        </div>

        <div class="nav-tabs">
            <button class="tab-btn active" id="btn-matches" onclick="switchTab('matches')">Meciuri</button>
            <button class="tab-btn" id="btn-tickets" onclick="switchTab('tickets')">⭐ Bilete Top</button>
        </div>

        <div id="tab-content">
            <p style="text-align:center;">Se încarcă meciurile...</p>
        </div>
    </div>

    <script>
        let currentUser = null;
        let isAdmin = false;

        function checkAuth() {
            fetch('/api/me').then(r => r.json()).then(data => {
                if (data.user) {
                    currentUser = data.user;
                    isAdmin = data.is_admin;
                    let expText = data.expires_at ? ` (${data.expires_at})` : ' (Permanent)';
                    document.getElementById('user-display').innerText = '👋 ' + currentUser + expText;
                    document.getElementById('auth-controls').style.display = 'none';
                    document.getElementById('logout-btn').style.display = 'block';
                    document.getElementById('admin-panel').style.display = isAdmin ? 'block' : 'none';
                } else {
                    currentUser = null;
                    isAdmin = false;
                    document.getElementById('user-display').innerText = 'Neconectat';
                    document.getElementById('auth-controls').style.display = 'flex';
                    document.getElementById('logout-btn').style.display = 'none';
                    document.getElementById('admin-panel').style.display = 'none';
                }
            });
        }

        function login() {
            fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: document.getElementById('username').value, password: document.getElementById('password').value})
            }).then(r => r.json()).then(data => {
                if (data.success) checkAuth();
                else alert(data.message);
            });
        }

        function register() {
            fetch('/api/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    username: document.getElementById('username').value,
                    password: document.getElementById('password').value,
                    code: document.getElementById('invite_code').value
                })
            }).then(r => r.json()).then(data => {
                alert(data.message);
                if (data.success) login();
            });
        }

        function logout() {
            fetch('/api/logout', {method: 'POST'}).then(() => checkAuth());
        }

        function generateCode() {
            const duration = document.getElementById('code-duration').value;
            fetch('/api/admin/generate_code', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({duration_days: parseInt(duration)})
            }).then(r => r.json()).then(data => {
                if (data.success) {
                    document.getElementById('generated-code-result').innerText = `Cod: ${data.code} (${data.days === 0 ? 'Permanent' : data.days + ' Zile'})`;
                } else {
                    alert(data.message);
                }
            });
        }

        function loadMatches() {
            const container = document.getElementById('tab-content');
            container.innerHTML = '<p style="text-align:center;">Se încarcă meciurile zilei...</p>';
            
            fetch('/api/matches').then(r => r.json()).then(matches => {
                if (!matches.length) {
                    container.innerHTML = '<p style="text-align:center;">Nu există meciuri disponibile azi.</p>';
                    return;
                }
                let html = '';
                matches.forEach(m => {
                    html += `
                        <div class="card">
                            <div class="match-card">
                                <div>
                                    <span class="badge">${m.league}</span>
                                    <div style="font-weight:bold; font-size:1rem; margin-top:4px;">${m.name}</div>
                                </div>
                                <div style="text-align:right;">
                                    <span style="font-weight:bold; color:#e2e8f0;">${m.score}</span>
                                </div>
                            </div>
                            <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.85rem;">
                                <div>🎯 Predicție: <strong style="color:#38bdf8;">${m.pred.prediction}</strong> (${m.pred.confidence})</div>
                            </div>
                        </div>
                    `;
                });
                container.innerHTML = html;
            });
        }

        function switchTab(tab) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('btn-' + tab).classList.add('active');
            
            if (tab === 'matches') {
                loadMatches();
            } else if (tab === 'tickets') {
                document.getElementById('tab-content').innerHTML = '<div class="card"><p style="text-align:center;">Bilete Top generate pe baza meciurilor din ligile principale.</p></div>';
            }
        }

        checkAuth();
        switchTab('matches');
    </script>
</body>
</html>
"""

class SimpleHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def get_session_user(self):
        cookie_header = self.headers.get('Cookie')
        if cookie_header:
            cookies = urllib.parse.parse_qs(cookie_header.replace('; ', '&'))
            session_id = cookies.get('session_id', [None])[0]
            if session_id in SESSIONS:
                username = SESSIONS[session_id]
                user_info = USERS_DB.get(username)
                if user_info and user_info["expires_at"]:
                    if datetime.now() > user_info["expires_at"]:
                        del SESSIONS[session_id]
                        return None
                return username
        return None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

        elif parsed.path == "/api/me":
            user = self.get_session_user()
            user_data = USERS_DB.get(user) if user else None
            exp_str = user_data["expires_at"].strftime("%d-%m-%Y") if user_data and user_data["expires_at"] else None

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "user": user,
                "is_admin": user_data["is_admin"] if user_data else False,
                "expires_at": exp_str
            }).encode("utf-8"))

        elif parsed.path == "/api/matches":
            today_str = datetime.now().strftime("%Y-%m-%d")
            raw_matches = fetch_football_data(today_str)
            for m in raw_matches:
                m["pred"] = generate_prediction(m)

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(raw_matches).encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))

        if self.path == "/api/register":
            username = data.get("username", "").strip()
            password = data.get("password", "").strip()
            code = data.get("code", "").strip()

            if not username or not password or not code:
                res = {"success": False, "message": "Toate câmpurile sunt obligatorii!"}
            elif username in USERS_DB:
                res = {"success": False, "message": "Numele de utilizator există deja."}
            elif code not in INVITE_CODES or INVITE_CODES[code]["is_used"]:
                res = {"success": False, "message": "Cod invalid sau deja utilizat!"}
            else:
                code_info = INVITE_CODES[code]
                expires_at = datetime.now() + timedelta(days=code_info["duration_days"]) if code_info["duration_days"] > 0 else None
                USERS_DB[username] = {"password": password, "expires_at": expires_at, "is_admin": False}
                code_info["is_used"] = True
                res = {"success": True, "message": "Cont creat cu succes!"}

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif self.path == "/api/login":
            username = data.get("username", "").strip()
            password = data.get("password", "").strip()
            user_info = USERS_DB.get(username)

            if user_info and user_info["password"] == password:
                if user_info["expires_at"] and datetime.now() > user_info["expires_at"]:
                    res = {"success": False, "message": "Contul a expirat!"}
                else:
                    session_id = str(uuid.uuid4())
                    SESSIONS[session_id] = username
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Set-Cookie", f"session_id={session_id}; Path=/; HttpOnly")
                    self.end_headers()
                    self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
                    return
            else:
                res = {"success": False, "message": "Date incorecte."}

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif self.path == "/api/admin/generate_code":
            user = self.get_session_user()
            user_info = USERS_DB.get(user)
            if not user_info or not user_info["is_admin"]:
                self.send_response(403)
                self.end_headers()
                return

            duration_days = int(data.get("duration_days", 30))
            new_code = f"XMTS-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"
            INVITE_CODES[new_code] = {"duration_days": duration_days, "is_used": False}

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "code": new_code, "days": duration_days}).encode("utf-8"))

        elif self.path == "/api/logout":
            cookie_header = self.headers.get('Cookie')
            if cookie_header:
                cookies = urllib.parse.parse_qs(cookie_header.replace('; ', '&'))
                session_id = cookies.get('session_id', [None])[0]
                if session_id in SESSIONS:
                    del SESSIONS[session_id]

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Set-Cookie", "session_id=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), SimpleHTTPRequestHandler) as httpd:
        print(f"Server XMTS pe portul: {PORT}")
        httpd.serve_forever()
