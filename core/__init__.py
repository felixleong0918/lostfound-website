import os
from pathlib import Path
from flask import Flask, jsonify
from core.extensions import db
from dotenv import load_dotenv

# 1. Force explicitly find the .env file in the root directory
# This ensures it loads regardless of where you run the script from
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, ".env"))

def create_app() -> Flask:
    app = Flask(__name__)
    
    db_url = os.environ.get("DATABASE_URL", "sqlite:///local.db")
    
    # 2. Diagnostic Print: Prove exactly what we are connecting to
    # (Remove this print statement before you deploy to Vercel later!)
    # print(f"--- DEBUG: Attempting to connect to: {db_url[:30]}... ---")
    
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    @app.route("/api/items", methods=["GET"])
    def get_items():
        from core.models import LostItem
        items = LostItem.query.order_by(LostItem.found_date.desc()).all()
        return jsonify([item.to_dict() for item in items])

    return app