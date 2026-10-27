import ast
import json
import math
import operator

BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

FUNCTIONS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "radians": math.radians,
    "degrees": math.degrees,
    "log": math.log10,
    "ln": math.log,
    "log2": math.log2,
    "exp": math.exp,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": math.factorial,
    "min": min,
    "max": max,
}

CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}

MAX_EXPONENT = 1000


def _evaluate(node):
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in CONSTANTS:
        return CONSTANTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPERATORS:
        return UNARY_OPERATORS[type(node.op)](_evaluate(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY_OPERATORS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        # Stops things like 9**9**9 from hanging the process.
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise ValueError("Exponent too large.")
        return BINARY_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
        return FUNCTIONS[node.func.id](*[_evaluate(arg) for arg in node.args])
    raise ValueError("Unsupported expression.")


def calculate(expression):
    cleaned = expression.strip().replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", "")
    try:
        result = _evaluate(ast.parse(cleaned, mode="eval"))
    except ZeroDivisionError:
        return {"error": "Division by zero."}
    except (SyntaxError, ValueError, TypeError, OverflowError) as error:
        return {"error": f"Couldn't evaluate '{expression}': {error}"}
    if isinstance(result, float):
        result = round(result, 10)
        if result == int(result) and abs(result) < 1e15:
            result = int(result)
    return {"expression": expression, "result": result}


# Each category maps a canonical unit to (factor to the category's base unit, aliases).
UNITS = {
    "length": {
        "mm": (0.001, ["millimeter", "millimetre"]),
        "cm": (0.01, ["centimeter", "centimetre"]),
        "m": (1, ["meter", "metre"]),
        "km": (1000, ["kilometer", "kilometre"]),
        "in": (0.0254, ["inch", "inches"]),
        "ft": (0.3048, ["foot", "feet"]),
        "yd": (0.9144, ["yard"]),
        "mi": (1609.344, ["mile"]),
        "nmi": (1852, ["nautical mile"]),
    },
    "mass": {
        "mg": (1e-6, ["milligram"]),
        "g": (0.001, ["gram"]),
        "kg": (1, ["kilogram", "kilo"]),
        "oz": (0.028349523125, ["ounce"]),
        "lb": (0.45359237, ["pound", "lbs"]),
        "st": (6.35029318, ["stone"]),
        "ton": (907.18474, ["us ton", "short ton"]),
        "tonne": (1000, ["metric ton"]),
    },
    "volume": {
        "ml": (0.001, ["milliliter", "millilitre"]),
        "l": (1, ["liter", "litre"]),
        "tsp": (0.00492892159375, ["teaspoon"]),
        "tbsp": (0.01478676478125, ["tablespoon"]),
        "fl oz": (0.0295735295625, ["fluid ounce", "floz"]),
        "cup": (0.2365882365, []),
        "pt": (0.473176473, ["pint"]),
        "qt": (0.946352946, ["quart"]),
        "gal": (3.785411784, ["gallon"]),
    },
    "area": {
        "sq m": (1, ["square meter", "square metre", "m2"]),
        "sq km": (1e6, ["square kilometer", "km2"]),
        "sq ft": (0.09290304, ["square foot", "square feet", "ft2"]),
        "sq in": (0.00064516, ["square inch", "square inches"]),
        "sq mi": (2589988.110336, ["square mile"]),
        "acre": (4046.8564224, []),
        "hectare": (10000, ["ha"]),
    },
    "speed": {
        "m/s": (1, ["meters per second", "mps"]),
        "km/h": (1 / 3.6, ["kph", "kmh", "kilometers per hour"]),
        "mph": (0.44704, ["miles per hour", "mi/h"]),
        "knot": (1852 / 3600, ["kt", "kn"]),
        "ft/s": (0.3048, ["feet per second", "fps"]),
    },
    "data": {
        "byte": (1, ["bytes"]),
        "kb": (1000, ["kilobyte"]),
        "mb": (1000**2, ["megabyte"]),
        "gb": (1000**3, ["gigabyte"]),
        "tb": (1000**4, ["terabyte"]),
        "kib": (1024, ["kibibyte"]),
        "mib": (1024**2, ["mebibyte"]),
        "gib": (1024**3, ["gibibyte"]),
        "tib": (1024**4, ["tebibyte"]),
    },
    "time": {
        "ms": (0.001, ["millisecond"]),
        "s": (1, ["sec", "second"]),
        "min": (60, ["minute"]),
        "hr": (3600, ["h", "hour"]),
        "day": (86400, ["d"]),
        "week": (604800, ["wk"]),
        "year": (31557600, ["yr"]),
    },
}

TEMPERATURE_ALIASES = {
    "c": "c", "celsius": "c", "centigrade": "c",
    "f": "f", "fahrenheit": "f",
    "k": "k", "kelvin": "k",
}

LOOKUP = {}
for _category, _units in UNITS.items():
    for _name, (_factor, _aliases) in _units.items():
        for _alias in [_name, *_aliases]:
            LOOKUP[_alias] = (_category, _name)


def _normalize(unit):
    unit = unit.strip().lower().replace("°", "").replace("degrees ", "").replace("degree ", "")
    candidates = [unit, unit.rstrip("s"), unit.removesuffix("es")]
    for candidate in candidates:
        if candidate in TEMPERATURE_ALIASES:
            return "temperature", TEMPERATURE_ALIASES[candidate]
        if candidate in LOOKUP:
            return LOOKUP[candidate]
    return None


def _to_celsius(value, unit):
    return {"c": value, "f": (value - 32) * 5 / 9, "k": value - 273.15}[unit]


def _from_celsius(value, unit):
    return {"c": value, "f": value * 9 / 5 + 32, "k": value + 273.15}[unit]


def convert_units(value, from_unit, to_unit):
    source, target = _normalize(from_unit), _normalize(to_unit)
    if not source:
        return {"error": f"Unknown unit: {from_unit}"}
    if not target:
        return {"error": f"Unknown unit: {to_unit}"}
    if source[0] != target[0]:
        return {"error": f"Can't convert {source[0]} to {target[0]}."}

    category = source[0]
    if category == "temperature":
        result = _from_celsius(_to_celsius(value, source[1]), target[1])
    else:
        units = UNITS[category]
        result = value * units[source[1]][0] / units[target[1]][0]
    return {
        "value": value,
        "from": source[1],
        "to": target[1],
        "result": round(result, 6),
        "category": category,
    }


if __name__ == "__main__":
    print(json.dumps(calculate("sqrt(144) + 2^3 * 1.5"), indent=2))
    print(json.dumps(convert_units(72, "fahrenheit", "celsius"), indent=2))
