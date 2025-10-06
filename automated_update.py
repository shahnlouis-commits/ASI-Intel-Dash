import os
import json
import base64
import requests
import sqlite3
from google import genai
from github import Github, GithubException
from datetime import datetime

# --- CONFIGURATION ---
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_PAT = os.environ.get("GITHUB_PAT")

REPO_NAME = "shahnlouis-commits/ASI-Intel-Dash"
JSON_FILE_PATH = "DashData/data.json"
DB_FILE_PATH = "DashData/archive.db"
BRANCH = "main"
MODEL_NAME = "gemini-1.5-pro-latest"
LIVE_ARTICLE_LIMIT = 150 # Max articles for the live JSON file

# --- CLASSIFICATION RULES ---
CLASSIFICATION_INSTRUCTIONS = """
You are a senior geopolitical risk analyst...
(Your detailed prompt remains here, no changes needed)
"""

# --- NEWS API QUERY CONFIGURATION ---
NEWS_QUERY_CONFIG = {
    'countries': 'ar,au,at,be,br,bg,ca,cn,co,cz,eg,fr,de,gr,hk,hu,in,id,ie,il,it,jp,lv,lt,my,mx,ma,nl,nz,ng,no,ph,pl,pt,ro,sa,rs,sg,sk,si,za,kr,se,ch,tw,th,tr,ae,ua,gb,us,ve',
    'keywords': ('sanction,instability,trade war,tariff,natural disaster,supply chain disruption,conflict,trade restriction,geopolitical tension,election,protest,unrest,coup,sovereignty,border dispute,military exercise,economic policy,inflation,recession,central bank,interest rates,debt crisis,market volatility,export control,energy security,food security,critical minerals,port congestion,labor strike,cyberattack,disinformation,espionage,semiconductor'),
    'limit': 25,
    'sort': 'published_desc'
}

# --- DATABASE FUNCTIONS ---

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
    """Adds new articles to the database, ignoring duplicates."""
    cursor = conn.cursor()
    new_articles_count = 0
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
        if cursor.rowcount > 0:
            new_articles_count += 1
    conn.commit()
    return new_articles_count

def get_all_articles_from_db(conn):
    """Fetches all articles from the database, sorted by date."""
    cursor = conn.cursor()
    cursor.execute("SELECT headline, type, countries, category, date, body FROM articles ORDER BY date DESC")
    rows = cursor.fetchall()
    # Convert rows back to list of dictionaries
    articles = []
    for row in rows:
        articles.append({
            "headline": row[0],
            "type": row[1],
            "countries": json.loads(row[2]), # Convert JSON string back to list
            "category": row[3],
            "date": row[4],
            "body": row[5]
        })
    return articles

# --- GITHUB AND API FUNCTIONS ---

def fetch_news():
    # ... (This function remains unchanged)
    print("Fetching news from Mediastack...")
    url = "http://api.mediastack.com/v1/news"
    params = {**NEWS_QUERY_CONFIG, 'access_key': NEWS_API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json().get('data', [])


def reformat_with_gemini(raw_news_data):
    # ... (This function remains unchanged)
    if not raw_news_data:
        return []
    print(f"Reformatting {len(raw_news_data)} articles with Gemini ({MODEL_NAME})...")
    user_prompt = f"RAW NEWS ARTICLES:\n{json.dumps(raw_news_data, indent=2)}"
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        MODEL_NAME,
        generation_config={"response_mime_type": "application/json"},
        system_instruction=CLASSIFICATION_INSTRUCTIONS
    )
    response = model.generate_content(user_prompt)
    try:
        return json.loads(response.text.strip())
    except json.JSONDecodeError:
        print(f"CRITICAL ERROR: LLM failed to produce valid JSON.")
        print(f"Raw LLM Output: {response.text}")
        return None

def get_file_from_github(repo, path, branch):
    """Fetches a file from github and returns its content and sha."""
    try:
        file_content = repo.get_contents(path, ref=branch)
        return file_content.decoded_content, file_content.sha
    except GithubException as e:
        if e.status == 404:
            return None, None # File doesn't exist
        raise

def commit_file_to_github(repo, path, branch, content, sha, is_binary=False):
    """Commits a file (text or binary) to the repo."""
    commit_message = f"Automated Update for {os.path.basename(path)}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    if sha:
        repo.update_file(path, commit_message, content, sha, branch=branch)
    else:
        repo.create_file(path, commit_message, content, branch=branch)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    if not all([NEWS_API_KEY, GEMINI_API_KEY, GITHUB_PAT]):
        print("ERROR: One or more environment variables are missing.")
    else:
        # Initialize GitHub connection
        g = Github(GITHUB_PAT)
        repo = g.get_repo(REPO_NAME)
        
        # Download existing database from GitHub
        db_content, db_sha = get_file_from_github(repo, DB_FILE_PATH, BRANCH)
        if db_content:
            with open("archive.db", "wb") as f:
                f.write(db_content)
        
        # Connect to the local SQLite DB and initialize
        conn = sqlite3.connect("archive.db")
        init_db(conn)

        # Fetch and process new articles
        raw_news = fetch_news()
        if raw_news:
            processed_data = reformat_with_gemini(raw_news)
            if processed_data:
                relevant_new_data = [item for item in processed_data if item.get('type') != 'irrelevant']
                
                if relevant_new_data:
                    # Add new, unique articles to the database
                    newly_added_count = add_articles_to_db(conn, relevant_new_data)
                    print(f"Added {newly_added_count} new unique articles to the archive.")

                    # Get all articles from the DB for the final processing
                    all_articles = get_all_articles_from_db(conn)
                    
                    # Create the live JSON data (limited entries)
                    live_json_data = all_articles[:LIVE_ARTICLE_LIMIT]
                    
                    # Commit live JSON file
                    _, json_sha = get_file_from_github(repo, JSON_FILE_PATH, BRANCH)
                    commit_file_to_github(repo, JSON_FILE_PATH, BRANCH, json.dumps(live_json_data, indent=4), json_sha)
                    print(f"Committed {len(live_json_data)} articles to {JSON_FILE_PATH}")

                    # Commit the updated database file
                    with open("archive.db", "rb") as f:
                        updated_db_content = f.read()
                    commit_file_to_github(repo, DB_FILE_PATH, BRANCH, updated_db_content, db_sha, is_binary=True)
                    print(f"Committed updated archive database to {DB_FILE_PATH}")

                else:
                    print("No new relevant articles found. Skipping commit.")
        else:
            print("No new articles fetched from API. Skipping commit.")
        
        conn.close()
