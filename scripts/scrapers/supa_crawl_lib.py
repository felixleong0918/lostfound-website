import os
import sys
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from pathlib import Path
from supabase import create_client, Client
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).resolve().parent.parent))
load_dotenv()

TARGET_URL = "https://lostfound.lib.ntu.edu.tw/"
SOURCE_SYSTEM = "school_libraries"

def clean_text(raw_text, max_length=None):
    """Strips messy HTML whitespace and truncates to avoid DB crashes."""
    if not raw_text:
        return None
    cleaned = " ".join(raw_text.split())
    if max_length and len(cleaned) > max_length:
        return cleaned[:max_length]
    return cleaned

def fetch_and_push():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("Error: Missing Supabase credentials in .env")
        return

    supabase: Client = create_client(supabase_url, supabase_key)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    # Calculate the watermark: 7 days ago
    watermark_date = (datetime.now() - timedelta(days=7)).strftime("%Y/%m/%d")
    print(f"Starting shallow crawl. Watermark cutoff: {watermark_date}")

    page = 0
    scan_active = True

    while scan_active:
        print(f"Scraping page {page}...")
        params = {'q': 'viewer', 'page': page}
        response = requests.get(TARGET_URL, params=params, headers=headers)
        
        if response.status_code != 200:
            print(f"Failed to retrieve page {page}. Status: {response.status_code}")
            break

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Using the superior selector from the reference script
        rows = soup.select('table tbody tr')
        if not rows:
            print("No data found. Pagination ceiling reached.")
            break

        upload_batch = []
        # Track the minimum found_date seen on this page; start with a high sentinel value
        oldest_date_on_page = "9999/12/31"
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 6:
                raw_date = clean_text(cols[1].text, 50)
                
                upload_batch.append({
                    "source_system": SOURCE_SYSTEM,
                    "original_id": clean_text(cols[0].text, 50),
                    "found_date": raw_date,
                    "location": clean_text(cols[2].text),
                    "description": clean_text(cols[3].text),
                    "category": clean_text(cols[4].text, 100),
                    "storage_place": clean_text(cols[5].text, 250)
                })

                if raw_date and raw_date < oldest_date_on_page:
                    oldest_date_on_page = raw_date

        if upload_batch:
            print(f"Upserting {len(upload_batch)} records to Supabase...")
            supabase.table("lost_items").upsert(upload_batch, on_conflict="source_system, original_id").execute()

        # Evaluate Watermark Strategy
        if oldest_date_on_page < watermark_date:
            print(f"Oldest item ({oldest_date_on_page}) is past the 7-day watermark. Terminating crawler.")
            scan_active = False
        else:
            page += 1
            # Polite delay to prevent rate limiting
            time.sleep(2)

        # Safety failsafe
        if page > 10:
            print("Failsafe triggered: Exceeded 10 pages.")
            scan_active = False

if __name__ == "__main__":
    fetch_and_push()
