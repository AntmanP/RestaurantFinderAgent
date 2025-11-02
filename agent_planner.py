"""
agent_planner.py

Agentic LLM planner + executor for "search nearby restaurants" MVP.
- Uses OpenAI-style function calling (replace with your LLM client as needed)
- Provider calls are stubbed; replace `call_google_places_stub`, `call_yelp_stub`
  with real API calls.
"""

import os
import time
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from rapidfuzz import fuzz

# If you use openai, uncomment these:
# import openai
# from dotenv import load_dotenv
# load_dotenv()
# openai.api_key = os.getenv("OPENAI_API_KEY")

# ---- Configuration ----
DEFAULT_MODEL = "gpt-4o-mini"  # replace with your LLM/alias
MIN_RESULTS_THRESHOLD = 3  # if fewer than this, we trigger expansion logic
MAX_EXPANSIONS = 2

# ---- Data classes ----
@dataclass
class UserQuery:
    lat: float
    lon: float
    radius_m: int
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    cuisines: Optional[List[str]] = None
    dietary_restrictions: Optional[List[str]] = None
    preferred_sources: Optional[List[str]] = None
    limit_per_source: int = 8
    expand_on_insufficient_results: bool = True

@dataclass
class Place:
    name: str
    address: str
    lat: float
    lon: float
    price_level: Optional[int]  # normalize 0..4 or None
    cuisines: List[str]
    dietary_tags: List[str]
    rating: Optional[float]  # normalized 0..5
    source: str
    source_id: str
    last_checked_ts: float
    raw: Dict[str,Any]
    distance_m: Optional[int] = None
    confidence: Optional[float] = None

# ---- Function & JSON-schema for planner (use with LLM's function-calling) ----
SEARCH_FUNCTION_SCHEMA = {
    "name": "search_restaurants",
    "description": "Plan a search across providers. Return the provider order, query params, and fallback policy.",
    "parameters": {
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "radius_m": {"type": "integer"},
            "budget_min": {"type": "integer"},
            "budget_max": {"type": "integer"},
            "cuisines": {"type": "array", "items": {"type": "string"}},
            "dietary_restrictions": {"type": "array", "items": {"type": "string"}},
            "preferred_sources": {"type": "array", "items": {"type":"string"}},
            "limit_per_source": {"type": "integer"},
            "expand_on_insufficient_results": {"type": "boolean"}
        },
        "required": ["lat", "lon", "radius_m"]
    }
}

# ---- LLM planner call (wrap your LLM client here) ----
def call_llm_planner(user_query: UserQuery, system_prompt: str = "") -> Dict[str,Any]:
    """
    Call the LLM to produce a planner action. For now we simulate a model response
    to avoid requiring keys. Replace simulation with real openai.ChatCompletion.create
    using function schema above.
    """
    # ---- SIMULATED RESPONSE (replace with real call) ----
    # A real call would look like:
    # resp = openai.ChatCompletion.create(
    #   model=DEFAULT_MODEL,
    #   messages=[{"role":"system","content":system_prompt}, {"role":"user","content": ...}],
    #   functions=[SEARCH_FUNCTION_SCHEMA],
    #   function_call={"name":"search_restaurants"}
    # )
    # result = json.loads(resp["choices"][0]["message"]["function_call"]["arguments"])
    # return result

    # For simulation just return basic plan using the user_query fields:
    result = {
        "lat": user_query.lat,
        "lon": user_query.lon,
        "radius_m": user_query.radius_m,
        "budget_min": user_query.budget_min or 0,
        "budget_max": user_query.budget_max or 4,
        "cuisines": user_query.cuisines or [],
        "dietary_restrictions": user_query.dietary_restrictions or [],
        "preferred_sources": user_query.preferred_sources or ["google", "yelp"],
        "limit_per_source": user_query.limit_per_source,
        "expand_on_insufficient_results": user_query.expand_on_insufficient_results
    }
    return result

# ---- Executor: provider wrappers (stubs here) ----
def call_google_places_stub(args: Dict[str,Any]) -> List[Dict[str,Any]]:
    """Simulate Google Places responses. Replace with real API call and mapping."""
    # Simulate some places near the coordinates.
    now = time.time()
    return [
        {
            "provider": "google",
            "id": "g_1",
            "name": "Luigi's Italian",
            "address": "123 Pasta St",
            "lat": args["lat"] + 0.001,
            "lon": args["lon"] + 0.0012,
            "price_level": 2,
            "types": ["restaurant","italian"],
            "rating": 4.5,
            "raw": {"sim": True},
            "ts": now
        },
        {
            "provider": "google",
            "id": "g_2",
            "name": "Green Leaf Vegetarian",
            "address": "5 Garden Ave",
            "lat": args["lat"] + 0.0005,
            "lon": args["lon"] - 0.0006,
            "price_level": 1,
            "types": ["restaurant","vegetarian"],
            "rating": 4.2,
            "raw": {"sim": True},
            "ts": now
        }
    ]

def call_yelp_stub(args: Dict[str,Any]) -> List[Dict[str,Any]]:
    now = time.time()
    return [
        {
            "provider": "yelp",
            "id": "y_9",
            "name": "Luigi's Italian",
            "address": "123 Pasta St",
            "lat": args["lat"] + 0.00102,
            "lon": args["lon"] + 0.00118,
            "price": "$$",
            "categories": ["italian","pizza"],
            "rating": 4.0,
            "raw": {"sim": True},
            "ts": now
        },
        {
            "provider": "yelp",
            "id": "y_11",
            "name": "Tiny Taco",
            "address": "88 Salsa Blvd",
            "lat": args["lat"] - 0.0015,
            "lon": args["lon"] - 0.0009,
            "price": "$",
            "categories": ["mexican"],
            "rating": 4.1,
            "raw": {"sim": True},
            "ts": now
        }
    ]

# ---- Normalization, dedupe, and merge ----
def normalize_provider_item(item: Dict[str,Any]) -> Place:
    """Map provider-specific fields to Place dataclass."""
    provider = item.get("provider", "unknown")
    name = item.get("name")
    address = item.get("address", "")
    lat = float(item.get("lat"))
    lon = float(item.get("lon"))
    # price normalization:
    price_level = None
    if "price_level" in item:
        price_level = int(item["price_level"])
    elif "price" in item:
        # Yelp style: "$$$" -> 3
        price_level = len(item["price"])
    cuisines = []
    if "types" in item:
        cuisines = item["types"]
    if "categories" in item:
        cuisines = cuisines + item["categories"]
    dietary_tags = []
    rating = item.get("rating")
    source = provider
    source_id = item.get("id") or item.get("place_id") or ""
    last_checked_ts = item.get("ts", time.time())
    p = Place(
        name=name,
        address=address,
        lat=lat,
        lon=lon,
        price_level=price_level,
        cuisines=list(set([c.lower() for c in cuisines if isinstance(c,str)])),
        dietary_tags=dietary_tags,
        rating=float(rating) if rating else None,
        source=source,
        source_id=source_id,
        last_checked_ts=last_checked_ts,
        raw=item,
        distance_m=None,
        confidence=None
    )
    return p

def dedupe_and_merge(places: List[Place], dedupe_threshold: int = 85) -> List[Place]:
    """
    Deduplicate by fuzzy name + proximity.
    If within ~30m and fuzzy name > threshold, merge sources.
    """
    merged: List[Place] = []
    for p in places:
        found = False
        for m in merged:
            name_sim = fuzz.token_sort_ratio(p.name, m.name)
            # Quick geospatial closeness (rough — convert lat/lon to meters approx)
            approx_dx = abs(p.lat - m.lat) * 111000
            approx_dy = abs(p.lon - m.lon) * 111000
            dist = (approx_dx**2 + approx_dy**2) ** 0.5
            if name_sim >= dedupe_threshold and dist < 40:
                # merge: keep best rating, union cuisines, add provenance
                m.cuisines = list(set(m.cuisines + p.cuisines))
                m.dietary_tags = list(set(m.dietary_tags + p.dietary_tags))
                if p.rating and (m.rating is None or p.rating > m.rating):
                    m.rating = p.rating
                # attach provenance by keeping raw results list
                if "_merged_raw" not in m.raw:
                    m.raw["_merged_raw"] = [m.raw]
                m.raw["_merged_raw"].append(p.raw)
                found = True
                break
        if not found:
            merged.append(p)
    return merged

# ---- Scoring / ranking ----
def compute_scores(places: List[Place], user_query: UserQuery) -> None:
    """
    Attach a confidence score (0..1) and distance estimate.
    This is a simple hybrid of exact-match filters and rating/distance heuristics.
    """
    for p in places:
        # distance estimate
        dx = abs(p.lat - user_query.lat) * 111000
        dy = abs(p.lon - user_query.lon) * 111000
        dist = int((dx**2 + dy**2) ** 0.5)
        p.distance_m = dist

        # filter match boolean weight
        match_score = 1.0
        if user_query.cuisines:
            if not any(c.lower() in p.cuisines for c in user_query.cuisines):
                match_score *= 0.6
        if user_query.dietary_restrictions:
            if not any(d.lower() in p.dietary_tags for d in user_query.dietary_restrictions):
                match_score *= 0.85

        rating_score = (p.rating or 3.0) / 5.0
        distance_penalty = max(0.0, 1 - (dist / max(1, user_query.radius_m * 2)))
        price_ok = True
        if user_query.budget_min is not None:
            if p.price_level is None or p.price_level < user_query.budget_min:
                price_ok = False
        if user_query.budget_max is not None:
            if p.price_level is None or p.price_level > user_query.budget_max:
                price_ok = False

        price_score = 1.0 if price_ok else 0.7

        # combine
        p.confidence = round((0.4 * match_score) + (0.3 * rating_score) + (0.2 * distance_penalty) + (0.1 * price_score), 3)

    # sort in-place by confidence desc then rating
    places.sort(key=lambda x: (x.confidence or 0, x.rating or 0), reverse=True)

# ---- Agent orchestrator ----
def run_agent_search(user_query: UserQuery, max_expansions: int = MAX_EXPANSIONS) -> Dict[str,Any]:
    # 1) Planner: ask LLM which sources to call and params:
    planner_args = call_llm_planner(user_query)
    # 2) Executor: call providers in planner_args['preferred_sources'] order
    results_raw = []
    for src in planner_args.get("preferred_sources", []):
        if src == "google":
            results_raw += call_google_places_stub(planner_args)
        elif src == "yelp":
            results_raw += call_yelp_stub(planner_args)
        else:
            # placeholder for future providers
            pass

    # 3) Normalize
    places = [normalize_provider_item(r) for r in results_raw]
    # 4) Dedupe and merge
    places = dedupe_and_merge(places)
    # 5) Score
    compute_scores(places, user_query)

    # 6) If not enough results and expansion allowed, expand radius and retry (deterministic fallback loop)
    expansions = 0
    while len(places) < MIN_RESULTS_THRESHOLD and user_query.expand_on_insufficient_results and expansions < max_expansions:
        expansions += 1
        # Expand radius by 1.5x
        user_query.radius_m = int(user_query.radius_m * 1.5)
        print(f"[agent] insufficient results, expanding radius to {user_query.radius_m}m (expansion {expansions})")
        # Re-run provider calls (simple approach; in production consider incremental)
        results_raw = []
        for src in planner_args.get("preferred_sources", []):
            if src == "google":
                results_raw += call_google_places_stub(planner_args)
            elif src == "yelp":
                results_raw += call_yelp_stub(planner_args)
        places = [normalize_provider_item(r) for r in results_raw]
        places = dedupe_and_merge(places)
        compute_scores(places, user_query)

    # 7) Build final structured response with provenance
    final = []
    for p in places:
        final.append({
            "name": p.name,
            "address": p.address,
            "lat": p.lat,
            "lon": p.lon,
            "price_level": p.price_level,
            "cuisines": p.cuisines,
            "dietary_tags": p.dietary_tags,
            "rating": p.rating,
            "source": p.source,
            "source_id": p.source_id,
            "last_checked_ts": p.last_checked_ts,
            "distance_m": p.distance_m,
            "confidence": p.confidence,
            "raw_preview": {k: v for k, v in (p.raw.items() if isinstance(p.raw, dict) else [])}
        })
    metadata = {
        "planner_args": planner_args,
        "expansions": expansions,
        "timestamp": time.time(),
        "num_results": len(final)
    }
    return {"results": final, "meta": metadata}

# ---- Demo/Test run ----
def demo():
    q = UserQuery(
        lat=40.7128,
        lon=-74.0060,
        radius_m=800,
        budget_min=1,
        budget_max=3,
        cuisines=["italian"],
        dietary_restrictions=["vegetarian"],
        preferred_sources=["google","yelp"],
        limit_per_source=8,
        expand_on_insufficient_results=True
    )
    out = run_agent_search(q)
    print(json.dumps(out, indent=2, default=str))

if __name__ == "__main__":
    demo()
