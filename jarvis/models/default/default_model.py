import anthropic
import json
import re
import sys
from configparser import ConfigParser
from pathlib import Path

# Resolve paths relative to this file, not the working directory
MODELS_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = MODELS_DIR.parents[1]
CONVERSATIONS_DIR = MODELS_DIR / "conversations"
CONVERSATIONS_DIR.mkdir(exist_ok=True)

# Get API key
config = ConfigParser()
config.read(ROOT_DIR / "config.conf")
anthropic_api_key = config["anthropic"]["anthropic_api_key"]
client = anthropic.Anthropic(api_key=anthropic_api_key)

# Get training data
with open(MODELS_DIR / "training_data" / "jarvis.txt", "r", encoding="utf-8") as file:
    content = file.read()

# Utilities import each other by bare module name (e.g. `from location import ...`),
# so each utility folder has to be on the path
UTILITIES_DIR = MODELS_DIR / "utilities"
for folder in UTILITIES_DIR.iterdir():
    if folder.is_dir():
        sys.path.append(str(folder))

from current_date import get_date
from current_time import get_time
from current_weather import get_weather
from dictionary import define
from finance import convert_currency, get_crypto_price, get_stock_price
from forecast import get_daily_forecast, get_hourly_forecast
from scores import LEAGUES, get_scores
from system_specifications import get_system_specifications
from system_status import get_system_status

UTILITY_FUNCTIONS = {
    "get_daily_forecast": get_daily_forecast,
    "get_hourly_forecast": get_hourly_forecast,
    "get_stock_price": get_stock_price,
    "get_crypto_price": get_crypto_price,
    "convert_currency": convert_currency,
    "get_scores": get_scores,
    "define": define,
    "get_time": get_time,
    "get_date": get_date,
    "get_weather": get_weather,
    "get_system_specifications": get_system_specifications,
    "get_system_status": get_system_status,
}

_NO_INPUT = {"type": "object", "properties": {}}

_ZIP_CODE = {
    "zip_code": {
        "type": "string",
        "description": "Optional US zip code to check instead of the user's own.",
    }
}

UTILITY_TOOLS = [
    {
        "name": "get_daily_forecast",
        "description": "Get the multi-day weather forecast (high/low, conditions, rain chance, wind, sunrise, sunset). Defaults to the user's configured zip code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days, 1-16. Defaults to 7."},
                **_ZIP_CODE,
            },
        },
    },
    {
        "name": "get_hourly_forecast",
        "description": "Get the hour-by-hour weather forecast starting from the current hour. Defaults to the user's configured zip code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "Number of hours, up to 48. Defaults to 12."},
                **_ZIP_CODE,
            },
        },
    },
    {
        "name": "get_stock_price",
        "description": "Get the current price and daily change for a stock or ETF ticker symbol.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Ticker symbol, e.g. AAPL."}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_crypto_price",
        "description": "Get the current price and 24-hour change for a cryptocurrency.",
        "input_schema": {
            "type": "object",
            "properties": {
                "coin_id": {"type": "string", "description": "CoinGecko coin id, e.g. bitcoin, ethereum, dogecoin. Defaults to bitcoin."},
                "currency": {"type": "string", "description": "Fiat currency code, e.g. usd. Defaults to usd."},
            },
        },
    },
    {
        "name": "convert_currency",
        "description": "Convert an amount between two fiat currencies at the latest exchange rate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "from_currency": {"type": "string", "description": "ISO currency code, e.g. USD."},
                "to_currency": {"type": "string", "description": "ISO currency code, e.g. EUR."},
            },
            "required": ["amount", "from_currency", "to_currency"],
        },
    },
    {
        "name": "get_scores",
        "description": "Get today's live and recent sports scores for a league, optionally filtered to one team.",
        "input_schema": {
            "type": "object",
            "properties": {
                "league": {"type": "string", "enum": list(LEAGUES), "description": "Defaults to nfl."},
                "team": {"type": "string", "description": "Optional team name to filter by, e.g. Chiefs."},
            },
        },
    },
    {
        "name": "define",
        "description": "Look up an English word: definitions, pronunciation, examples, synonyms, and antonyms.",
        "input_schema": {
            "type": "object",
            "properties": {"word": {"type": "string"}},
            "required": ["word"],
        },
    },
    {
        "name": "get_time",
        "description": "Get the current local time.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "get_date",
        "description": "Get the current local date (MM/DD/YYYY).",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "get_weather",
        "description": "Get the current weather. Defaults to the user's configured zip code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "zip_code": {
                    "type": "string",
                    "description": "Optional US zip code to check instead of the user's own.",
                }
            },
        },
    },
    {
        "name": "get_system_specifications",
        "description": "Get the computer's hardware and OS specifications (CPU, memory, GPUs, disks, motherboard, BIOS).",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "get_system_status",
        "description": "Get the computer's live status: CPU usage, memory, disk usage, uptime, battery, and top processes.",
        "input_schema": _NO_INPUT,
    },
]



def _conversation_path(conversation_id):
    # Reject ids that could escape the conversations directory
    if not re.fullmatch(r"[\w-]+", conversation_id):
        raise ValueError(f"Invalid conversation id: {conversation_id!r}")
    return CONVERSATIONS_DIR / f"{conversation_id}.json"


def load_history(conversation_id):
    path = _conversation_path(conversation_id)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_history(conversation_id, history):
    _conversation_path(conversation_id).write_text(
        json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _run_utility(name, tool_input):
    function = UTILITY_FUNCTIONS.get(name)
    if function is None:
        return f"Unknown tool: {name}", True
    try:
        return json.dumps(function(**tool_input), ensure_ascii=False), False
    except Exception as error:
        return f"{type(error).__name__}: {error}", True


def send_message(user_input, conversation_id="default"):
    history = load_history(conversation_id)
    history.append({"role": "user", "content": user_input})

    # Tool turns stay local; only the final text reply is saved to history
    messages = list(history)

    while True:
        message = _create_message(messages)
        if message.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": message.content})
        results = []
        for block in message.content:
            if block.type != "tool_use":
                continue
            output, is_error = _run_utility(block.name, block.input)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": results})

    reply = "".join(block.text for block in message.content if block.type == "text")
    history.append({"role": "assistant", "content": reply})
    save_history(conversation_id, history)
    return reply


def _create_message(messages):
    return client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=1024,
        system=content,
        messages=messages,
        tools=UTILITY_TOOLS + [
        {
            "name": "web_fetch",
            "type": "web_fetch_20260318",
            "allowed_callers": ["direct"],
        },
        {"type": "bash_20250124", "name": "bash"},
        {
            "type": "browser_toolset_20260801",
            "configs": {
                "javascript_exec": {"enabled": True},
                "file_upload": {"enabled": True},
                "read_console": {"enabled": True},
                "read_network": {"enabled": True},
            },
        },
        {
            "name": "web_search",
            "type": "web_search_20260318",
            "allowed_callers": ["direct"],
        },
        ],
        output_config={"effort": "medium"},
    )


if __name__ == "__main__":
    print(send_message("What GPU do I have, and what is the weather for me?", "demo"))