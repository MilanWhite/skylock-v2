import sqlite3
import os

# Define the database path relative to the project root
# (assuming the main script runs from the root)
DB_PATH = "database/tles.db"

def get_db_connection():
    """Establishes a connection to the SQLite database and ensures tables exist."""

    # Ensure the database directory exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        print(f"Creating database directory: {db_dir}")
        os.makedirs(db_dir)

    conn = sqlite3.connect(DB_PATH)
    
    # Create the tles table if it doesn't exist
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            line1 TEXT NOT NULL,
            line2 TEXT NOT NULL,
            source TEXT,
            fetched_at TEXT,
            UNIQUE(name, line1, line2)
        )
    ''')
    conn.commit()
    
    return conn