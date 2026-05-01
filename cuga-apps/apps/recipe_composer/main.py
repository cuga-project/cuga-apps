"""
Recipe Composer — CUGA Demo App
==============================

Tell the agent what's in your pantry. It tracks ingredients, learns dietary
preferences, looks up rough nutrition for each item, and proposes 3–5 recipes
you can actually cook tonight — with a per-recipe "make / skip" reason.

All tools are inline @tool defs. No MCP servers, no external APIs. Macro
estimates and substitution suggestions come from small static tables baked
into the tool bodies, so this app stands on its own without keys.

Run:
    python main.py
    python main.py --port 28820
    python main.py --provider anthropic

Then open: http://127.0.0.1:28820

Environment variables:
    LLM_PROVIDER          rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL             model name override
    AGENT_SETTING_CONFIG  path to CUGA settings TOML (defaulted in make_agent)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

# ── Path bootstrap — must come before local imports ─────────────────────
_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in (str(_DIR), str(_DEMOS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Third-party (after path bootstrap)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ui import _HTML


# ── Per-thread session store ────────────────────────────────────────────
# thread_id → {pantry, diet, allergies, recipes}
_sessions: dict[str, dict] = {}


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            "pantry":    [],
            "diet":      "",
            "allergies": [],
            "recipes":   [],
        }
    return _sessions[thread_id]


def _append_unique(lst: list[str], value: str) -> None:
    if value and value.lower() not in [v.lower() for v in lst]:
        lst.append(value)


# ── Static lookup tables (the inline "knowledge base") ──────────────────
# Per 100 g — a deliberately compact slice of common pantry staples. Numbers
# are rounded; this is meant to be directional ("how much protein roughly?"),
# not a clinical food database.
_MACROS_PER_100G: dict[str, dict[str, float]] = {
    "chicken breast":   {"calories": 165, "protein": 31, "carbs": 0,  "fat": 3.6},
    "ground beef":      {"calories": 250, "protein": 26, "carbs": 0,  "fat": 17},
    "salmon":           {"calories": 208, "protein": 20, "carbs": 0,  "fat": 13},
    "tofu":             {"calories":  76, "protein": 8,  "carbs": 1.9, "fat": 4.8},
    "egg":              {"calories": 155, "protein": 13, "carbs": 1.1, "fat": 11},
    "rice":             {"calories": 130, "protein": 2.7, "carbs": 28, "fat": 0.3},
    "pasta":            {"calories": 158, "protein": 5.8, "carbs": 31, "fat": 0.9},
    "bread":            {"calories": 265, "protein": 9.0, "carbs": 49, "fat": 3.2},
    "potato":           {"calories":  77, "protein": 2.0, "carbs": 17, "fat": 0.1},
    "sweet potato":     {"calories":  86, "protein": 1.6, "carbs": 20, "fat": 0.1},
    "broccoli":         {"calories":  34, "protein": 2.8, "carbs": 7,  "fat": 0.4},
    "spinach":          {"calories":  23, "protein": 2.9, "carbs": 3.6, "fat": 0.4},
    "tomato":           {"calories":  18, "protein": 0.9, "carbs": 3.9, "fat": 0.2},
    "onion":            {"calories":  40, "protein": 1.1, "carbs": 9.3, "fat": 0.1},
    "garlic":           {"calories": 149, "protein": 6.4, "carbs": 33, "fat": 0.5},
    "carrot":           {"calories":  41, "protein": 0.9, "carbs": 10, "fat": 0.2},
    "olive oil":        {"calories": 884, "protein": 0,   "carbs": 0,  "fat": 100},
    "butter":           {"calories": 717, "protein": 0.9, "carbs": 0.1, "fat": 81},
    "cheese":           {"calories": 402, "protein": 25, "carbs": 1.3, "fat": 33},
    "milk":             {"calories":  42, "protein": 3.4, "carbs": 5.0, "fat": 1.0},
    "yogurt":           {"calories":  59, "protein": 10, "carbs": 3.6, "fat": 0.4},
    "lentils":          {"calories": 116, "protein": 9,  "carbs": 20, "fat": 0.4},
    "chickpeas":        {"calories": 164, "protein": 8.9, "carbs": 27, "fat": 2.6},
    "black beans":      {"calories": 132, "protein": 8.9, "carbs": 24, "fat": 0.5},
    "quinoa":           {"calories": 120, "protein": 4.4, "carbs": 21, "fat": 1.9},
    "oats":             {"calories": 389, "protein": 17, "carbs": 66, "fat": 7},
    "almonds":          {"calories": 579, "protein": 21, "carbs": 22, "fat": 50},
    "peanut butter":    {"calories": 588, "protein": 25, "carbs": 20, "fat": 50},
    "avocado":          {"calories": 160, "protein": 2.0, "carbs": 9,  "fat": 15},
    "banana":           {"calories":  89, "protein": 1.1, "carbs": 23, "fat": 0.3},
    "apple":            {"calories":  52, "protein": 0.3, "carbs": 14, "fat": 0.2},
    "lemon":            {"calories":  29, "protein": 1.1, "carbs": 9,  "fat": 0.3},
    "soy sauce":        {"calories":  53, "protein": 8.1, "carbs": 4.9, "fat": 0.6},
    "honey":            {"calories": 304, "protein": 0.3, "carbs": 82, "fat": 0},
}

# Fast pantry → suggested swap. Keys are ingredient name (lowercase); value
# is a (substitute, "why this works") tuple.
_SUBSTITUTIONS: dict[str, list[tuple[str, str]]] = {
    "butter":     [("olive oil", "1:1 by volume in sautés; lighter mouthfeel"),
                   ("yogurt",   "in baking, 1:1 — denser, tangier crumb")],
    "milk":       [("yogurt", "thin with water 2:1 for sauces"),
                   ("almond milk", "1:1 in most savory dishes")],
    "egg":        [("yogurt + 1/4 tsp baking powder", "binds quickbreads"),
                   ("flax meal + water (1 tbsp + 3 tbsp)", "vegan binder")],
    "cheese":     [("nutritional yeast", "savory, umami, vegan; use ~1/2 the volume")],
    "pasta":      [("rice", "serve as a base under the sauce"),
                   ("spiralized zucchini", "lower-carb noodle stand-in")],
    "rice":       [("quinoa", "1:1, +25% liquid; higher protein"),
                   ("cauliflower rice", "lower-carb stand-in")],
    "bread":      [("lettuce wraps", "for sandwiches and burgers")],
    "ground beef":[("lentils", "cooked + seasoned; great for tacos and chili"),
                   ("mushrooms (chopped)", "for bolognese and shepherd's pie")],
    "chicken breast":[("tofu", "press, then sub 1:1 in stir-fries"),
                      ("chickpeas", "in salads and curries")],
    "soy sauce":  [("tamari", "1:1, gluten-free"),
                   ("coconut aminos", "1:1, lower sodium")],
    "honey":      [("maple syrup", "1:1, vegan")],
}

# Diet → ingredient blocklist. Used by check_diet_compatibility.
_DIET_BLOCKLIST: dict[str, set[str]] = {
    "vegetarian":   {"chicken breast", "ground beef", "salmon"},
    "vegan":        {"chicken breast", "ground beef", "salmon", "egg", "milk",
                     "yogurt", "cheese", "butter", "honey"},
    "pescatarian":  {"chicken breast", "ground beef"},
    "gluten-free":  {"pasta", "bread"},
    "dairy-free":   {"milk", "yogurt", "cheese", "butter"},
    "keto":         {"rice", "pasta", "bread", "potato", "sweet potato",
                     "banana", "apple", "honey", "oats"},
}


# ── Tools ────────────────────────────────────────────────────────────────
def _make_tools():
    from langchain_core.tools import tool

    @tool
    def add_to_pantry(thread_id: str, ingredient: str) -> str:
        """Add an ingredient to the user's pantry for this session.
        Call this whenever the user mentions something they have on hand.

        Args:
            thread_id:  The current session/thread ID (always pass through).
            ingredient: Plain English ingredient name, e.g. "chicken breast",
                        "rice", "olive oil". Normalize to singular, lowercase.
        """
        if not ingredient:
            return json.dumps({"ok": False, "error": "ingredient is empty",
                               "code": "bad_input"})
        session = _get_session(thread_id)
        normalized = ingredient.strip().lower()
        _append_unique(session["pantry"], normalized)
        log.info("[%s] added to pantry: %s", thread_id[:8], normalized)
        return json.dumps({"ok": True, "data": {
            "added": normalized,
            "pantry_size": len(session["pantry"]),
        }})

    @tool
    def remove_from_pantry(thread_id: str, ingredient: str) -> str:
        """Remove an ingredient from the user's pantry — e.g. they ran out.

        Args:
            thread_id:  The current session/thread ID.
            ingredient: Ingredient name to remove (case-insensitive match).
        """
        session = _get_session(thread_id)
        target = (ingredient or "").strip().lower()
        before = len(session["pantry"])
        session["pantry"] = [i for i in session["pantry"] if i.lower() != target]
        return json.dumps({"ok": True, "data": {
            "removed": before != len(session["pantry"]),
            "pantry_size": len(session["pantry"]),
        }})

    @tool
    def list_pantry(thread_id: str) -> str:
        """List the ingredients currently in the user's pantry. Call this at the
        start of a recipe request to see what you have to work with.

        Args:
            thread_id: The current session/thread ID.
        """
        session = _get_session(thread_id)
        return json.dumps({"ok": True, "data": {
            "pantry":     session["pantry"],
            "count":      len(session["pantry"]),
            "diet":       session["diet"] or "no preference",
            "allergies":  session["allergies"],
        }})

    @tool
    def set_diet(thread_id: str, diet: str) -> str:
        """Save the user's dietary preference for this session.

        Args:
            thread_id: The current session/thread ID.
            diet: One of: vegetarian, vegan, pescatarian, gluten-free,
                  dairy-free, keto, omnivore. Use "omnivore" or empty
                  string to clear any prior preference.
        """
        session = _get_session(thread_id)
        d = (diet or "").strip().lower()
        if d in ("", "omnivore", "none"):
            session["diet"] = ""
            return json.dumps({"ok": True, "data": {"diet": "no preference"}})
        if d not in _DIET_BLOCKLIST:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": f"unknown diet '{d}'. Valid: " +
                                        ", ".join(_DIET_BLOCKLIST) + ", omnivore"})
        session["diet"] = d
        return json.dumps({"ok": True, "data": {"diet": d}})

    @tool
    def add_allergy(thread_id: str, ingredient: str) -> str:
        """Mark an ingredient as something the user can't eat. Recipes that include
        any allergen are blocked at suggestion time.

        Args:
            thread_id:  The current session/thread ID.
            ingredient: Ingredient (e.g. "peanut butter", "almonds").
        """
        session = _get_session(thread_id)
        normalized = (ingredient or "").strip().lower()
        if not normalized:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "ingredient is empty"})
        _append_unique(session["allergies"], normalized)
        return json.dumps({"ok": True, "data": {
            "allergies": session["allergies"],
        }})

    @tool
    def estimate_macros(ingredient: str, grams: int = 100) -> str:
        """Look up rough macros for a portion of one ingredient. Static lookup
        table — no network call. Useful for rough nutrition guidance per
        recipe ("about 30 g protein, 700 kcal").

        Args:
            ingredient: Ingredient name (case-insensitive).
            grams:      Portion size in grams (default 100).
        """
        key = (ingredient or "").strip().lower()
        if key not in _MACROS_PER_100G:
            return json.dumps({"ok": False, "code": "not_found",
                               "error": f"no macro data for '{key}'. "
                                        f"Try: {', '.join(sorted(_MACROS_PER_100G)[:8])}…"})
        per100 = _MACROS_PER_100G[key]
        scale = grams / 100.0
        return json.dumps({"ok": True, "data": {
            "ingredient": key,
            "grams":      grams,
            "calories":   round(per100["calories"] * scale, 1),
            "protein_g":  round(per100["protein"] * scale, 1),
            "carbs_g":    round(per100["carbs"]   * scale, 1),
            "fat_g":      round(per100["fat"]     * scale, 1),
        }})

    @tool
    def suggest_substitution(ingredient: str) -> str:
        """Suggest pantry-friendly substitutions for an ingredient the user
        doesn't have. Use this when proposing a recipe that calls for
        something not in the user's pantry.

        Args:
            ingredient: Ingredient to substitute (case-insensitive).
        """
        key = (ingredient or "").strip().lower()
        subs = _SUBSTITUTIONS.get(key, [])
        if not subs:
            return json.dumps({"ok": True, "data": {
                "ingredient": key,
                "substitutes": [],
                "note": "No standard substitutions on file — feel free to "
                        "improvise or ask the user.",
            }})
        return json.dumps({"ok": True, "data": {
            "ingredient": key,
            "substitutes": [{"name": s, "why": w} for s, w in subs],
        }})

    @tool
    def check_diet_compatibility(thread_id: str, ingredients_csv: str) -> str:
        """Check whether a list of ingredients is compatible with the user's
        active diet + allergies. Call this BEFORE proposing a recipe so you
        can flag and substitute problem ingredients up front.

        Args:
            thread_id:       The current session/thread ID.
            ingredients_csv: Comma-separated ingredient names.
        """
        session = _get_session(thread_id)
        items = [i.strip().lower() for i in (ingredients_csv or "").split(",") if i.strip()]
        if not items:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "ingredients_csv is empty"})
        blocked_diet = []
        if session["diet"] in _DIET_BLOCKLIST:
            blocked_diet = [i for i in items if i in _DIET_BLOCKLIST[session["diet"]]]
        blocked_allergy = [i for i in items if i in session["allergies"]]
        return json.dumps({"ok": True, "data": {
            "diet":             session["diet"] or "no preference",
            "blocked_by_diet":  blocked_diet,
            "blocked_by_allergy": blocked_allergy,
            "compatible":       not (blocked_diet or blocked_allergy),
        }})

    @tool
    def save_recipes(thread_id: str, recipes_json: str) -> str:
        """Persist the structured recipe suggestions so the UI can render them
        as cards. Call this EVERY time you produce a set of recipe ideas.

        Args:
            thread_id:    The current session/thread ID.
            recipes_json: A JSON array. Each element must include:
                            title           (str)
                            time_minutes    (int)
                            difficulty      (str: "easy" | "medium" | "hard")
                            uses            (list[str], from the user's pantry)
                            missing         (list[str], items the user needs to buy)
                            calories_est    (int, optional, total per serving)
                            why             (str, one sentence — why suggest this)
                            steps           (list[str], 3–8 short cook steps)
        """
        session = _get_session(thread_id)
        try:
            recipes = json.loads(recipes_json)
            if not isinstance(recipes, list):
                return json.dumps({"ok": False, "code": "bad_input",
                                   "error": "recipes_json must be a JSON array"})
            session["recipes"] = recipes
            log.info("[%s] saved %d recipes", thread_id[:8], len(recipes))
            return json.dumps({"ok": True, "data": {"saved": len(recipes)}})
        except json.JSONDecodeError as exc:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": f"invalid JSON: {exc}"})

    return [
        add_to_pantry, remove_from_pantry, list_pantry,
        set_diet, add_allergy,
        estimate_macros, suggest_substitution, check_diet_compatibility,
        save_recipes,
    ]


# ── System prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
# Recipe Composer

You are a friendly home-cooking assistant. Your job is to learn what's in the
user's pantry, respect their dietary needs, and propose 3–5 cookable recipes
they'd actually enjoy tonight.

## Listening for pantry updates
Whenever the user mentions an ingredient they have, call `add_to_pantry`. Do
this *eagerly* — even if they're just chatting. Same for diet (`set_diet`)
and allergies (`add_allergy`). One call per item.

## When the user asks for ideas
Follow this exact sequence:

1. Call `list_pantry(thread_id=...)` to see what's available.
2. Brainstorm 3–5 candidate dishes that use what they have.
3. For each candidate, list its ingredients and call
   `check_diet_compatibility(ingredients_csv=...)`. If anything is blocked,
   either swap it (`suggest_substitution`) or drop the dish.
4. Optional: call `estimate_macros` for the heaviest 2–3 ingredients of each
   dish so you can fill `calories_est` reasonably (sum across portions).
5. Call `save_recipes(recipes_json=...)` with a JSON array. Each recipe must
   set `uses`, `missing`, `time_minutes`, `difficulty`, `why`, `steps`.
   `missing` is empty for "you have everything" dishes.
6. Reply to the user in plain prose: list each recipe with one-line
   description and the cook time. Mention which pantry items it uses and
   what (if anything) they'd need to buy.

## Rules
- Don't invent ingredient data. If `estimate_macros` returns `not_found`,
  carry on with a vague qualifier ("hearty", "light") rather than guessing.
- Substitutions come from `suggest_substitution`. Don't make them up.
- Stay under 6 recipes. Quality over quantity.
- Keep your reply tight — one paragraph of intro, then the list.

## Thread ID
You will receive the thread_id in every user message (format:
"[thread:<UUID>]"). Always extract it and pass it unchanged to every tool
call that requires thread_id.
"""


# ── Agent factory ────────────────────────────────────────────────────────
def make_agent():
    from cuga.sdk import CugaAgent
    from _llm import create_llm

    _provider_toml = {
        "rits":      "settings.rits.toml",
        "watsonx":   "settings.watsonx.toml",
        "openai":    "settings.openai.toml",
        "anthropic": "settings.openai.toml",
        "litellm":   "settings.litellm.toml",
        "ollama":    "settings.openai.toml",
    }
    provider = (os.getenv("LLM_PROVIDER") or "").lower()
    os.environ.setdefault(
        "AGENT_SETTING_CONFIG",
        _provider_toml.get(provider, "settings.rits.toml"),
    )

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ── Request models ──────────────────────────────────────────────────────
class AskReq(BaseModel):
    question: str
    thread_id: str = ""


# ── HTTP server ──────────────────────────────────────────────────────────
def _web(port: int) -> None:
    import uvicorn

    app = FastAPI(title="Recipe Composer", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _agent = None

    def _get_agent():
        nonlocal _agent
        if _agent is None:
            log.info("Initialising CugaAgent…")
            _agent = make_agent()
            log.info("CugaAgent ready.")
        return _agent

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.post("/ask")
    async def api_ask(req: AskReq):
        thread_id = req.thread_id or str(uuid.uuid4())
        augmented = f"[thread:{thread_id}] {req.question}"
        try:
            agent = _get_agent()
            result = await agent.invoke(augmented, thread_id=thread_id)
            return {"answer": str(result), "thread_id": thread_id}
        except Exception as exc:
            log.exception("Agent invocation failed")
            return JSONResponse(
                status_code=500,
                content={"answer": f"Error: {exc}", "thread_id": thread_id},
            )

    @app.get("/session/{thread_id}")
    async def api_session(thread_id: str):
        return _get_session(thread_id)

    @app.get("/health")
    async def health():
        return {"ok": True}

    print(f"\n  Recipe Composer  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Recipe Composer — CUGA demo app")
    parser.add_argument("--port", type=int, default=28820)
    parser.add_argument(
        "--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"],
    )
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)


if __name__ == "__main__":
    main()
