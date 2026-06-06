from __future__ import annotations

import json
import os
import smtplib
from contextlib import closing
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from flask import Flask, request, session, render_template, redirect, url_for, flash
from dotenv import load_dotenv

import matching
import bridge

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
MAIL_LOG = BASE_DIR / "mail.log"

DATABASE_URL = os.environ.get("DATABASE_URL")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

from supabase import create_client, Client
supabase: Client | None = create_client(SUPABASE_URL, SUPABASE_ANON_KEY) if SUPABASE_URL and SUPABASE_ANON_KEY else None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-for-production")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

EMBED_BATCH = 32  # 一次送進 Jina 的招領物筆數


# --- Template Filters ---
@app.template_filter('format_time')
def format_time(s):
    if not s: return ""
    if isinstance(s, datetime):
        return s.strftime("%Y/%m/%d %H:%M")
    try:
        return datetime.fromisoformat(str(s)).strftime("%Y/%m/%d %H:%M")
    except ValueError:
        return s

@app.template_filter('from_json')
def from_json(s):
    try:
        return json.loads(s)
    except Exception:
        return []


# --- Database ---
def get_db() -> psycopg.Connection:
    """開一條 Supabase Postgres 連線（dict row）。

    prepare_threshold=None 是為了配合 Supabase 的 transaction pooler（pgbouncer），
    避免 prepared statement 在連線間衝突。
    """
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL 未設定")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, prepare_threshold=None)

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def is_ntu_email(email: str) -> bool:
    return email.strip().lower().endswith("@ntu.edu.tw")

# 應用自有資料表（找到的招領物 lost_items 由爬蟲 / SQLAlchemy 那側維護）。
_SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS users (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        supabase_id text UNIQUE,
        name text NOT NULL,
        email text NOT NULL UNIQUE,
        created_at text NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS lost_reports (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        user_id bigint NOT NULL REFERENCES users(id),
        title text NOT NULL,
        category text,
        location text,
        lost_at text NOT NULL,
        description text,
        embedding text,
        created_at text NOT NULL
    )""",
    # lost_item_id 對應 lost_items.id（integer），型別需相符。
    """CREATE TABLE IF NOT EXISTS matches (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        report_id bigint NOT NULL REFERENCES lost_reports(id),
        lost_item_id integer NOT NULL REFERENCES lost_items(id),
        score int NOT NULL,
        reasons_json text NOT NULL,
        created_at text NOT NULL,
        UNIQUE(report_id, lost_item_id)
    )""",
    """CREATE TABLE IF NOT EXISTS notifications (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        user_id bigint NOT NULL REFERENCES users(id),
        subject text NOT NULL,
        message text NOT NULL,
        is_read int NOT NULL DEFAULT 0,
        delivery text NOT NULL DEFAULT 'email',
        created_at text NOT NULL
    )""",
    # 招領物的語意向量（JSON 陣列存 text；資料量小，於 Python 端算 cosine）。
    "ALTER TABLE lost_items ADD COLUMN IF NOT EXISTS embedding text",
]

def init_db() -> None:
    with closing(get_db()) as db:
        for statement in _SCHEMA_STATEMENTS:
            db.execute(statement)
        db.commit()

init_db()


# --- Email ---
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
    # 465 = implicit SSL (SMTPS)；587/其他 = STARTTLS。
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as smtp:
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(message)
    return True


# --- Auth Helpers ---
def require_login() -> int | None:
    return session.get("user_id")

def get_user(user_id: int):
    with closing(get_db()) as db:
        return db.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


# --- Found items (lost_items) <-> 前端 / 媒合用的 external 形狀 ---
def _external_from_lost_item(row: dict) -> dict:
    """把一筆 lost_items 列映射成前端 / 媒合用的 dict，並帶上 id。"""
    external = bridge.lost_item_to_external(row)
    external["id"] = row["id"]
    return external

def fetch_bundle(user_id: int | None) -> dict:
    with closing(get_db()) as db:
        item_rows = db.execute("SELECT * FROM lost_items ORDER BY found_date DESC").fetchall()
        external_items = [_external_from_lost_item(r) for r in item_rows]
        if not user_id:
            external_items = [e for e in external_items if e["source_type"] != "facebook"]
            return {"external_items": external_items, "reports": [], "matches": [], "notifications": []}

        reports = [dict(r) for r in db.execute("SELECT * FROM lost_reports WHERE user_id = %s ORDER BY lost_at DESC", (user_id,))]
        match_rows = db.execute(
            """SELECT m.id, m.score, m.reasons_json, m.created_at, r.title AS report_title,
                      li.source_system, li.original_id, li.found_date, li.location,
                      li.description, li.category, li.storage_place
               FROM matches m
               JOIN lost_reports r ON r.id = m.report_id
               JOIN lost_items li ON li.id = m.lost_item_id
               WHERE r.user_id = %s
               ORDER BY m.score DESC, m.created_at DESC""",
            (user_id,),
        ).fetchall()
        matches = []
        for mr in match_rows:
            ext = bridge.lost_item_to_external(mr)
            matches.append({
                "id": mr["id"], "score": mr["score"], "reasons_json": mr["reasons_json"], "created_at": mr["created_at"],
                "report_title": mr["report_title"],
                "external_title": ext["title"], "external_location": ext["location"],
                "external_source_name": ext["source_name"], "external_source_type": ext["source_type"],
                "external_source_url": ext["source_url"],
            })
        notifications = [dict(r) for r in db.execute("SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC", (user_id,))]
    return {"external_items": external_items, "reports": reports, "matches": matches, "notifications": notifications}


# --- Embeddings (JSON text 欄位 + Python cosine) ---
def _ensure_report_embedding(db, report) -> list[float] | None:
    if report.get("embedding"):
        try:
            return json.loads(report["embedding"])
        except (TypeError, ValueError):
            pass
    if not matching.embeddings_enabled():
        return None
    try:
        vec = matching.embed_text(matching.item_text(report))
        db.execute("UPDATE lost_reports SET embedding = %s WHERE id = %s", (json.dumps(vec), report["id"]))
        db.commit()
        return vec
    except Exception:
        app.logger.exception("產生通報 embedding 失敗，改用關鍵字比對")
        return None

def _ensure_item_embedding(db, item_row, external) -> list[float] | None:
    if item_row.get("embedding"):
        try:
            return json.loads(item_row["embedding"])
        except (TypeError, ValueError):
            pass
    if not matching.embeddings_enabled():
        return None
    try:
        vec = matching.embed_text(matching.item_text(external))
        db.execute("UPDATE lost_items SET embedding = %s WHERE id = %s", (json.dumps(vec), item_row["id"]))
        db.commit()
        return vec
    except Exception:
        app.logger.exception("產生招領物 embedding 失敗，改用關鍵字比對")
        return None

def _ensure_all_item_embeddings(db) -> None:
    """為尚未產生向量的招領物批次補算 embedding。"""
    rows = db.execute("SELECT * FROM lost_items WHERE embedding IS NULL OR embedding = ''").fetchall()
    if not rows:
        return
    for start in range(0, len(rows), EMBED_BATCH):
        chunk = rows[start:start + EMBED_BATCH]
        texts = [matching.item_text(_external_from_lost_item(r)) for r in chunk]
        vectors = matching.embed_texts(texts)
        for row, vec in zip(chunk, vectors):
            db.execute("UPDATE lost_items SET embedding = %s WHERE id = %s", (json.dumps(vec), row["id"]))
    db.commit()

def _item_cosines(db, report_embedding: list[float]) -> dict[int, float]:
    result: dict[int, float] = {}
    for row in db.execute("SELECT id, embedding FROM lost_items WHERE embedding IS NOT NULL AND embedding <> ''"):
        try:
            vec = json.loads(row["embedding"])
        except (TypeError, ValueError):
            continue
        result[row["id"]] = matching.cosine(report_embedding, vec)
    return result


# --- Matching ---
def _try_create_match(db, report, external, cos: float | None) -> bool:
    score, reasons = matching.blended_score(report, external, cos)
    if score < matching.MATCH_THRESHOLD:
        return False
    exists = db.execute("SELECT id FROM matches WHERE report_id = %s AND lost_item_id = %s", (report["id"], external["id"])).fetchone()
    if exists:
        return False
    db.execute(
        "INSERT INTO matches (report_id, lost_item_id, score, reasons_json, created_at) VALUES (%s, %s, %s, %s, %s)",
        (report["id"], external["id"], score, json.dumps(reasons, ensure_ascii=False), now_iso()),
    )
    db.commit()
    return True

def _notify_match(db, user, report, external) -> None:
    subject = f"新的遺失物媒合結果：{report['title']}"
    message = f"你的遺失通報「{report['title']}」出現新的可能配對：{external['title']}（來源：{external['source_name']}，地點：{external['location']}）。"
    db.execute("INSERT INTO notifications (user_id, subject, message, delivery, created_at) VALUES (%s, %s, %s, 'email', %s)", (user["id"], subject, message, now_iso()))
    db.commit()
    extra = f"\n原始來源連結：{external['source_url']}" if external["source_type"] == "facebook" else ""
    send_email(user["email"], subject, message + extra)

def run_matching(report_id: int) -> None:
    """新通報 → 比對所有招領物（lost_items），對新配對發出通知。"""
    with closing(get_db()) as db:
        report = db.execute("SELECT * FROM lost_reports WHERE id = %s", (report_id,)).fetchone()
        if not report: return
        user = db.execute("SELECT * FROM users WHERE id = %s", (report["user_id"],)).fetchone()
        report_embedding = _ensure_report_embedding(db, report)
        cosine_by_item = None
        if report_embedding is not None:
            try:
                _ensure_all_item_embeddings(db)
                cosine_by_item = _item_cosines(db, report_embedding)
            except Exception:
                app.logger.exception("語意媒合失敗，改用關鍵字比對")
        for item_row in db.execute("SELECT * FROM lost_items").fetchall():
            external = _external_from_lost_item(item_row)
            cos = cosine_by_item.get(item_row["id"]) if cosine_by_item is not None else None
            if _try_create_match(db, report, external, cos):
                _notify_match(db, user, report, external)

def run_matching_for_lost_item(lost_item_id: int) -> int:
    """單筆招領物 → 反向比對所有現有通報，必要時建立 match 並通知失主。回傳新配對數。"""
    new_matches = 0
    with closing(get_db()) as db:
        item_row = db.execute("SELECT * FROM lost_items WHERE id = %s", (lost_item_id,)).fetchone()
        if not item_row: return 0
        external = _external_from_lost_item(item_row)
        item_embedding = _ensure_item_embedding(db, item_row, external)
        for report in db.execute("SELECT * FROM lost_reports").fetchall():
            cos = None
            if item_embedding is not None:
                report_embedding = _ensure_report_embedding(db, report)
                if report_embedding is not None:
                    cos = matching.cosine(item_embedding, report_embedding)
            if _try_create_match(db, report, external, cos):
                user = db.execute("SELECT * FROM users WHERE id = %s", (report["user_id"],)).fetchone()
                _notify_match(db, user, report, external)
                new_matches += 1
    return new_matches

def process_new_lost_items() -> dict:
    """處理「剛爬進來、還沒算過向量」的招領物：產生 embedding 並反向比對現有通報。

    爬蟲（scripts/scrapers/supa_crawl_lib.py）只負責把資料 upsert 進 lost_items；
    這支負責後續的語意處理與媒合，適合在每次爬完後執行（task match-lostitems）。
    """
    with closing(get_db()) as db:
        new_ids = [r["id"] for r in db.execute("SELECT id FROM lost_items WHERE embedding IS NULL OR embedding = '' ORDER BY id")]
    total_matches = 0
    for lost_item_id in new_ids:
        total_matches += run_matching_for_lost_item(lost_item_id)
    return {"ok": True, "processed": len(new_ids), "new_matches": total_matches}


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
        except Exception:
            app.logger.exception("Failed to send Supabase OTP")
            flash("發送驗證碼失敗，請稍後再試。", "error")
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
        if not supabase:
            flash("系統未設定 Supabase 憑證。", "error")
            return redirect(url_for("login"))
        try:
            res = supabase.auth.verify_otp({"email": email, "token": otp, "type": "email"})
            if res and res.user:
                sb_user = res.user
                with closing(get_db()) as db:
                    user = db.execute(
                        "SELECT id, supabase_id FROM users WHERE supabase_id = %s OR email = %s",
                        (sb_user.id, email),
                    ).fetchone()
                    if not user:
                        name = email.split("@")[0]
                        row = db.execute(
                            "INSERT INTO users (supabase_id, name, email, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
                            (sb_user.id, name, email, now_iso()),
                        ).fetchone()
                        db.commit()
                        user = {"id": row["id"], "supabase_id": sb_user.id}
                    elif not user["supabase_id"]:
                        db.execute("UPDATE users SET supabase_id = %s WHERE id = %s", (sb_user.id, user["id"]))
                        db.commit()
                session["user_id"] = user["id"]
                session.pop("auth_email", None)
                session.pop("auth_time", None)
                session.permanent = True
                return redirect(url_for("dashboard"))
        except Exception:
            flash("驗證失敗: 驗證碼錯誤或已過期。", "error")
    return render_template("auth.html", step="otp", email=email)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def dashboard():
    user_id = session.get("user_id")
    user = get_user(user_id) if user_id else None
    bundle = fetch_bundle(user_id)
    summary = {}
    for item in bundle["external_items"]:
        summary[item["source_name"]] = summary.get(item["source_name"], 0) + 1
    return render_template("app.html", view="dashboard", user=user, summary=summary, **bundle)

@app.route("/sources")
def sources():
    user_id = session.get("user_id")
    user = get_user(user_id) if user_id else None
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
                row = db.execute(
                    "INSERT INTO lost_reports (user_id, title, category, location, lost_at, description, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (user_id, title, category, location, lost_at, description, now_iso()),
                ).fetchone()
                db.commit()
                report_id = row["id"]
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
            db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = %s", (user_id,))
            db.commit()
    return redirect(url_for("notifications"))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
