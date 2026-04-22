import requests
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import time

# ── CONFIG ──────────────────────────────────────────────────────────────────
LETTERBOXD_USER = "itannoguer"
SHEET_ID = "1jgAMBSpiSLBSPbhbJZfrj_KJ1QQt2uxvDk210tULxlo"
COUNTRY = "AR"
LANGUAGE = "es"

# Letterboxd session cookies (set via GitHub Secrets)
LB_COOKIES = {
    "com.xk72.webparts.csrf": os.environ.get("LB_CSRF", ""),
    "letterboxd.signed.in": os.environ.get("LB_SESSION", ""),
}

# Google credentials from GitHub Secrets
GOOGLE_CREDS = json.loads(os.environ.get("GOOGLE_CREDENTIALS", "{}"))

# ── JUSTWATCH ────────────────────────────────────────────────────────────────
JUSTWATCH_QUERY = """
query SearchTitles($country: Country!, $language: Language!, $first: Int, $searchQuery: String!) {
  popularTitles(country: $country, first: $first, filter: {searchQuery: $searchQuery, objectTypes: [MOVIE]}) {
    edges {
      node {
        content(country: $country, language: $language) {
          title
          originalReleaseYear
        }
        offers(country: $country, platform: WEB) {
          monetizationType
          package {
            clearName
          }
        }
      }
    }
  }
}
"""

def get_watchlist():
    """Fetch watchlist from Letterboxd using session cookies."""
    movies = []
    page = 1
    
    session = requests.Session()
    session.cookies.update(LB_COOKIES)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Referer": "https://letterboxd.com/",
    }
    
    while True:
        url = f"https://letterboxd.com/{LETTERBOXD_USER}/watchlist/page/{page}/"
        response = session.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"Error fetching page {page}: {response.status_code}")
            break
        
        html = response.text
        
        # Extract film names using data-item-name attribute
        import re
        matches = re.findall(r'data-item-name="([^"]+)"', html)
        
        if not matches:
            break
            
        movies.extend(matches)
        print(f"Page {page}: found {len(matches)} movies")
        
        # Check if there's a next page
        if f'/page/{page + 1}/' not in html:
            break
            
        page += 1
        time.sleep(1)  # Be polite
    
    return movies

def get_justwatch_availability(title):
    """Query JustWatch GraphQL API for a movie's availability in Argentina."""
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": "https://www.justwatch.com",
        "Referer": "https://www.justwatch.com/",
    }
    
    payload = {
        "query": JUSTWATCH_QUERY,
        "variables": {
            "country": COUNTRY,
            "language": LANGUAGE,
            "first": 1,
            "searchQuery": title
        }
    }
    
    try:
        response = requests.post(
            "https://apis.justwatch.com/graphql",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            return "sin disponibilidad"
        
        data = response.json()
        edges = data.get("data", {}).get("popularTitles", {}).get("edges", [])
        
        if not edges:
            return "sin disponibilidad"
        
        offers = edges[0].get("node", {}).get("offers", [])
        
        if not offers:
            return "sin disponibilidad"
        
        # Format: "Netflix:FLATRATE|Amazon Prime Video:RENT"
        platforms = []
        seen = set()
        for offer in offers:
            name = offer.get("package", {}).get("clearName", "")
            mtype = offer.get("monetizationType", "")
            key = f"{name}:{mtype}"
            if key not in seen:
                platforms.append(key)
                seen.add(key)
        
        return "|".join(platforms) if platforms else "sin disponibilidad"
        
    except Exception as e:
        print(f"JustWatch error for '{title}': {e}")
        return "sin disponibilidad"

def update_sheet(movies_data):
    """Write results to Google Sheets."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds = Credentials.from_service_account_info(GOOGLE_CREDS, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1
    
    # Clear existing data (keep headers)
    sheet.batch_clear(["A2:D500"])
    
    # Write new data
    rows = []
    for movie in movies_data:
        rows.append([
            movie["title"],
            movie.get("year", ""),
            movie["platforms"],
            movie["updated_at"]
        ])
    
    if rows:
        sheet.update(f"A2:D{len(rows)+1}", rows)
    
    print(f"Updated sheet with {len(rows)} movies")

def main():
    from datetime import datetime
    
    print("🎬 Starting Letterboxd × JustWatch sync...")
    
    # 1. Get watchlist
    print("\n📋 Fetching watchlist from Letterboxd...")
    movies = get_watchlist()
    print(f"Total movies found: {len(movies)}")
    
    if not movies:
        print("No movies found. Check your Letterboxd cookies.")
        return
    
    # 2. Query JustWatch for each movie
    print("\n🔍 Querying JustWatch Argentina...")
    results = []
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    for i, title in enumerate(movies):
        print(f"[{i+1}/{len(movies)}] {title}")
        platforms = get_justwatch_availability(title)
        
        # Extract year from title if present (e.g. "Misery (1990)")
        import re
        year_match = re.search(r'\((\d{4})\)$', title)
        clean_title = re.sub(r'\s*\(\d{4}\)$', '', title).strip()
        year = year_match.group(1) if year_match else ""
        
        results.append({
            "title": clean_title,
            "year": year,
            "platforms": platforms,
            "updated_at": now
        })
        
        time.sleep(0.5)  # Rate limiting
    
    # 3. Update Google Sheet
    print("\n📊 Updating Google Sheet...")
    update_sheet(results)
    
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
