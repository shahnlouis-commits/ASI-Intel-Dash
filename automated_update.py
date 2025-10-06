import os
import json
import base64
import requests
import sqlite3
import google.generativeai as genai
from github import Github, Auth, GithubException # Added Auth
from datetime import datetime

# --- CONFIGURATION ---
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_PAT = os.environ.get("GITHUB_PAT")

REPO_NAME = "shahnlouis-commits/ASI-Dash-2.0"
JSON_FILE_PATH = "DashData/data.json"
DB_FILE_PATH = "archive.db"
BRANCH = "main"
MODEL_NAME = "gemini-1.5-pro" # <-- CORRECTED THIS LINE
LIVE_ARTICLE_LIMIT = 150

# --- CLASSIFICATION RULES ---
CLASSIFICATION_INSTRUCTIONS = """
You are a senior geopolitical risk analyst. Your task is to extract key information from raw news articles and format it as a strict JSON array based on the provided schema.

**CRITICAL RULES:**
1.  You MUST extract the publication `date` in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ).
2.  You MUST identify all relevant countries and list them as an array of ISO 3166 alpha-2 codes in the `countries` field.
3.  The `body` must be a concise, 3-4 sentence summary of the event and its risk implications, written for a consultancy client.
4.  If an article is not relevant to geopolitical or systemic risk (e.g., a local crime story), you MUST classify its `type` as 'irrelevant'.

TYPE CHOICES (Select ONE): ['high priority', 'medium priority', 'forecast alert', 'strategic watch', 'irrelevant']

CATEGORY DEFINITIONS (Select ONE. Use 'n/a' for irrelevant articles):
1. Economic Warfare & Control: Policy actions using economic means (sanctions, tariffs) for geopolitical pressure.
2. Geopolitical Instability: Risks from political conflict, social unrest, wars, or government collapses.
3. Regulatory & Policy Shift: Major governmental changes shaping markets and supply chains.
4. Structural & Environmental Risk: Systemic threats to infrastructure, resources, or continuity.
5. Security & Technology Threat: High-impact risks where the primary vector is digital or emerging technology.
6. n/a: Use this category only for articles with type 'irrelevant'.

Your FINAL OUTPUT MUST be a valid JSON array. DO NOT include any text, headers, or explanations outside the JSON array itself.
"""

# --- NEWS API QUERY CONFIGURATION (GNEWS) ---
NEWS_API_CONFIG = {
    'q': '(sanction OR tariff OR "trade war" OR geopolitical OR election OR protest)',
    'lang': 'en',
    'country': 'us,gb,ca,au,cn,jp,de,fr',
    'max': 100
}

# --- DATABASE FUNCTIONS ---
# ... (These functions are correct and do not need to be changed)
def init_db(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            headline TEXT PRIMARY KEY, type TEXT, countries TEXT,
            category TEXT, date TEXT, body TEXT
        )''')
    conn.commit()

def add_articles_to_db(conn, articles):
    cursor = conn.cursor()
    new_articles_count = 0
    for article in articles:
        cursor.execute('''
            INSERT OR IGNORE INTO articles (headline, type, countries, category, date, body)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            article['headline'], article['type'], json.dumps(article['countries']),
            article['category'], article['date'], article['body']
        ))
        if cursor.rowcount > 0: new_articles_count += 1
    conn.commit()
    return new_articles_count

def get_all_articles_from_db(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT headline, type, countries, category, date, body FROM articles ORDER BY date DESC")
    rows = cursor.fetchall()
    articles = []
    for row in rows:
        articles.append({
            "headline": row[0], "type": row[1], "countries": json.loads(row[2]),
            "category": row[3], "date": row[4], "body": row[5]
        })
    return articles

# --- GITHUB AND API FUNCTIONS ---
# ... (These functions are correct and do not need to be changed)
def fetch_news():
    print("Fetching news from GNews.io...")
    url = f"https://gnews.io/api/v4/search?token={NEWS_API_KEY}"
    params = NEWS_API_CONFIG
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json().get('articles', [])

def reformat_with_gemini(raw_news_data):
    if not raw_news_data: return []
    print(f"Reformatting {len(raw_news_data)} articles with Gemini ({MODEL_NAME})...")
    for article in raw_news_data:
        if 'title' in article: article['headline'] = article.pop('title')
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
    try:
        file_content = repo.get_contents(path, ref=branch)
        return file_content.decoded_content, file_content.sha
    except GithubException as e:
        if e.status == 404: return None, None
        raise

def commit_file_to_github(repo, path, branch, content, sha):
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
        # Authenticate with GitHub using the modern method
        auth = Auth.Token(GITHUB_PAT)
        g = Github(auth=auth) # <-- UPDATED THIS LINE
        repo = g.get_repo(REPO_NAME)
        
        db_content, db_sha = get_file_from_github(repo, DB_FILE_PATH, BRANCH)
        if db_content:
            with open("archive.db", "wb") as f:
                f.write(db_content)
        
        conn = sqlite3.connect("archive.db")
        init_db(conn)

        raw_news = fetch_news()
        if raw_news:
            processed_data = reformat_with_gemini(raw_news)
            if processed_data:
                relevant_new_data = [item for item in processed_data if item.get('type') != 'irrelevant']
                if relevant_new_data:
                    newly_added_count = add_articles_to_db(conn, relevant_new_data)
                    print(f"Added {newly_added_count} new unique articles to the archive.")

                    all_articles = get_all_articles_from_db(conn)
                    live_json_data = all_articles[:LIVE_ARTICLE_LIMIT]
                    
                    _, json_sha = get_file_from_github(repo, JSON_FILE_PATH, BRANCH)
                    commit_file_to_github(repo, JSON_FILE_PATH, BRANCH, json.dumps(live_json_data, indent=4), json_sha)
                    print(f"Committed {len(live_json_data)} articles to {JSON_FILE_PATH}")

                    with open("archive.db", "rb") as f:
                        updated_db_content = f.read()
                    commit_file_to_github(repo, DB_FILE_PATH, BRANCH, updated_db_content, db_sha)
                    print(f"Committed updated archive database to {DB_FILE_PATH}")
                else:
                    print("No new relevant articles found after Gemini filtering.")
        else:
            print("No new articles fetched from GNews API. Skipping commit.")
        
        conn.close()
