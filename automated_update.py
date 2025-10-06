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
    cursor.execute("SELECT headline, type, countries, category, date, body FROM
