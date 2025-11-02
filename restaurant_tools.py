import requests
import time
import os
from dotenv import load_dotenv
# Get the directory of this file and load .env from there
current_dir = os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(current_dir, '.env')
load_dotenv(env_file)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
YELP_API_KEY = os.getenv("YELP_API_KEY")

YELP_CUISINE_MAP = {
    "indian": "indpak",
    "italian": "italian",
    "chinese": "chinese",
    "mexican": "mexican",
    "japanese": "japanese",
    "thai": "thai",
    "vegan": "vegan",
    "vegetarian": "vegetarian",
    "french": "french",
    "american": "newamerican",
    "mediterranean": "mediterranean",
}

def call_google_places(location, cuisine=None, budget=None):
    """Call Google Places API to fetch nearby restaurants."""
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{location['lat']},{location['lng']}",
        "radius": 2000,
        "type": "restaurant",
        "key": GOOGLE_API_KEY
    }

    if cuisine:
        params["keyword"] = cuisine

    resp = requests.get(url, params=params)
    data = resp.json()

    restaurants = []
    for r in data.get("results", []):
        restaurants.append({
            "name": r["name"],
            "rating": r.get("rating"),
            "price_level": r.get("price_level"),
            "address": r.get("vicinity"),
            "source": "google",
        })

    return restaurants


def call_yelp(location, cuisine=None, budget=None, limit=10):
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    
    params = {
        "latitude": location["lat"],
        "longitude": location["lng"],
        "limit": limit,
        "sort_by": "rating",
    }

    # Cuisine fix
    if cuisine:
        alias = YELP_CUISINE_MAP.get(cuisine.lower())
        if alias:
            params["categories"] = alias
        else:
            params["term"] = cuisine  # fallback
    
    # Budget fix (Yelp uses 1–4)
    if budget == "low":
        params["price"] = "1,2"
    elif budget == "medium":
        params["price"] = "2,3"
    elif budget == "high":
        params["price"] = "3,4"

    response = requests.get("https://api.yelp.com/v3/businesses/search", headers=headers, params=params)
    data = response.json()

    if "businesses" not in data:
        return []

    restaurants = []
    for b in data.get("businesses", []):
        restaurants.append({
            "name": b["name"],
            "rating": b.get("rating"),
            "price_level": b.get("price"),
            "address": b["location"]["address1"],
            "categories": [c["title"] for c in b.get("categories", [])],
            "phone" : b["phone"],
            "source": "yelp"
        })

    return restaurants


def search_restaurants(location, cuisine=None, budget=None):
    """Fetch from both sources and merge."""
    results = []

    try:
        results.extend(call_google_places(location, cuisine, budget))
    except Exception as e:
        print("Google API error:", e)
        time.sleep(1)

    try:
        results.extend(call_yelp(location, cuisine, budget))
    except Exception as e:
        print("Yelp API error:", e)
        time.sleep(1)

    return results
