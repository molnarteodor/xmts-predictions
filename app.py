import os
import json
import psycopg2
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

# Preluare URL baza de date din setările de pe Render sau fallback pe fișier local
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    return None

def init_db():
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jack_project (
                id SERIAL PRIMARY KEY,
                data JSONB NOT NULL
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

# Inițializăm baza de date la pornire
try:
    init_db()
except Exception as e:
    print("Eroare la pornirea bazei de date:", e)

def load_project():
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT data FROM jack_project ORDER BY id DESC LIMIT 1;")
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                return row[0]
        except Exception:
            pass
    return {
        "initial_bankroll": 500.0,
        "target_bankroll": 800.0,
        "bankroll": 500.0,
        "bets": []
    }

def save_project(data):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM jack_project;")
            cur.execute("INSERT INTO jack_project (data) VALUES (%s);", [json.dumps(data)])
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print("Eroare la salvarea în baza de date:", e)

@app.route("/api/project", methods=["GET", "POST"])
def api_project():
    if request.method == "POST":
        body = request.get_json(silent=True)
        if body and "bankroll" in body and "bets" in body:
            save_project(body)
            return jsonify(body)
    return jsonify(load_project())
