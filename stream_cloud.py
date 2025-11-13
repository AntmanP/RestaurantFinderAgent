import streamlit as st
import json
import os
from planner_agent_cloud import plan_search
from restaurant_tools import call_yelp, get_current_location
from agent_controller_cloud import critique_results
import pandas as pd
import geocoder

# Set page config
st.set_page_config(
    page_title="Restaurant Finder",
    page_icon="🍽️",
    layout="wide"
)

# Handle environment variables for deployment
def load_api_keys():
    """Load API keys from Streamlit secrets or environment variables"""
    try:
        # Try Streamlit secrets first (for deployed version)
        yelp_key = st.secrets["YELP_API_KEY"]
        openai_key = st.secrets.get("OPENAI_API_KEY", None)
        return yelp_key, openai_key
    except:
        # Fallback to environment variables (for local development)
        from dotenv import load_dotenv
        load_dotenv()
        yelp_key = os.getenv("YELP_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        return yelp_key, openai_key

# Load API keys
YELP_API_KEY, OPENAI_API_KEY = load_api_keys()

# Initialize session state
if 'location' not in st.session_state:
    st.session_state.location = None
if 'results' not in st.session_state:
    st.session_state.results = []

def get_coordinates_from_address_streamlit(address):
    """Convert address to lat/lng coordinates using geocoder library."""
    try:
        # Use OpenStreetMap geocoding (free and reliable)
        g = geocoder.osm(address)
        if g.ok:
            return {
                "lat": g.lat,
                "lng": g.lng,
                "formatted_address": g.address
            }
        else:
            # Try with ArcGIS as backup (also free)
            g = geocoder.arcgis(address)
            if g.ok:
                return {
                    "lat": g.lat,
                    "lng": g.lng,
                    "formatted_address": g.address
                }
            else:
                return None
    except Exception as e:
        st.error(f"❌ Geocoding error: {e}")
        return None

def get_location_from_input(location_input, location_type):
    """Get coordinates based on user input type."""
    if location_type == "Address":
        return get_coordinates_from_address_streamlit(location_input)
    elif location_type == "Current Location":
        return get_current_location()
    elif location_type == "Coordinates":
        try:
            lat, lng = map(float, location_input.split(','))
            return {"lat": lat, "lng": lng}
        except:
            return None
    return None

def display_restaurant_card(restaurant):
    """Display a restaurant in a nice card format."""
    with st.container():
        st.markdown("---")
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader(f"🍴 {restaurant['name']}")
            st.write(f"📍 **Address:** {restaurant['address']}")
            st.write(f"⭐ **Rating:** {restaurant.get('rating', 'N/A')}")
            if restaurant.get('categories'):
                st.write(f"🍽️ **Cuisine:** {', '.join(restaurant['categories'])}")
            if restaurant.get('phone'):
                st.write(f"📞 **Phone:** {restaurant['phone']}")
            if restaurant.get('price_level'):
                st.write(f"💰 **Price:** {'$' * len(restaurant['price_level'])}")
        
        with col2:
            menu_url = restaurant.get('menu_url')
            if menu_url and menu_url != "Menu not available":
                st.link_button("📋 View Menu", menu_url, use_container_width=True)
            else:
                st.info("📋 Menu not available")

def main():
    # Header
    st.title("🍽️ Restaurant Finder Dashboard")
    st.write("Find the perfect restaurant based on your preferences!")

    # Show API key status
    if not YELP_API_KEY:
        st.error("❌ Yelp API key not found. Please configure your API keys.")
        return
    
    # Show OpenAI status
    if not OPENAI_API_KEY:
        st.warning("⚠️ OpenAI API key not found. AI features will be limited.")

    # Sidebar for location setup
    with st.sidebar:
        st.header("📍 Set Your Location")
        
        location_type = st.selectbox(
            "How would you like to set your location?",
            ["Address", "Current Location", "Coordinates"]
        )
        
        location_input = ""
        if location_type == "Address":
            location_input = st.text_input(
                "Enter address or city name:", 
                placeholder="e.g., 123 Main St, New York, NY or Times Square, NYC",
                help="You can enter: street address, landmark, city name, or neighborhood"
            )
        elif location_type == "Coordinates":
            location_input = st.text_input("Enter coordinates (lat,lng):", placeholder="e.g., 40.7128,-74.0060")
        
        if st.button("📍 Set Location", type="primary"):
            with st.spinner("Getting location..."):
                if location_type == "Current Location":
                    location_data = get_current_location()
                elif location_type == "Address" and location_input.strip():
                    location_data = get_location_from_input(location_input.strip(), location_type)
                elif location_type == "Coordinates" and location_input.strip():
                    location_data = get_location_from_input(location_input.strip(), location_type)
                else:
                    st.error("❌ Please enter a valid location.")
                    location_data = None
                
                if location_data:
                    st.session_state.location = location_data
                    st.success("✅ Location set successfully!")
                    if location_data.get('formatted_address'):
                        st.write(f"📍 {location_data['formatted_address']}")
                    else:
                        st.write(f"📍 Lat: {location_data['lat']:.4f}, Lng: {location_data['lng']:.4f}")
                else:
                    st.error("❌ Could not set location. Please try again with a different address.")
        
        # Display current location
        if st.session_state.location:
            st.success("✅ Location Ready")
            st.write(f"**Lat:** {st.session_state.location['lat']:.4f}")
            st.write(f"**Lng:** {st.session_state.location['lng']:.4f}")
            if st.session_state.location.get('formatted_address'):
                st.write(f"**Address:** {st.session_state.location['formatted_address']}")

    # Main search interface
    if not st.session_state.location:
        st.warning("⚠️ Please set your location first using the sidebar.")
        return

    # Search form
    with st.form("restaurant_search"):
        st.header("🔍 Search for Restaurants")
        
        col1, col2 = st.columns(2)
        
        with col1:
            user_query = st.text_area(
                "What kind of restaurant are you looking for?",
                placeholder="e.g., Italian restaurant with good pasta, vegan friendly place, cheap Mexican food",
                height=100
            )
        
        with col2:
            # Updated limit to match Yelp API constraint
            limit = st.slider("Number of results", min_value=1, max_value=10, value=10)
            # Show AI critique option only if OpenAI is available
            if OPENAI_API_KEY:
                show_critique = st.checkbox("Show AI critique of results", value=True)
            else:
                show_critique = False
                st.info("🤖 AI critique requires OpenAI API key")
        
        search_button = st.form_submit_button("🔍 Search Restaurants", type="primary", use_container_width=True)
    
    # Perform search
    if search_button and user_query.strip():
        with st.spinner("🔍 Searching for restaurants..."):
            # Get search plan
            plan = plan_search(user_query)
            
            # Show the plan
            with st.expander("📋 Search Plan"):
                st.json(plan)
            
            # Get results
            results = call_yelp(
                st.session_state.location, 
                cuisine=plan.get("cuisine"), 
                budget=plan.get("budget"),
                limit=limit
            )
            
            if results:
                st.session_state.results = results
                st.success(f"✅ Found {len(results)} restaurants!")
                
                # Show critique if enabled and OpenAI is available
                if show_critique and OPENAI_API_KEY:
                    with st.spinner("🤔 Analyzing results..."):
                        critique = critique_results(user_query, plan, results)
                        
                        with st.expander("🤔 AI Analysis"):
                            if critique.get("is_satisfied", True):
                                st.success("✅ Results look good!")
                            else:
                                st.warning(f"⚠️ {critique.get('reason', 'Results may not match your request')}")
                                if critique.get("corrected_plan"):
                                    st.info("💡 Suggested improvements:")
                                    st.json(critique["corrected_plan"])
                            
                            st.json(critique)
            
            else:
                st.error("❌ No restaurants found for your request. Try adjusting your search.")
                st.session_state.results = []
    
    # Display results
    if st.session_state.results:
        st.header(f"🍽️ Restaurant Results ({len(st.session_state.results)} found)")
        
        # Option to view as table or cards
        view_type = st.radio("View as:", ["Cards", "Table"], horizontal=True)
        
        if view_type == "Cards":
            for restaurant in st.session_state.results:
                display_restaurant_card(restaurant)
                
        else:  # Table view
            df_data = []
            for r in st.session_state.results:
                df_data.append({
                    "Name": r['name'],
                    "Rating": r.get('rating', 'N/A'),
                    "Address": r['address'],
                    "Categories": ', '.join(r.get('categories', [])),
                    "Phone": r.get('phone', 'N/A'),
                    "Menu Available": "✅" if r.get('menu_url') and r.get('menu_url') != "Menu not available" else "❌"
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True)
            
            # Show menu links separately for table view
            st.subheader("📋 Menu Links")
            for i, restaurant in enumerate(st.session_state.results):
                menu_url = restaurant.get('menu_url')
                if menu_url and menu_url != "Menu not available":
                    st.markdown(f"**{restaurant['name']}:** [View Menu]({menu_url})")
                else:
                    st.markdown(f"**{restaurant['name']}:** Menu not available")

if __name__ == "__main__":
    main()