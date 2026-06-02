from __future__ import annotations

import json
import os
import smtplib
import sqlite3
import re
from contextlib import closing
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from flask import Flask, request, send_from_directory, session, render_template, redirect, url_for, flash
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "lostfound.db"
MAIL_LOG = BASE_DIR / "mail.log"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

from supabase import create_client, Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY) if SUPABASE_URL and SUPABASE_ANON_KEY else None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-for-production")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

# --- Template Filters ---
@app.template_filter('format_time')
def format_time(s):
    if not s: return ""
    try:
        dt = datetime.fromisoformat(s)
        return dt.strftime("%Y/%m/%d %H:%M")
    except ValueError:
        return s

@app.template_filter('from_json')
def from_json(s):
    try:
        return json.loads(s)
    except Exception:
        return []

# --- Database Seeding ---
SEED_EXTERNAL_ITEMS = [
    {
        "title": "AirPods Pro 耳機", "category": "電子產品", "location": "總圖 1F 服務台附近", "found_at": "2026-05-25T14:25",
        "description": "黑色充電盒，外殼上有白色貼紙，已送往服務台。", "source_name": "圖書館遺失版", "source_type": "library", "source_url": "",
    },
    {
        "title": "學生證", "category": "證件", "location": "管理學院 1F", "found_at": "2026-05-25T09:10",
        "description": "在管院一樓撿到學生證一張，可持證明至櫃台認領。", "source_name": "圖書館遺失版", "source_type": "library", "source_url": "",
    },
    {
        "title": "黑色皮夾", "category": "配件", "location": "小福 2F", "found_at": "2026-05-24T18:40",
        "description": "短夾內有悠遊卡，外觀有磨損。", "source_name": "FB交流版", "source_type": "facebook", "source_url": "https://facebook.com/groups/ntu.lostfound/posts/black-wallet",
    },
    {
        "title": "灰色雨傘", "category": "日用品", "location": "普通教學館", "found_at": "2026-05-23T17:20",
        "description": "灰色長傘，木頭握把，已交至駐警隊。", "source_name": "駐警隊", "source_type": "police", "source_url": "",
    },
    {
        "title": "深藍色外套", "category": "衣物", "location": "活大前草地", "found_at": "2026-05-22T20:15",
        "description": "外套袖口有白色條紋，天氣轉涼前可至貼文聯絡。", "source_name": "FB交流版", "source_type": "facebook", "source_url": "https://facebook.com/groups/ntu.lostfound/posts/jacket",
    },
]

def get_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def is_ntu_email(email: str) -> bool:
    return email.strip().lower().endswith("@ntu.edu.tw")

def normalize_words(text: str) -> set[str]:
    clean = text.lower()
    for token in ["：", "，", ",", ".", "(", ")", "[", "]", "{", "}", "<", ">"]:
        clean = clean.replace(token, " ")
    return {piece for piece in clean.split() if piece}

def similarity(report: sqlite3.Row, external: sqlite3.Row) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if report["category"] == external["category"]:
        score += 35
        reasons.append("類型一致")
    report_location = report["location"].lower()
    external_location = external["location"].lower()
    if report_location[:2] and (report_location[:2] in external_location or external_location[:2] in report_location):
        score += 20
        reasons.append("地點相近")
    report_time = datetime.fromisoformat(report["lost_at"])
    external_time = datetime.fromisoformat(external["found_at"])
    diff_hours = abs((external_time - report_time).total_seconds()) / 3600
    if diff_hours <= 6:
        score += 20
        reasons.append("時間高度接近")
    elif diff_hours <= 24:
        score += 10
        reasons.append("時間落在合理範圍")
    shared = normalize_words(report["title"] + " " + report["description"]).intersection(normalize_words(external["title"] + " " + external["description"]))
    if shared:
        score += min(25, len(shared) * 6)
        reasons.append("關鍵字重疊：" + "、".join(sorted(shared)[:4]))
    return min(score, 99), reasons

def send_email(recipient: str, subject: str, body: str) -> bool:
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_sender = os.environ.get("SMTP_SENDER", smtp_user or "noreply@ntu-lost-etl.local")
    if not smtp_host or not smtp_user or not smtp_password:
        with MAIL_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"[{now_iso()}] TO: {recipient}\nSUBJECT: {subject}\n{body}\n\n")
        return False
    message = EmailMessage()
    message["From"] = smtp_sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)
    return True

def init_db() -> None:
    with closing(get_db()) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, supabase_id TEXT UNIQUE, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS external_items (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, category TEXT NOT NULL, location TEXT NOT NULL, found_at TEXT NOT NULL, description TEXT NOT NULL, source_name TEXT NOT NULL, source_type TEXT NOT NULL, source_url TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS lost_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL, category TEXT NOT NULL, location TEXT NOT NULL, lost_at TEXT NOT NULL, description TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
            CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER NOT NULL, external_item_id INTEGER NOT NULL, score INTEGER NOT NULL, reasons_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(report_id, external_item_id), FOREIGN KEY(report_id) REFERENCES lost_reports(id), FOREIGN KEY(external_item_id) REFERENCES external_items(id));
            CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, subject TEXT NOT NULL, message TEXT NOT NULL, is_read INTEGER NOT NULL DEFAULT 0, delivery TEXT NOT NULL DEFAULT 'email', created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
        """)
        count = db.execute("SELECT COUNT(*) AS count FROM external_items").fetchone()["count"]
        if count == 0:
            db.executemany("INSERT INTO external_items (title, category, location, found_at, description, source_name, source_type, source_url) VALUES (:title, :category, :location, :found_at, :description, :source_name, :source_type, :source_url)", SEED_EXTERNAL_ITEMS)
        db.commit()

init_db()

# --- Auth Helpers ---
def require_login() -> int | None:
    return session.get("user_id")

def get_user(user_id: int):
    with closing(get_db()) as db:
        return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

def fetch_bundle(user_id: int) -> dict:
    with closing(get_db()) as db:
        external_items = [dict(row) for row in db.execute("SELECT * FROM external_items ORDER BY found_at DESC")]
        reports = [dict(row) for row in db.execute("SELECT * FROM lost_reports WHERE user_id = ? ORDER BY lost_at DESC", (user_id,))]
        matches = [dict(row) for row in db.execute("SELECT matches.id, matches.score, matches.reasons_json, matches.created_at, lost_reports.title AS report_title, external_items.title AS external_title, external_items.location AS external_location, external_items.source_name AS external_source_name, external_items.source_type AS external_source_type, external_items.source_url AS external_source_url FROM matches JOIN lost_reports ON lost_reports.id = matches.report_id JOIN external_items ON external_items.id = matches.external_item_id WHERE lost_reports.user_id = ? ORDER BY matches.score DESC, matches.created_at DESC", (user_id,))]
        notifications = [dict(row) for row in db.execute("SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC", (user_id,))]
    return {"external_items": external_items, "reports": reports, "matches": matches, "notifications": notifications}

def run_matching(report_id: int) -> None:
    with closing(get_db()) as db:
        report = db.execute("SELECT * FROM lost_reports WHERE id = ?", (report_id,)).fetchone()
        if not report: return
        user = db.execute("SELECT * FROM users WHERE id = ?", (report["user_id"],)).fetchone()
        external_items = db.execute("SELECT * FROM external_items").fetchall()
        new_matches = []
        for external in external_items:
            score, reasons = similarity(report, external)
            if score < 45: continue
            exists = db.execute("SELECT id FROM matches WHERE report_id = ? AND external_item_id = ?", (report["id"], external["id"])).fetchone()
            if exists: continue
            db.execute("INSERT INTO matches (report_id, external_item_id, score, reasons_json, created_at) VALUES (?, ?, ?, ?, ?)", (report["id"], external["id"], score, json.dumps(reasons, ensure_ascii=False), now_iso()))
            new_matches.append(external)
        db.commit()
    if new_matches:
        with closing(get_db()) as db:
            for item in new_matches:
                subject = f"新的遺失物媒合結果：{report['title']}"
                message = f"你的遺失通報「{report['title']}」出現新的可能配對：{item['title']}（來源：{item['source_name']}，地點：{item['location']}）。"
                db.execute("INSERT INTO notifications (user_id, subject, message, delivery, created_at) VALUES (?, ?, ?, 'email', ?)", (user["id"], subject, message, now_iso()))
                extra = f"\n原始來源連結：{item['source_url']}" if item["source_type"] == "facebook" else ""
                send_email(user["email"], subject, message + extra)
            db.commit()

# --- Routes ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not is_ntu_email(email):
            flash("請輸入正確的台大 Email 格式 (必須以 @ntu.edu.tw 結尾)", "error")
            return redirect(url_for("login"))
        if not supabase:
            flash("系統未設定 Supabase 憑證。", "error")
            return redirect(url_for("login"))
        try:
            supabase.auth.sign_in_with_otp({"email": email})
            session["auth_email"] = email
            session["auth_time"] = datetime.now().timestamp()
            flash("驗證碼已寄出，請檢查您的台大信箱。", "info")
            return redirect(url_for("verify"))
        except Exception as e:
            flash(f"發送驗證碼失敗: {e}", "error")
            return redirect(url_for("login"))
    
    # Clear stale auth state when visiting login page
    session.pop("auth_email", None)
    session.pop("auth_time", None)
    return render_template("auth.html", step="email")

@app.route("/verify", methods=["GET", "POST"])
def verify():
    email = session.get("auth_email")
    auth_time = session.get("auth_time")
    
    # Block if no email, or if the OTP request is older than 10 minutes (600 seconds)
    if not email or not auth_time or (datetime.now().timestamp() - auth_time > 600):
        session.pop("auth_email", None)
        session.pop("auth_time", None)
        flash("驗證已超時或無效，請重新輸入 Email。", "error")
        return redirect(url_for("login"))
        
    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        if not otp:
            flash("請輸入驗證碼。", "error")
            return redirect(url_for("verify"))
        try:
            res = supabase.auth.verify_otp({"email": email, "token": otp, "type": "email"})
            if res and res.user:
                sb_user = res.user
                with closing(get_db()) as db:
                    user = db.execute("SELECT id FROM users WHERE supabase_id = ? OR email = ?", (sb_user.id, email)).fetchone()
                    if not user:
                        name = email.split("@")[0]
                        db.execute("INSERT INTO users (supabase_id, name, email, created_at) VALUES (?, ?, ?, ?)", (sb_user.id, name, email, now_iso()))
                        db.commit()
                        user = db.execute("SELECT id FROM users WHERE supabase_id = ?", (sb_user.id,)).fetchone()
                    elif not user["supabase_id"]:
                        db.execute("UPDATE users SET supabase_id = ? WHERE id = ?", (sb_user.id, user["id"]))
                        db.commit()
                session["user_id"] = user["id"]
                session.pop("auth_email", None)
                session.pop("auth_time", None)
                session.permanent = True
                return redirect(url_for("dashboard"))
        except Exception as e:
            flash(f"驗證失敗: 驗證碼錯誤或已過期。", "error")
    return render_template("auth.html", step="otp", email=email)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def dashboard():
    user_id = require_login()
    if not user_id: return redirect(url_for("login"))
    user = get_user(user_id)
    bundle = fetch_bundle(user_id)
    summary = {}
    for item in bundle["external_items"]:
        summary[item["source_name"]] = summary.get(item["source_name"], 0) + 1
    return render_template("app.html", view="dashboard", user=user, summary=summary, **bundle)

@app.route("/sources")
def sources():
    user_id = require_login()
    if not user_id: return redirect(url_for("login"))
    user = get_user(user_id)
    bundle = fetch_bundle(user_id)
    q = request.args.get("q", "").strip().lower()
    source = request.args.get("source", "all")
    category = request.args.get("category", "all")
    filtered = []
    for item in bundle["external_items"]:
        text = f"{item['title']} {item['location']} {item['description']} {item['source_name']} {item['category']}".lower()
        if q and q not in text: continue
        if source != "all" and item["source_name"] != source: continue
        if category != "all" and item["category"] != category: continue
        filtered.append(item)
    bundle.pop("external_items", None)
    return render_template("app.html", view="sources", user=user, external_items=filtered, q=q, cur_source=source, cur_cat=category, **bundle)

@app.route("/report", methods=["GET", "POST"])
def report():
    user_id = require_login()
    if not user_id: return redirect(url_for("login"))
    user = get_user(user_id)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        location = request.form.get("location", "").strip()
        lost_at = request.form.get("lost_at", "").strip()
        description = request.form.get("description", "").strip()
        if all([title, category, location, lost_at, description]):
            with closing(get_db()) as db:
                db.execute("INSERT INTO lost_reports (user_id, title, category, location, lost_at, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, title, category, location, lost_at, description, now_iso()))
                db.commit()
                report_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            run_matching(report_id)
            flash("通報已成功送出！", "info")
            return redirect(url_for("matches"))
        else:
            flash("請完整填寫通報資訊。", "error")
    return render_template("app.html", view="report", user=user, **fetch_bundle(user_id))

@app.route("/matches")
def matches():
    user_id = require_login()
    if not user_id: return redirect(url_for("login"))
    return render_template("app.html", view="matches", user=get_user(user_id), **fetch_bundle(user_id))

@app.route("/notifications")
def notifications():
    user_id = require_login()
    if not user_id: return redirect(url_for("login"))
    return render_template("app.html", view="notifications", user=get_user(user_id), **fetch_bundle(user_id))

@app.route("/notifications/read-all", methods=["POST"])
def read_all_notifications():
    user_id = require_login()
    if user_id:
        with closing(get_db()) as db:
            db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
            db.commit()
    return redirect(url_for("notifications"))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
