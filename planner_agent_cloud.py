import json
import re
from restaurant_tools import call_yelp
from transformers import pipeline
import torch

# Initialize the model pipeline once (cached)
def load_model():
    """Load and cache the Hugging Face model"""
    try:
        # Use a smaller, faster model that works well for JSON generation
        generator = pipeline(
            "text-generation",
            model="microsoft/DialoGPT-medium",
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )
        return generator
    except Exception as e:
        print(f"Error loading model: {e}")
        return None

def parse_cuisine_and_budget(user_query):
    """Simple rule-based parsing as fallback or primary method"""
    query_lower = user_query.lower()
    
    # Cuisine detection
    cuisines = {
        'italian': ['italian', 'pizza', 'pasta', 'spaghetti'],
        'chinese': ['chinese', 'dim sum', 'noodles'],
        'mexican': ['mexican', 'tacos', 'burrito', 'quesadilla'],
        'indian': ['indian', 'curry', 'naan', 'tandoori'],
        'japanese': ['japanese', 'sushi', 'ramen', 'teriyaki'],
        'thai': ['thai', 'pad thai'],
        'mediterranean': ['mediterranean', 'greek', 'hummus'],
        'american': ['american', 'burger', 'bbq', 'steak'],
        'french': ['french', 'croissant', 'baguette']
    }
    
    detected_cuisine = None
    for cuisine, keywords in cuisines.items():
        if any(keyword in query_lower for keyword in keywords):
            detected_cuisine = cuisine
            break
    
    # Budget detection
    budget = None
    if any(word in query_lower for word in ['cheap', 'affordable', 'budget', 'inexpensive', 'under']):
        budget = 'low'
    elif any(word in query_lower for word in ['expensive', 'fancy', 'fine dining', 'upscale', 'high-end']):
        budget = 'high'
    elif any(word in query_lower for word in ['moderate', 'mid-range', 'average']):
        budget = 'medium'
    
    # Diet detection
    diet = None
    if any(word in query_lower for word in ['vegan', 'plant-based']):
        diet = 'vegan'
    elif any(word in query_lower for word in ['vegetarian', 'veggie']):
        diet = 'vegetarian'
    elif any(word in query_lower for word in ['gluten-free', 'gluten free']):
        diet = 'gluten-free'
    
    return {
        "cuisine": detected_cuisine,
        "budget": budget,
        "diet": diet,
        "use": ["yelp"]
    }

def plan_search(user_query):
    """Generate structured plan for restaurant search using rule-based approach."""
    try:
        # Use rule-based parsing - it's actually quite effective for this use case
        plan = parse_cuisine_and_budget(user_query)
        return plan
        
    except Exception as e:
        print(f"Error in plan_search: {e}")
        # Ultimate fallback
        return {"cuisine": None, "budget": None, "diet": None, "use": ["yelp"]}

def execute_plan(location, plan):
    """Call Yelp with plan fields."""
    print(f"Executing plan: {plan}")
    return call_yelp(
        location,
        cuisine=plan.get("cuisine") or plan.get("diet"),
        budget=plan.get("budget")
    )

if __name__ == "__main__":
    user_query = input("Enter your restaurant request: ")
    location = {"lat": 40.748817, "lng": -73.985428}  # Manhattan

    plan = plan_search(user_query)
    print(f"Plan: {plan}")
    results = execute_plan(location, plan)

    print("\nRestaurants found:")
    for r in results:
        print(f" - {r['name']} ({r.get('rating','?')}) - {r['address']}")