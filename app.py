import os
import json
import psycopg2
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    return None

def init_db():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS jack_project (
                    id SERIAL PRIMARY KEY,
                    data TEXT NOT NULL
                );
            """)
            cur.execute("SELECT COUNT(*) FROM jack_project;")
            if cur.fetchone()[0] == 0:
                default_data = {
                    "initial_bankroll": 500.0,
                    "target_bankroll": 800.0,
                    "bankroll": 500.0,
                    "bets": []
                }
                cur.execute("INSERT INTO jack_project (data) VALUES (%s);", [json.dumps(default_data)])
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print("Eroare la init_db:", e)

try:
    init_db()
except Exception as e:
    print("Nu s-a putut initializa baza de date:", e)

@app.route("/api/project", methods=["GET", "POST"])
def api_project():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "No database connection"}), 500

    try:
        cur = conn.cursor()
        if request.method == "POST":
            body = request.get_json(silent=True)
            if body and "bankroll" in body and "bets" in body:
                cur.execute("DELETE FROM jack_project;")
                cur.execute("INSERT INTO jack_project (data) VALUES (%s);", [json.dumps(body)])
                conn.commit()
                cur.close()
                conn.close()
                return jsonify(body)
        
        cur.execute("SELECT data FROM jack_project ORDER BY id DESC LIMIT 1;")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return jsonify(json.loads(row[0]))
    except Exception as e:
        print("Eroare în rutele API:", e)
        if conn:
            conn.close()

    return jsonify({
        "initial_bankroll": 500.0,
        "target_bankroll": 800.0,
        "bankroll": 500.0,
        "bets": []
    })

# Citim interfața direct din fișierul extern index.html
@app.route("/")
def index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "Eroare: Fisierul index.html lipseste!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
