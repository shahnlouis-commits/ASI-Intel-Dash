import os
import json
import base64
import requests
from google import genai
from github import Github
from datetime import datetime
from jsonschema import validate, ValidationError

# --- CONFIGURATION ---
# Keys are read from GitHub Secrets
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_PAT = os.environ.get("GITHUB_PAT")  
# Use the new name 'GH_TOKEN' to fetch the value, but keep the variable name 'GITHUB_PAT' 
# inside the script for consistency (so you don't have to change the PyGithub calls).

# Your Provided Repository Details
REPO_NAME = "shahnlouis-commits/ASI-Intel-Dash"
FILE_PATH = "DashData/data.json"
BRANCH = "Main"
SCHEMA_FILE = "schema.json"
MODEL_NAME = "gemini-2.5-pro" # Upgraded for better classification

# --- CLASSIFICATION RULES (Passed to Gemini as System Instruction) ---
CLASSIFICATION_INSTRUCTIONS = """
You are a senior geopolitical risk analyst for a consulting firm. Your task is to classify raw news articles into a strict JSON format.
Analyze the content and assign a single 'type' and 'category' based on the definitions below.

TYPE CHOICES (Select ONE): ['high priority', 'medium priority', 'forecast alert', 'strategic watch']

CATEGORY DEFINITIONS (Select ONE based on the primary risk driver):
1. Economic Warfare & Control: Policy actions that use economic means (tariffs, sanctions, export controls, trade investigations) to exert geopolitical pressure.
2. Geopolitical Instability: Risks from political conflict, state fragility, social unrest, wars, coups, or government collapses.
3. Regulatory & Policy Shift: Major governmental or multilateral regulatory changes designed to shape markets and supply chains (e.g., new EU investment plans, critical mineral sourcing).
4. Structural & Environmental Risk: Systemic threats to physical infrastructure, resources, and continuity (e.g., nuclear safety failures, labor disputes, resource scarcity, climate-driven risks).
5. Security & Technology Threat: High-impact risks where the primary vector is digital or emerging technology (e.g., major cyberattacks on critical infrastructure, state-sponsored hacking, corporate espionage).

Your FINAL OUTPUT MUST be a valid JSON array strictly adhering to the provided JSON Schema. DO NOT include any text, headers, or explanations outside the JSON array.
"""
# --- NEWS API QUERY CONFIGURATION ---
NEWS_QUERY_CONFIG = {
    'countries': 'ar,au,br,ca,cn,eg,fr,de,in,id,ir,iq,il,jp,kp,sa,ru,kr,tw,ua,uk,us', # Expanded global list
    'keywords': 'sanction, instability, trade war, tariff, natural disaster, supply chain disruption, conflict, trade restriction',
    'limit': 25, 
    'sort': 'published_desc'
}


# --- CORE FUNCTIONS (Modified to use fixed data path) ---

def fetch_news():
    """Fetches geopolitical news from Mediastack API."""
    print("Fetching news from Mediastack...")
    url = "http://api.mediastack.com/v1/news"
    params = {**NEWS_QUERY_CONFIG, 'access_key': NEWS_API_KEY}
    
    response = requests.get(url, params=params)
    response.raise_for_status() 
    return response.json().get('data', [])

def reformat_with_gemini(raw_news_data, schema):
    """Feeds raw data into Gemini to reformat and extract risk data."""
    if not raw_news_data:
        return []

    print(f"Reformatting {len(raw_news_data)} articles with Gemini ({MODEL_NAME})...")
    
    # Combine the system instructions and the raw data for the user prompt
    user_prompt = f"RAW NEWS ARTICLES:\n{json.dumps(raw_news_data, indent=2)}"
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_prompt,
        config={
            "system_instruction": CLASSIFICATION_INSTRUCTIONS,
            "response_mime_type": "application/json",
            "response_schema": schema # Pass the JSON schema directly
        }
    )
    
    try:
        formatted_json = json.loads(response.text.strip())
        validate(instance=formatted_json, schema=schema)
        return formatted_json
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"CRITICAL ERROR: LLM failed to produce valid JSON or schema mismatch.")
        # If Gemini fails the strict schema, we should review the raw output before proceeding
        print(f"Raw LLM Output (Text): {response.text}") 
        return None 

def commit_to_github(new_data):
    """Updates the specified file in the GitHub repository."""
    print("Committing data to GitHub...")
    g = Github(GITHUB_PAT)
    repo = g.get_repo(REPO_NAME)
    
    # Try to get the existing file to obtain its SHA (required for updating)
    try:
        contents = repo.get_contents(FILE_PATH, ref=BRANCH)
        sha = contents.sha
    except Exception:
        # File doesn't exist (first run or file deleted), will create it later
        sha = None

    commit_message = f"Automated 30-min Geopolitical Risk Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    # Commit the new data (overwriting the file with the new analysis)
    action = repo.update_file if sha else repo.create_file
    
    action(
        FILE_PATH,
        commit_message,
        json.dumps(new_data, indent=4),
        sha=sha, # Only required for update, ignored for create
        branch=BRANCH
    )
    print(f"Commit successful! File updated/created at {FILE_PATH} on branch {BRANCH}.")


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    if not all([NEWS_API_KEY, GEMINI_API_KEY, GITHUB_PAT]):
        print("ERROR: One or more environment variables are missing. Check your GitHub Secrets.")
    else:
        try:
            with open(SCHEMA_FILE, 'r') as f:
                data_schema = json.load(f)
        except FileNotFoundError:
            print(f"FATAL ERROR: Schema file {SCHEMA_FILE} not found. Cannot proceed.")
            exit(1)
            
        raw_news = fetch_news()
        
        if raw_news:
            final_data = reformat_with_gemini(raw_news, data_schema)
            
            if final_data is not None:
                commit_to_github(final_data)
            else:
                print("Aborting commit due to invalid LLM output.")
        else:
            print("No new articles fetched. Skipping commit.")
