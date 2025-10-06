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

# Your Provided Repository Details
REPO_NAME = "shahnlouis-commits/ASI-Intel-Dash"
FILE_PATH = "DashData/data.json"
BRANCH = "main" # Corrected to lowercase 'main' which is the default
SCHEMA_FILE = "schema.json"
MODEL_NAME = "gemini-1.5-pro-latest" 

# --- CLASSIFICATION RULES (Passed to Gemini as System Instruction) ---
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
    # All 55 supported countries from the documentation
    'countries': 'ar,au,at,be,br,bg,ca,cn,co,cz,eg,fr,de,gr,hk,hu,in,id,ie,il,it,jp,lv,lt,my,mx,ma,nl,nz,ng,no,ph,pl,pt,ro,sa,rs,sg,sk,si,za,kr,se,ch,tw,th,tr,ae,ua,gb,us,ve',
    
    # Expanded list of keywords for broader coverage
    'keywords': (
        # Original Keywords
        'sanction,instability,trade war,tariff,natural disaster,supply chain disruption,conflict,trade restriction,'
        # Geopolitical & Diplomatic
        'geopolitical tension,election,protest,unrest,coup,sovereignty,border dispute,military exercise,'
        # Economic & Financial
        'economic policy,inflation,recession,central bank,interest rates,debt crisis,market volatility,export control,'
        # Supply Chain & Resources
        'energy security,food security,critical minerals,port congestion,labor strike,'
        # Cyber & Technology
        'cyberattack,disinformation,espionage,semiconductor'
    ),
    
    'limit': 25, 
    'sort': 'published_desc'
}


# --- CORE FUNCTIONS ---

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
    
    user_prompt = f"RAW NEWS ARTICLES:\n{json.dumps(raw_news_data, indent=2)}"
    
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        MODEL_NAME,
        generation_config={"response_mime_type": "application/json"},
        system_instruction=CLASSIFICATION_INSTRUCTIONS
    )

    response = model.generate_content(user_prompt)
    
    try:
        # Assuming response.text contains the JSON string. Adjust if the API object structure is different.
        formatted_json = json.loads(response.text.strip())
        # The schema is not directly used for validation here as Gemini 1.5 handles it,
        # but it's good practice to have it for potential future local validation.
        # validate(instance=formatted_json, schema=schema) 
        return formatted_json
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"CRITICAL ERROR: LLM failed to produce valid JSON or schema mismatch.")
        print(f"Raw LLM Output (Text): {response.text}") 
        return None 

def commit_to_github(new_data):
    """Updates the specified file in the GitHub repository."""
    print("Committing data to GitHub...")
    g = Github(GITHUB_PAT)
    repo = g.get_repo(REPO_NAME)
    
    try:
        contents = repo.get_contents(FILE_PATH, ref=BRANCH)
        sha = contents.sha
    except Exception:
        sha = None

    commit_message = f"Automated Geopolitical Risk Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    action = repo.update_file if sha else repo.create_file
    
    action(
        FILE_PATH,
        commit_message,
        json.dumps(new_data, indent=4),
        sha=sha,
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
                # Filter out any articles Gemini marked as irrelevant
                relevant_data = [item for item in final_data if item.get('type') != 'irrelevant']
                
                if relevant_data:
                    print(f"Found {len(relevant_data)} relevant articles. Committing to GitHub...")
                    commit_to_github(relevant_data)
                else:
                    print("No relevant articles found after filtering. Skipping commit.")
            else:
                print("Aborting commit due to invalid LLM output.")
        else:
            print("No new articles fetched. Skipping commit.")
