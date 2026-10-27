import json
import urllib.error
import urllib.parse
import urllib.request

# TheMealDB's free public API; "1" is its shared test key.
BASE_URL = "https://www.themealdb.com/api/json/v1/1"
MAX_INSTRUCTION_CHARS = 3000


def _get_meals(path):
    try:
        with urllib.request.urlopen(f"{BASE_URL}/{path}", timeout=10) as response:
            return json.load(response).get("meals") or []
    except (OSError, ValueError, urllib.error.URLError):
        return []


def _summary(meal):
    return {
        "id": meal["idMeal"],
        "name": meal["strMeal"],
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
    }


def _full_recipe(meal):
    ingredients = []
    for number in range(1, 21):
        ingredient = (meal.get(f"strIngredient{number}") or "").strip()
        if ingredient:
            measure = (meal.get(f"strMeasure{number}") or "").strip()
            ingredients.append(f"{measure} {ingredient}".strip())
    instructions = " ".join((meal.get("strInstructions") or "").split())
    return {
        **_summary(meal),
        "tags": [tag for tag in (meal.get("strTags") or "").split(",") if tag],
        "ingredients": ingredients,
        "instructions": instructions[:MAX_INSTRUCTION_CHARS],
        "video": meal.get("strYoutube") or None,
        "source": meal.get("strSource") or None,
    }


def _find_meals(query):
    query = query.strip()
    meals = _get_meals(f"search.php?s={urllib.parse.quote(query)}")
    if meals:
        return meals
    # Nothing by dish name, so treat the query as a main ingredient.
    ingredient = urllib.parse.quote(query.replace(" ", "_"))
    return _get_meals(f"filter.php?i={ingredient}")


def search_recipes(query, limit=8):
    meals = _find_meals(query)[: max(1, min(int(limit), 20))]
    if not meals:
        return {}
    return {"query": query.strip(), "recipes": [_summary(meal) for meal in meals]}


def get_recipe(query=None, meal_id=None):
    if meal_id:
        meals = _get_meals(f"lookup.php?i={urllib.parse.quote(str(meal_id))}")
    elif query:
        meals = _find_meals(query)
        # Ingredient matches only carry id and name, so fetch the full entry for the top hit.
        if meals and "strInstructions" not in meals[0]:
            meals = _get_meals(f"lookup.php?i={meals[0]['idMeal']}")
    else:
        return {"error": "Give a dish name, an ingredient, or a recipe id."}
    return _full_recipe(meals[0]) if meals else {}


def random_recipe():
    meals = _get_meals("random.php")
    return _full_recipe(meals[0]) if meals else {}


if __name__ == "__main__":
    print(json.dumps(get_recipe("lasagne"), indent=2))
