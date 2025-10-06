import sqlite3
import json

DB_FILE = "archive.db"
JSON_FILE = "old_data.json"

def init_db(conn):
    """Initializes the database table if it doesn't exist."""
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            headline TEXT PRIMARY KEY,
            type TEXT,
            countries TEXT,
            category TEXT,
            date TEXT,
            body TEXT
        )
    ''')
    conn.commit()

def add_articles_to_db(conn, articles):
    """Adds articles to the database, ignoring duplicates."""
    cursor = conn.cursor()
    for article in articles:
        # The headline is the PRIMARY KEY, so INSERT OR IGNORE prevents duplicates
        cursor.execute('''
            INSERT OR IGNORE INTO articles (headline, type, countries, category, date, body)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            article['headline'],
            article['type'],
            json.dumps(article['countries']), # Store list as JSON string
            article['category'],
            article['date'],
            article['body']
        ))
    conn.commit()

# --- Main Execution ---
if __name__ == "__main__":
    print(f"Connecting to new database: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    init_db(conn)

    try:
        print(f"Reading data from {JSON_FILE}...")
        with open(JSON_FILE, 'r') as f:
            old_data = json.load(f)
        
        print(f"Adding {len(old_aata)} articles to the database...")
        add_articles_to_db(conn, old_data)
        
        print("Success! Database has been seeded with your old data.")

    except FileNotFoundError:
        print(f"ERROR: Could not find the file '{JSON_FILE}'. Please make sure it's in the root directory.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()
