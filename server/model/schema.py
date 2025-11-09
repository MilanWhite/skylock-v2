CREATE_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS tles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    line1 TEXT NOT NULL,
    line2 TEXT NOT NULL,
    source TEXT,
    fetched_at TEXT,
    UNIQUE(name, line1, line2)
);
'''

def create_tables(conn):
    """Executes the schema creation scripts."""
    try:
        cur = conn.cursor()
        cur.executescript(CREATE_TABLE_SQL)
        conn.commit()
    except Exception as e:
        print(f"Error creating schema: {e}")