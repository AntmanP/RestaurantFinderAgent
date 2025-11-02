import json
from openai import OpenAI
from restaurant_tools import call_yelp
import os
from dotenv import load_dotenv
# Get the directory of this file and load .env from there
current_dir = os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(current_dir, '.env')
load_dotenv(env_file)
OPENAI_APIKEY = os.getenv("OPENAI_APIKEY")
client = OpenAI(api_key=OPENAI_APIKEY)

SYSTEM_PROMPT = """
You are a restaurant search planning agent.
You analyze natural language requests about finding places to eat and return
a JSON plan describing how to search.

Always return valid JSON with these keys:
{
  "cuisine": string | null,
  "budget": "low" | "medium" | "high" | null,
  "diet": string | null,
  "use": ["yelp"]
}

Rules:
- Cuisine should be inferred from user query (e.g., sushi, pizza, vegan, indian, mexican, euthopian, mediteranian).
- Budget levels:
    - 'low' → cheap / affordable / under $15
    - 'medium' → normal / moderate / around $30
    - 'high' → expensive / fine dining / upscale
- Diet refers to dietary restrictions (e.g., vegetarian, vegan, gluten-free).
- Always include "use": ["yelp"] unless user explicitly says otherwise.
- Do not include any extra commentary — only return valid JSON.
"""

FEW_SHOT_EXAMPLES = [
    {
        "user": "Find me cheap Italian restaurants nearby",
        "assistant": {
            "cuisine": "italian",
            "budget": "low",
            "diet": None,
            "use": ["yelp"]
        }
    },
    {
        "user": "Show vegan-friendly options in downtown",
        "assistant": {
            "cuisine": None,
            "budget": None,
            "diet": "vegan",
            "use": ["yelp"]
        }
    },
    {
        "user": "Find fancy sushi places near me",
        "assistant": {
            "cuisine": "sushi",
            "budget": "high",
            "diet": None,
            "use": ["yelp"]
        }
    },
    {
        "user": "Find fancy Indian restaurants near me",
        "assistant": {
            "cuisine": "Indian",
            "budget": "high",
            "diet": None,
            "use": ["yelp"]
        }
    },
     {
        "user": "Find fancy Indian vegetarian restaurants near me",
        "assistant": {
            "cuisine": "Indian",
            "budget": "high",
            "diet": "vegetarian",
            "use": ["yelp"]
        }
    }
]


def plan_search(user_query):
    """Generate structured plan for restaurant search."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for ex in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": ex["user"]})
        messages.append({"role": "assistant", "content": json.dumps(ex["assistant"])})

    messages.append({"role": "user", "content": user_query})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.2
    )

    plan_text = response.choices[0].message.content.strip()
    try:
        plan = json.loads(plan_text)
    except json.JSONDecodeError:
        print("⚠️ Could not parse plan. Raw response:")
        print(plan_text)
        plan = {"cuisine": None, "budget": None, "diet": None, "use": ["yelp"]}
    return plan


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
    results = execute_plan(location, plan)

    print("\nRestaurants found:")
    for r in results:
        print(f" - {r['name']} ({r.get('rating','?')}⭐) - {r['address']}")
