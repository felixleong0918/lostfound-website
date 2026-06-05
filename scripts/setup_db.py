import os
import sys
from pathlib import Path

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

if __name__ == "__main__":
    main()
