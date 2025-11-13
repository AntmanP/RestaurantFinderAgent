import json
from restaurant_tools import call_yelp, get_location_input
import os
from dotenv import load_dotenv
import re

# Optional Hugging Face imports
try:
    from transformers import pipeline
    import torch
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

# Get the directory of this file and load .env from there
current_dir = os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(current_dir, '.env')
load_dotenv(env_file)

# Global model cache
_model_cache = None

def get_hf_model():
    """Load and cache Hugging Face model for text generation"""
    global _model_cache
    
    if _model_cache is not None:
        return _model_cache
    
    if not HF_AVAILABLE:
        return None
    
    try:
        # Use a lightweight model that can run on CPU
        _model_cache = pipeline(
            "text-generation",
            model="microsoft/DialoGPT-small",  # Small, fast model
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device=0 if torch.cuda.is_available() else -1,  # GPU if available, else CPU
        )
        return _model_cache
    except Exception as e:
        print(f"Error loading HF model: {e}")
        return None

def critique_results_hf(user_query, plan, results):
    """Use Hugging Face model for critique"""
    model = get_hf_model()
    
    if not model:
        # Fallback to rule-based approach
        return critique_results_rule_based(user_query, plan, results)
    
    results_text = json.dumps(results[:5], indent=2)  # Limit for token constraints
    
    prompt = f"""Analyze these restaurant results for the query: "{user_query}"

Plan: {json.dumps(plan)}

Results: {results_text}

Are these restaurants relevant? Respond with JSON:
{{"is_satisfied": true/false, "reason": "explanation"}}"""

    try:
        # Generate response
        response = model(prompt, max_length=200, num_return_sequences=1, temperature=0.3)
        
        # Extract generated text
        generated = response[0]['generated_text']
        
        # Try to find JSON in the response
        json_start = generated.find('{')
        json_end = generated.rfind('}') + 1
        
        if json_start != -1 and json_end > json_start:
            json_text = generated[json_start:json_end]
            critique = json.loads(json_text)
            
            # Ensure required fields
            if 'is_satisfied' not in critique:
                critique['is_satisfied'] = True
            if 'reason' not in critique:
                critique['reason'] = "Analysis completed"
            critique['corrected_plan'] = None
            
            return critique
        
    except Exception as e:
        print(f"HF model error: {e}")
    
    # Fallback to rule-based
    return critique_results_rule_based(user_query, plan, results)

def critique_results_rule_based(user_query, plan, results):
    """Rule-based critique as fallback"""
    if not results:
        return {
            "is_satisfied": False,
            "reason": "No restaurants found",
            "corrected_plan": None
        }
    
    # Simple relevance check
    query_lower = user_query.lower()
    relevant_count = 0
    
    for restaurant in results[:5]:
        name_lower = restaurant.get('name', '').lower()
        categories = restaurant.get('categories', [])
        
        # Check if restaurant name or categories match query intent
        if plan.get('cuisine'):
            if plan['cuisine'].lower() in name_lower or \
               any(plan['cuisine'].lower() in cat.lower() for cat in categories):
                relevant_count += 1
                continue
        
        # Check for general relevance
        query_words = [word for word in query_lower.split() if len(word) > 3]
        if any(word in name_lower for word in query_words):
            relevant_count += 1
    
    relevance_ratio = relevant_count / len(results[:5]) if results else 0
    
    if relevance_ratio >= 0.4:  # 40% or more relevant
        return {
            "is_satisfied": True,
            "reason": f"Found {relevant_count} relevant restaurants out of {len(results[:5])}",
            "corrected_plan": None
        }
    else:
        return {
            "is_satisfied": False,
            "reason": f"Only {relevant_count} out of {len(results[:5])} restaurants seem relevant",
            "corrected_plan": None
        }

# Main critique function - tries HF first, falls back to rule-based
def critique_results(user_query, plan, results):
    """Main critique function with fallback strategy"""
    if HF_AVAILABLE:
        return critique_results_hf(user_query, plan, results)
    else:
        return critique_results_rule_based(user_query, plan, results)

def clean_json_block(text):
    """Remove markdown ```json ... ``` wrappers if present."""
    text = re.sub(r"^```(?:json)?", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    return text.strip()

# Rest of the functions remain the same as the rule-based version...
def run_agent(user_query, location):
    """Full loop: plan → execute → critique → replan if needed → optionally scrape menus."""
    print(f"\n🧭 User Query: {user_query}")
    print(f"📍 Searching near: Lat {location['lat']}, Lng {location['lng']}")

    try:
        from planner_agent_cloud import plan_search
    except ImportError:
        from planner_agent import plan_search

    plan = plan_search(user_query)
    print(f"Initial plan{json.dumps(plan, indent=2)}")
    results = call_yelp(location, cuisine=plan.get("cuisine"), budget=plan.get("budget"))

    if not results:
        print("\n❌ No restaurants found for your request.")
        return []
    
    for r in results:
        print(f" - {r['name']} | ({r.get('rating', '?')}⭐) - {r['address']} | Contact Number:{r['phone']}")

    print("\n🤔 Analyzing results...")
    critique = critique_results(user_query, plan, results)
    print(f"📊 Critique: {json.dumps(critique, indent=2)}")
    
    if not critique.get("is_satisfied", True):
        print(f"⚠️ Results may not match your request: {critique.get('reason', 'Unknown reason')}")
        if critique.get("corrected_plan"):
            print(f"💡 Suggested correction: {json.dumps(critique['corrected_plan'], indent=2)}")
    else:
        print("✅ Results look good!")
    
    return results

if __name__ == "__main__":
    print("🍽️ Welcome to the Restaurant Finder Agent!")
    
    location = get_location_input()
    if not location:
        print("❌ Could not determine location. Exiting.")
        exit(1)
    
    while True:
        print("\n" + "="*50)
        print("Options:")
        print("1. Search for restaurants")
        print("2. Change location") 
        print("3. Exit")
        
        choice = input("Choose option (1-3): ").strip()
        
        if choice == "1":
            query = input("\nEnter your restaurant request: ")
            if query.strip():
                run_agent(query, location)
            else:
                print("❌ Please enter a valid restaurant request.")
                
        elif choice == "2":
            new_location = get_location_input()
            if new_location:
                location = new_location
                print("✅ Location updated!")
            else:
                print("❌ Location not changed.")
                
        elif choice == "3":
            print("👋 Goodbye!")
            break
            
        else:
            print("❌ Invalid choice. Please enter 1, 2, or 3.")