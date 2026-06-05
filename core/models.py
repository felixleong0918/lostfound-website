from core.extensions import db
from datetime import datetime

class LostItem(db.Model):
    __tablename__ = 'lost_items'

    # 1. The Integer Surrogate Key (Auto-increments automatically in Postgres)
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # 2. The Natural Keys for the Scrapers
    source_system = db.Column(db.String(50), nullable=False)
    original_id = db.Column(db.String(50), nullable=False)
    
    # 3. The rule that prevents duplicate scraped data
    __table_args__ = (
        db.UniqueConstraint('source_system', 'original_id', name='uix_source_original_id'),
    )

    found_date = db.Column(db.String(50), nullable=False)
    location = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(100), nullable=True)
    storage_place = db.Column(db.String(250), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
