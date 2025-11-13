import requests
import time
import os
from dotenv import load_dotenv
import geocoder 

# Get the directory of this file and load .env from there
current_dir = os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(current_dir, '.env')
load_dotenv(env_file)

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
            "menu_url": b.get("attributes", {}).get("menu_url", "Menu not available"),
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

def get_coordinates_fallback(address):
    """Fallback geocoding using the free geocoder library."""
    try:
        g = geocoder.osm(address)
        if g.ok:
            return {
                "lat": g.lat,
                "lng": g.lng,
                "formatted_address": g.address
            }
        else:
            print(f"❌ Could not geocode address: {address}")
            return None
    except Exception as e:
        print(f"❌ Geocoding error: {e}")
        return None

def get_current_location():
    """Get current location using IP-based geolocation."""
    try:
        g = geocoder.ip('me')
        if g.ok:
            return {
                "lat": g.lat,
                "lng": g.lng,
                "formatted_address": f"{g.city}, {g.state}, {g.country}"
            }
        else:
            print("❌ Could not determine current location")
            return None
    except Exception as e:
        print(f"❌ Error getting current location: {e}")
        return None

def get_location_input():
    """Interactive function to get user location."""
    print("\n📍 How would you like to specify your location?")
    print("1. Enter an address/city name")
    print("2. Use current location (IP-based)")
    print("3. Enter coordinates manually")
    
    while True:
        choice = input("Choose option (1-3): ").strip()
        
        if choice == "1":
            address = input("Enter address or city: ").strip()
            if address:
                location_data = get_coordinates_from_address(address)
                if location_data:
                    print(f"📍 Found: {location_data.get('formatted_address', address)}")
                    return {"lat": location_data["lat"], "lng": location_data["lng"]}
                else:
                    print("❌ Could not find that location. Please try a different address.")
                    continue
            else:
                print("❌ Please enter an address.")
                continue
                
        elif choice == "2":
            location_data = get_current_location()
            if location_data:
                print(f"📍 Current location: {location_data['formatted_address']}")
                return {"lat": location_data["lat"], "lng": location_data["lng"]}
            else:
                print("❌ Could not determine current location. Please try another option.")
                continue
                
        elif choice == "3":
            try:
                lat = float(input("Enter latitude: "))
                lng = float(input("Enter longitude: "))
                print(f"📍 Using coordinates: {lat}, {lng}")
                return {"lat": lat, "lng": lng}
            except ValueError:
                print("❌ Invalid coordinates. Please enter valid numbers.")
                continue
        else:
            print("❌ Invalid choice. Please enter 1, 2, or 3.")
            continue
