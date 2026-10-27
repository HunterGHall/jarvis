import json
import random

MAX_DICE = 100


def roll_dice(sides=6, count=1):
    sides, count = int(sides), int(count)
    if sides < 2 or not 1 <= count <= MAX_DICE:
        return {"error": f"Need at least 2 sides and between 1 and {MAX_DICE} dice."}
    rolls = [random.randint(1, sides) for _ in range(count)]
    return {"dice": f"{count}d{sides}", "rolls": rolls, "total": sum(rolls)}


def flip_coin():
    return {"result": random.choice(["Heads", "Tails"])}


def random_number(minimum=1, maximum=100):
    minimum, maximum = int(minimum), int(maximum)
    if minimum > maximum:
        minimum, maximum = maximum, minimum
    return {"min": minimum, "max": maximum, "result": random.randint(minimum, maximum)}


def pick_random(options):
    options = [str(option) for option in options if str(option).strip()]
    if not options:
        return {"error": "No options given."}
    return {"options": len(options), "picked": random.choice(options)}


if __name__ == "__main__":
    print(json.dumps(roll_dice(20, 2), indent=2))
    print(json.dumps(flip_coin(), indent=2))
    print(json.dumps(random_number(), indent=2))
    print(json.dumps(pick_random(["pizza", "tacos", "sushi"]), indent=2))
