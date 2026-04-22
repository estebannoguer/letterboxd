import requests
import os
import time
import re
from datetime import datetime

# ── CONFIG ───────────────────────────────────────────────────────────────────
LETTERBOXD_USER = "itannoguer"
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_NAME = "Watchlist"
COUNTRY = "AR"
LANGUAGE = "es"

LB_COOKIES = {
    "com.xk72.webparts.csrf": os.environ.get("LB_CSRF", ""),
    "letterboxd.signed.in":   os.environ.get("LB_SESSION", ""),
}

HEADERS_LB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Referer": "https://letterboxd.com/",
}

JUSTWATCH_QUERY = """
query SearchTitles($country: Country!, $language: Language!, $first: Int, $searchQuery: String!) {
  popularTitles(country: $country, first: $first, filter: {searchQuery: $searchQuery, objectTypes: [MOVIE]}) {
    edges {
      node {
        content(country: $country, language: $language) { title originalReleaseYear }
        offers(country: $country, platform: WEB) {
          monetizationType
          package { clearName }
        }
      }
    }
  }
}
"""

# ── LETTERBOXD ───────────────────────────────────────────────────────────────
def get_watchlist():
    movies = []
    page = 1
    session = requests.Session()
    session.cookies.update(LB_COOKIES)

    while True:
        url = f"https://letterboxd.com/{LETTERBOXD_USER}/watchlist/page/{page}/"
        r = session.get(url, headers=HEADERS_LB, timeout=15)
        if r.status_code != 200:
            print(f"  Page {page} returned {r.status_code}, stopping.")
            break

        matches = re.findall(r'data-item-name="([^"]+)"', r.text)
        if not matches:
            break

        movies.extend(matches)
        print(f"  Page {page}: {len(matches)} movies")

        if f'/page/{page + 1}/' not in r.text:
            break
        page += 1
        time.sleep(1)

    return movies

# ── JUSTWATCH ────────────────────────────────────────────────────────────────
def get_availability(title):
    try:
        r = requests.post(
            "https://apis.justwatch.com/graphql",
            json={"query": JUSTWATCH_QUERY, "variables": {
                "country": COUNTRY, "language": LANGUAGE,
                "first": 1, "searchQuery": title
            }},
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Origin": "https://www.justwatch.com",
                "Referer": "https://www.justwatch.com/",
            },
            timeout=10
        )
        edges = r.json().get("data", {}).get("popularTitles", {}).get("edges", [])
        if not edges:
            return "sin disponibilidad"
        offers = edges[0].get("node", {}).get("offers", [])
        if not offers:
            return "sin disponibilidad"
        seen, result = set(), []
        for o in offers:
            k = f"{o['package']['clearName']}:{o['monetizationType']}"
            if k not in seen:
                result.append(k)
                seen.add(k)
        return "|".join(result)
    except Exception as e:
        print(f"  JustWatch error: {e}")
        return "sin disponibilidad"

# ── AIRTABLE ─────────────────────────────────────────────────────────────────
def airtable_request(method, endpoint, **kwargs):
    base_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    r = requests.request(method, f"{base_url}{endpoint}", headers=headers, **kwargs)
    r.raise_for_status()
    return r.json()

def get_all_record_ids():
    ids = []
    offset = None
    while True:
        params = {"fields[]": "Título", "pageSize": 100}
        if offset:
            params["offset"] = offset
        data = airtable_request("GET", "", params=params)
        ids.extend([rec["id"] for rec in data.get("records", [])])
        offset = data.get("offset")
        if not offset:
            break
    return ids

def delete_all_records():
    ids = get_all_record_ids()
    for i in range(0, len(ids), 10):
        batch = ids[i:i+10]
        params = "&".join([f"records[]={rid}" for rid in batch])
        airtable_request("DELETE", f"?{params}")
        time.sleep(0.2)
    print(f"  Deleted {len(ids)} existing records")

def insert_records(movies):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    for i in range(0, len(movies), 10):
        batch = movies[i:i+10]
        records = [{"fields": {
            "Título": m["title"],
            "Año": m["year"],
            "Plataformas": m["platforms"],
            "Actualizado": now,
        }} for m in batch]
        airtable_request("POST", "", json={"records": records, "typecast": True})
        time.sleep(0.2)
    print(f"  Inserted {len(movies)} records")

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("Letterboxd x JustWatch AR — starting sync\n")

    print("Fetching watchlist...")
    raw = get_watchlist()
    print(f"  Total: {len(raw)} movies\n")

    if not raw:
        print("No movies found. Check LB_CSRF and LB_SESSION secrets.")
        return

    print("Querying JustWatch Argentina...")
    results = []
    for i, raw_title in enumerate(raw):
        year_m = re.search(r'\((\d{4})\)$', raw_title)
        title  = re.sub(r'\s*\(\d{4}\)$', '', raw_title).strip()
        year   = year_m.group(1) if year_m else ""
        platforms = get_availability(title)
        print(f"  [{i+1}/{len(raw)}] {title} -> {platforms[:60]}")
        results.append({"title": title, "year": year, "platforms": platforms})
        time.sleep(0.4)

    print("\nUpdating Airtable...")
    delete_all_records()
    insert_records(results)

    print("\nSync complete!")

if __name__ == "__main__":
    main()
