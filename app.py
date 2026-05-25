from __future__ import annotations

import json
import os
import smtplib
import sqlite3
from contextlib import closing
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "lostfound.db"
MAIL_LOG = BASE_DIR / "mail.log"

app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "change-me-for-production")


SEED_EXTERNAL_ITEMS = [
    {
        "title": "AirPods Pro 耳機",
        "category": "電子產品",
        "location": "總圖 1F 服務台附近",
        "found_at": "2026-05-25T14:25",
        "description": "黑色充電盒，外殼上有白色貼紙，已送往服務台。",
        "source_name": "圖書館遺失版",
        "source_type": "library",
        "source_url": "",
    },
    {
        "title": "學生證",
        "category": "證件",
        "location": "管理學院 1F",
        "found_at": "2026-05-25T09:10",
        "description": "在管院一樓撿到學生證一張，可持證明至櫃台認領。",
        "source_name": "圖書館遺失版",
        "source_type": "library",
        "source_url": "",
    },
    {
        "title": "黑色皮夾",
        "category": "配件",
        "location": "小福 2F",
        "found_at": "2026-05-24T18:40",
        "description": "短夾內有悠遊卡，外觀有磨損。",
        "source_name": "FB交流版",
        "source_type": "facebook",
        "source_url": "https://facebook.com/groups/ntu.lostfound/posts/black-wallet",
    },
    {
        "title": "灰色雨傘",
        "category": "日用品",
        "location": "普通教學館",
        "found_at": "2026-05-23T17:20",
        "description": "灰色長傘，木頭握把，已交至駐警隊。",
        "source_name": "駐警隊",
        "source_type": "police",
        "source_url": "",
    },
    {
        "title": "深藍色外套",
        "category": "衣物",
        "location": "活大前草地",
        "found_at": "2026-05-22T20:15",
        "description": "外套袖口有白色條紋，天氣轉涼前可至貼文聯絡。",
        "source_name": "FB交流版",
        "source_type": "facebook",
        "source_url": "https://facebook.com/groups/ntu.lostfound/posts/jacket",
    },
    {
        "title": "白色保溫瓶",
        "category": "日用品",
        "location": "博雅教學館",
        "found_at": "2026-05-24T08:05",
        "description": "瓶身有藍色貼紙，已由駐警隊暫時保管。",
        "source_name": "駐警隊",
        "source_type": "police",
        "source_url": "",
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
    if report_location[:2] and (
        report_location[:2] in external_location or external_location[:2] in report_location
    ):
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

    shared = normalize_words(report["title"] + " " + report["description"]).intersection(
        normalize_words(external["title"] + " " + external["description"])
    )
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
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS external_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL,
              category TEXT NOT NULL,
              location TEXT NOT NULL,
              found_at TEXT NOT NULL,
              description TEXT NOT NULL,
              source_name TEXT NOT NULL,
              source_type TEXT NOT NULL,
              source_url TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS lost_reports (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              title TEXT NOT NULL,
              category TEXT NOT NULL,
              location TEXT NOT NULL,
              lost_at TEXT NOT NULL,
              description TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS matches (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              report_id INTEGER NOT NULL,
              external_item_id INTEGER NOT NULL,
              score INTEGER NOT NULL,
              reasons_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE(report_id, external_item_id),
              FOREIGN KEY(report_id) REFERENCES lost_reports(id),
              FOREIGN KEY(external_item_id) REFERENCES external_items(id)
            );

            CREATE TABLE IF NOT EXISTS notifications (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              subject TEXT NOT NULL,
              message TEXT NOT NULL,
              is_read INTEGER NOT NULL DEFAULT 0,
              delivery TEXT NOT NULL DEFAULT 'email',
              created_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )
        count = db.execute("SELECT COUNT(*) AS count FROM external_items").fetchone()["count"]
        if count == 0:
            db.executemany(
                """
                INSERT INTO external_items
                (title, category, location, found_at, description, source_name, source_type, source_url)
                VALUES (:title, :category, :location, :found_at, :description, :source_name, :source_type, :source_url)
                """,
                SEED_EXTERNAL_ITEMS,
            )

        notification_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(notifications)").fetchall()
        }
        if "delivery" not in notification_columns:
            db.execute(
                "ALTER TABLE notifications ADD COLUMN delivery TEXT NOT NULL DEFAULT 'email'"
            )
        db.commit()


def require_login() -> int:
    user_id = session.get("user_id")
    if not user_id:
        raise ValueError("請先登入。")
    return int(user_id)


def fetch_bundle(user_id: int) -> dict:
    with closing(get_db()) as db:
        external_items = [dict(row) for row in db.execute("SELECT * FROM external_items ORDER BY found_at DESC")]
        reports = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM lost_reports WHERE user_id = ? ORDER BY lost_at DESC",
                (user_id,),
            )
        ]
        matches = [
            dict(row)
            for row in db.execute(
                """
                SELECT
                  matches.id,
                  matches.score,
                  matches.reasons_json,
                  matches.created_at,
                  lost_reports.title AS report_title,
                  external_items.title AS external_title,
                  external_items.location AS external_location,
                  external_items.source_name AS external_source_name,
                  external_items.source_type AS external_source_type,
                  external_items.source_url AS external_source_url
                FROM matches
                JOIN lost_reports ON lost_reports.id = matches.report_id
                JOIN external_items ON external_items.id = matches.external_item_id
                WHERE lost_reports.user_id = ?
                ORDER BY matches.score DESC, matches.created_at DESC
                """,
                (user_id,),
            )
        ]
        notifications = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
        ]

    return {
        "external_items": external_items,
        "reports": reports,
        "matches": matches,
        "notifications": notifications,
    }


def create_notifications(user: sqlite3.Row, report: sqlite3.Row, external_items: list[sqlite3.Row]) -> None:
    if not external_items:
        return

    with closing(get_db()) as db:
        for item in external_items:
            subject = f"新的遺失物媒合結果：{report['title']}"
            message = (
                f"你的遺失通報「{report['title']}」出現新的可能配對："
                f"{item['title']}（來源：{item['source_name']}，地點：{item['location']}）。"
            )
            db.execute(
                """
                INSERT INTO notifications (user_id, subject, message, delivery, created_at)
                VALUES (?, ?, ?, 'email', ?)
                """,
                (user["id"], subject, message, now_iso()),
            )
            extra = f"\n原始來源連結：{item['source_url']}" if item["source_type"] == "facebook" else ""
            send_email(user["email"], subject, message + extra)
        db.commit()


def run_matching(report_id: int) -> None:
    with closing(get_db()) as db:
        report = db.execute("SELECT * FROM lost_reports WHERE id = ?", (report_id,)).fetchone()
        if report is None:
            return
        user = db.execute("SELECT * FROM users WHERE id = ?", (report["user_id"],)).fetchone()
        external_items = db.execute("SELECT * FROM external_items").fetchall()
        new_matches: list[sqlite3.Row] = []

        for external in external_items:
            score, reasons = similarity(report, external)
            if score < 45:
                continue
            exists = db.execute(
                "SELECT id FROM matches WHERE report_id = ? AND external_item_id = ?",
                (report["id"], external["id"]),
            ).fetchone()
            if exists:
                continue

            db.execute(
                """
                INSERT INTO matches (report_id, external_item_id, score, reasons_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (report["id"], external["id"], score, json.dumps(reasons, ensure_ascii=False), now_iso()),
            )
            new_matches.append(external)

        db.commit()

    create_notifications(user, report, new_matches)


@app.route("/")
def root():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(BASE_DIR, filename)


@app.route("/api/register", methods=["POST"])
def register():
    payload = request.get_json(force=True)
    name = payload.get("name", "").strip()
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    if not name or not email or not password:
        return jsonify({"error": "請完整填寫註冊資訊。"}), 400
    if not is_ntu_email(email):
        return jsonify({"error": "請使用台大學生 Email（@ntu.edu.tw）註冊。"}), 400
    if len(password) < 8:
        return jsonify({"error": "密碼至少需要 8 碼。"}), 400

    with closing(get_db()) as db:
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return jsonify({"error": "這個 Email 已經註冊過。"}), 400
        db.execute(
            """
            INSERT INTO users (name, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, email, generate_password_hash(password, method="pbkdf2:sha256"), now_iso()),
        )
        db.commit()
        user = db.execute("SELECT id, name, email FROM users WHERE email = ?", (email,)).fetchone()

    session["user_id"] = user["id"]
    return jsonify({"user": dict(user)})


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(force=True)
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    with closing(get_db()) as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "帳號或密碼錯誤。"}), 401
        session["user_id"] = user["id"]
        public_user = {"id": user["id"], "name": user["name"], "email": user["email"]}
    return jsonify({"user": public_user})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/session")
def get_session():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "尚未登入。"}), 401
    with closing(get_db()) as db:
        user = db.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            session.clear()
            return jsonify({"error": "尚未登入。"}), 401
    return jsonify({"user": dict(user)})


@app.route("/api/bootstrap")
def bootstrap():
    try:
        user_id = require_login()
    except ValueError as error:
        return jsonify({"error": str(error)}), 401
    return jsonify(fetch_bundle(user_id))


@app.route("/api/report-lost", methods=["POST"])
def report_lost():
    try:
        user_id = require_login()
    except ValueError as error:
        return jsonify({"error": str(error)}), 401

    payload = request.get_json(force=True)
    title = payload.get("title", "").strip()
    category = payload.get("category", "").strip()
    location = payload.get("location", "").strip()
    lost_at = payload.get("lost_at", "").strip()
    description = payload.get("description", "").strip()

    if not all([title, category, location, lost_at, description]):
        return jsonify({"error": "請完整填寫遺失通報資訊。"}), 400

    with closing(get_db()) as db:
        db.execute(
            """
            INSERT INTO lost_reports (user_id, title, category, location, lost_at, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, title, category, location, lost_at, description, now_iso()),
        )
        db.commit()
        report_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    run_matching(report_id)
    return jsonify(fetch_bundle(user_id))


@app.route("/api/notifications/read-all", methods=["POST"])
def read_all_notifications():
    try:
        user_id = require_login()
    except ValueError as error:
        return jsonify({"error": str(error)}), 401

    with closing(get_db()) as db:
        db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
        db.commit()
    return jsonify({"notifications": fetch_bundle(user_id)["notifications"]})


init_db()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
