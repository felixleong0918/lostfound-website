import os
import sys
from pathlib import Path
from supabase import create_client, Client

# Fix python paths so the script can execute from root directory context
sys.path.append(str(Path(__file__).parent.parent))

from core import create_app
from core.extensions import db

def main():
    app = create_app()
    with app.app_context():
        print("Connecting to database cluster...")
        
        import core.models
        
        db.create_all()
        print("Initialization successful! table structure verified.")

        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        bucket_name = os.environ.get("SUPABASE_STORAGE_BUCKET")

        if supabase_url and supabase_key and bucket_name:
            supabase: Client = create_client(supabase_url, supabase_key)
            existing_buckets = {
                bucket.get("name")
                for bucket in (supabase.storage.list_buckets() or [])
                if isinstance(bucket, dict)
            }
            if bucket_name not in existing_buckets:
                try:
                    supabase.storage.create_bucket(bucket_name)
                    print(f"Initialization successful! storage bucket '{bucket_name}' created.")
                except Exception as exc:
                    raise RuntimeError(f"Failed to initialize storage bucket '{bucket_name}': {exc}") from exc
            else:
                print(f"Initialization successful! storage bucket '{bucket_name}' already exists.")
        else:
            print("Skipping storage bucket initialization (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/SUPABASE_STORAGE_BUCKET not fully set).")

if __name__ == "__main__":
    main()
