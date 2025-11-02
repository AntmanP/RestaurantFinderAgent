import json
from openai import OpenAI
from planner_agent import plan_search
from restaurant_tools import call_yelp
import os
from dotenv import load_dotenv
import re

# Get the directory of this file and load .env from there
current_dir = os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(current_dir, '.env')
load_dotenv(env_file)
OPENAI_APIKEY = os.getenv("OPENAI_APIKEY")
client = OpenAI(api_key=OPENAI_APIKEY)

CRITIQUE_PROMPT = """
You are a restaurant results critic.

You receive:
- The original user query
- The search plan (cuisine, budget, diet)
- The list of restaurants returned (with name, rating, and address)

Your task:
1. Check if the restaurants truly match the cuisine and dietary intent.
2. If fewer than 3 are relevant or most are off-topic (wrong cuisine or unrelated),
   suggest a corrected plan.

Return JSON with these keys:
{
  "is_satisfied": true | false,
  "reason": string,
  "corrected_plan": {
     "cuisine": string | None,
     "budget": "low" | "medium" | "high" | None,
     "diet": string | None,
     "use": ["yelp"]
  } | None
}
"""

def critique_results(user_query, plan, results):
    """Ask LLM to verify if Yelp results match the intent."""
    results_text = json.dumps(results[:8], indent=2)
    messages = [
        {"role": "system", "content": CRITIQUE_PROMPT},
        {"role": "user", "content": f"User query: {user_query}\n\nPlan: {json.dumps(plan)}\n\nResults:\n{results_text}"}
    ]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.3
    )

    critique_text = response.choices[0].message.content.strip()
    try:
        cleaned = clean_json_block(critique_text)
        critique = json.loads(cleaned)
    except json.JSONDecodeError:
        print("⚠️ Could not parse critique. Raw:")
        print(critique_text)
        critique = {"is_satisfied": True, "reason": "Parse failed", "corrected_plan": None}

    return critique

def clean_json_block(text):
    """Remove markdown ```json ... ``` wrappers if present."""
    # remove code fences
    text = re.sub(r"^```(?:json)?", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    return text.strip()


def run_agent(user_query, location):
    """Full loop: plan → execute → critique → replan if needed."""
    print(f"\n🧭 User Query: {user_query}")

    # Step 1 — initial plan + search
    plan = plan_search(user_query)
    results = call_yelp(location, cuisine=plan.get("cuisine"), budget=plan.get("budget"))

    # Step 2 — handle empty initial results
    if not results:
        print("\n❌ No restaurants found for your request.")
        return []
     
    for r in results:
      print(f" - {r['name']} | ({r.get('rating', '?')}⭐) - {r['address']} | Contact Number:{r['phone']}")

    # Step 3 — critique the results
    critique = critique_results(user_query, plan, results)
    print(f"\n🔎 Critique: {critique.get('reason', 'No reason provided')}")

    # Step 4 — if critique says “not satisfied”, handle replan
    if not critique.get("is_satisfied"):
        corrected = critique.get("corrected_plan")
        if corrected:
            print("\n⚙️ Replanning based on critique...")
            results = call_yelp(location, cuisine=corrected.get("cuisine"), budget=corrected.get("budget"))
            plan = corrected

            # Step 5 — if still no results, bail out gracefully
            if not results:
                print("\n❌ No restaurants found after replanning.")
                return []
        else:
            print("\n❌ Critique returned no valid correction. Stopping.")
            return []

    # Step 6 — print final results
    print(f"\n✅ Final Results:{plan['cuisine']}")
    for r in results:
        print(f" - {r['name']} | ({r.get('rating', '?')}⭐) - {r['address']} | Contact Number:{r['phone']}")
    return results



if __name__ == "__main__":
    location = {"lat": 40.748817, "lng": -73.985428} # location to be set from the application you are making the request from
    query = input("Enter your restaurant request: ") # add conditions like 'should be open', 'can we go over menu',
    run_agent(query, location)
