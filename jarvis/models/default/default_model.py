import anthropic
import json
import re
import sys
import time
from configparser import ConfigParser
from pathlib import Path

# Resolve paths relative to this file, not the working directory
MODELS_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = MODELS_DIR.parents[1]
CONVERSATIONS_DIR = MODELS_DIR / "conversations"
CONVERSATIONS_DIR.mkdir(exist_ok=True)

# Create a config template on first run, since the real one is gitignored
CONFIG_PATH = ROOT_DIR / "config.conf"
if not CONFIG_PATH.exists():
    CONFIG_PATH.write_text(
        "[anthropic]\n"
        "anthropic_api_key = YOUR_KEY\n"
        "model = claude-haiku-5-5\n"
        "\n"
        "[personal]\n"
        "name = YOUR_NAME\n"
        "zip_code = YOUR_ZIP\n"
        "\n"
        "[settings]\n"
        "show_cost = False\n",
        encoding="utf-8",
    )
    sys.exit(f"Created {CONFIG_PATH}. Fill in your details and run again.")

# Get API key and model version
config = ConfigParser()
config.read(CONFIG_PATH)
anthropic_api_key = config["anthropic"]["anthropic_api_key"]
client = anthropic.Anthropic(api_key=anthropic_api_key)
model_version = config["anthropic"].get("model", "claude-sonnet-5-5")
show_cost = config.get("settings", "show_cost", fallback="").strip().strip('"').lower() in {"true", "yes", "on", "1"}

# Get training data
with open(MODELS_DIR / "training_data" / "jarvis.txt", "r", encoding="utf-8") as file:
    content = file.read()

# Tell the model who it is talking to
user_name = config.get("personal", "name", fallback="").strip().strip('"')
if user_name:
    content += f"\n\nThe user's name is {user_name}, address them as there name when needed, and if natural."

# Utilities import each other by bare module name (e.g. `from location import ...`),
# so each utility folder has to be on the path
UTILITIES_DIR = MODELS_DIR / "utilities"
for folder in UTILITIES_DIR.iterdir():
    if folder.is_dir():
        sys.path.append(str(folder))

from current_date import get_date
from current_time import get_time
from current_weather import get_weather
from air_quality import get_air_quality
from app_launcher import close_app, open_app
from calculator import calculate, convert_units
from clipboard import read_clipboard, write_clipboard
from dictionary import define
from file_search import FOLDERS, search_files
from finance import convert_currency, get_crypto_price, get_stock_price
from focus_mode import get_do_not_disturb, set_do_not_disturb
from forecast import get_daily_forecast, get_hourly_forecast
from media_control import MEDIA_KEYS, get_now_playing, media_control
from network_status import get_network_status, ping_host
from news import TOPICS as NEWS_TOPICS, get_headlines, search_news
from randomizer import flip_coin, pick_random, random_number, roll_dice
from scores import LEAGUES, get_scores
from sun_moon import get_sun_and_moon
from system_specifications import get_system_specifications
from system_status import get_system_status
from timer import cancel_timer, list_timers, set_timer

UTILITY_FUNCTIONS = {
    "get_headlines": get_headlines,
    "search_news": search_news,
    "calculate": calculate,
    "convert_units": convert_units,
    "roll_dice": roll_dice,
    "flip_coin": flip_coin,
    "random_number": random_number,
    "pick_random": pick_random,
    "get_do_not_disturb": get_do_not_disturb,
    "set_do_not_disturb": set_do_not_disturb,
    "close_app": close_app,
    "open_app": open_app,
    "set_timer": set_timer,
    "list_timers": list_timers,
    "cancel_timer": cancel_timer,
    "read_clipboard": read_clipboard,
    "write_clipboard": write_clipboard,
    "search_files": search_files,
    "get_network_status": get_network_status,
    "ping_host": ping_host,
    "get_air_quality": get_air_quality,
    "get_sun_and_moon": get_sun_and_moon,
    "media_control": media_control,
    "get_now_playing": get_now_playing,
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
        "name": "get_headlines",
        "description": "Get current news headlines by topic, from many outlets. Each story has its source, how long ago it was published, and the other outlets also covering it (more outlets means a bigger story). Use this for 'what's in the news' questions, before web search. 'local' uses the user's zip code. Links are Google News redirects, so use web search if the user wants an article's full details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "enum": list(NEWS_TOPICS), "description": "Defaults to top."},
                "limit": {"type": "integer", "description": "Number of stories, up to 20. Defaults to 8."},
                **_ZIP_CODE,
            },
        },
    },
    {
        "name": "search_news",
        "description": "Search recent news articles about a person, company, event, or subject. Same story format as get_headlines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "days": {"type": "integer", "description": "How many days back to look, up to 30. Defaults to 3."},
                "limit": {"type": "integer", "description": "Number of stories, up to 20. Defaults to 8."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "calculate",
        "description": "Evaluate a math expression exactly. Supports + - * / // ** ^, parentheses, pi, e, and sqrt, sin, cos, tan, log (base 10), ln, abs, round, floor, ceil, factorial, min, max. Convert percentages first, e.g. '15% of 80' becomes '0.15 * 80'.",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    },
    {
        "name": "convert_units",
        "description": "Convert a value between units of length, mass, volume, area, speed, data size, time, or temperature (c, f, k).",
        "input_schema": {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "from_unit": {"type": "string", "description": "e.g. miles, kg, fahrenheit, mph, GB."},
                "to_unit": {"type": "string"},
            },
            "required": ["value", "from_unit", "to_unit"],
        },
    },
    {
        "name": "roll_dice",
        "description": "Roll one or more dice, e.g. 2d20 for a D&D attack.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sides": {"type": "integer", "description": "Sides per die. Defaults to 6."},
                "count": {"type": "integer", "description": "Number of dice, up to 100. Defaults to 1."},
            },
        },
    },
    {
        "name": "flip_coin",
        "description": "Flip a coin: heads or tails.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "random_number",
        "description": "Pick a random whole number between a minimum and maximum, inclusive.",
        "input_schema": {
            "type": "object",
            "properties": {
                "minimum": {"type": "integer", "description": "Defaults to 1."},
                "maximum": {"type": "integer", "description": "Defaults to 100."},
            },
        },
    },
    {
        "name": "pick_random",
        "description": "Pick one item at random from a list of options, e.g. to decide where to eat.",
        "input_schema": {
            "type": "object",
            "properties": {"options": {"type": "array", "items": {"type": "string"}}},
            "required": ["options"],
        },
    },
    {
        "name": "get_do_not_disturb",
        "description": "Check whether Windows Do Not Disturb (focus mode) is on.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "set_do_not_disturb",
        "description": "Turn Windows Do Not Disturb on or off. While on, notification banners are silenced.",
        "input_schema": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
        },
    },
    {
        "name": "close_app",
        "description": "Close an open app the way the X button does, so apps with unsaved work will still prompt. Only close what the user explicitly asked for. The terminal Jarvis runs in and the desktop shell are protected.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "App name, e.g. Spotify, Chrome, Notepad."}},
            "required": ["name"],
        },
    },
    {
        "name": "open_app",
        "description": "Open an application, a website, or one of the user's main folders (Desktop, Documents, Downloads, Pictures, Music, Videos) on their computer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "App name (e.g. Spotify, calculator), a folder name, or an http(s) URL."}
            },
            "required": ["name"],
        },
    },
    {
        "name": "set_timer",
        "description": "Start a countdown timer that alerts the user in the terminal when it finishes. Convert the requested time to seconds.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "number", "description": "Duration in seconds."},
                "label": {"type": "string", "description": "Optional name for the timer, e.g. 'pasta'."},
            },
            "required": ["seconds"],
        },
    },
    {
        "name": "list_timers",
        "description": "List the active timers and how much time each has left.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "cancel_timer",
        "description": "Cancel an active timer by id or label.",
        "input_schema": {
            "type": "object",
            "properties": {
                "timer_id": {"type": "integer"},
                "label": {"type": "string"},
            },
        },
    },
    {
        "name": "read_clipboard",
        "description": "Read the text currently on the user's clipboard.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "write_clipboard",
        "description": "Copy text to the user's clipboard, replacing what's there.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "search_files",
        "description": "Search the user's main folders (Desktop, Documents, Downloads, Pictures, Music, Videos) for files by name and/or extension, newest first. With no query it lists the most recently modified files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to match in the file name."},
                "folder": {"type": "string", "enum": FOLDERS, "description": "Limit the search to one folder."},
                "extension": {"type": "string", "description": "File extension, e.g. pdf."},
                "limit": {"type": "integer", "description": "Max results, up to 50. Defaults to 20."},
            },
        },
    },
    {
        "name": "get_network_status",
        "description": "Get the computer's network status: connectivity, latency, local and public IP, hostname, and Wi-Fi network and signal.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "ping_host",
        "description": "Ping a hostname or IP address and report reachability and latency.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Hostname or IP, e.g. google.com."},
                "count": {"type": "integer", "description": "Number of pings, up to 10. Defaults to 4."},
            },
            "required": ["host"],
        },
    },
    {
        "name": "get_air_quality",
        "description": "Get the current air quality (US AQI, pollutants) and UV index. Defaults to the user's configured zip code.",
        "input_schema": {"type": "object", "properties": _ZIP_CODE},
    },
    {
        "name": "get_sun_and_moon",
        "description": "Get today's sunrise, sunset, and daylight hours, plus the current moon phase. Defaults to the user's configured zip code.",
        "input_schema": {"type": "object", "properties": _ZIP_CODE},
    },
    {
        "name": "media_control",
        "description": "Control media playback and system volume on the user's computer: play/pause, next or previous track, stop, volume up/down, or mute.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": list(MEDIA_KEYS)},
                "times": {
                    "type": "integer",
                    "description": "For volume_up/volume_down only: key presses, each about 2% volume. Defaults to 1.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "get_now_playing",
        "description": "Get the title, artist, album, source app, and playback status of the media currently playing on the user's computer.",
        "input_schema": _NO_INPUT,
    },
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


def _emit_server_tools(message, emit):
    # Server-side tools (web search/fetch) run inside the API call, so they're reported afterwards
    for block in message.content:
        if block.type == "server_tool_use":
            emit({"type": "tool_call", "name": block.name, "input": block.input, "server": True})
        elif block.type.endswith("_tool_result"):
            result = getattr(block, "content", None)
            if isinstance(result, list):
                summary, is_error = f"{len(result)} result{'s' if len(result) != 1 else ''}", False
            else:
                error_type = str(getattr(result, "type", "") or getattr(result, "error_code", ""))
                summary, is_error = error_type or "done", "error" in error_type
            emit(
                {
                    "type": "tool_result",
                    "name": block.type.removesuffix("_tool_result"),
                    "output": summary,
                    "is_error": is_error,
                }
            )


def send_message(user_input, conversation_id="default", on_event=None):
    # on_event gets a dict per tool call/result so a front end can show what the model is doing
    emit = on_event or (lambda _: None)
    history = load_history(conversation_id)
    history.append({"role": "user", "content": user_input})

    # Tool turns are kept in history so later turns can see what was actually looked up
    messages = history

    while True:
        message = _create_message(messages)
        emit({"type": "usage", "model": model_version, "usage": message.usage.model_dump()})
        messages.append({"role": "assistant", "content": _dump_content(message)})
        _emit_server_tools(message, emit)
        if message.stop_reason != "tool_use":
            break

        results = []
        for block in message.content:
            if block.type != "tool_use":
                continue
            emit({"type": "tool_call", "name": block.name, "input": block.input})
            started = time.perf_counter()
            output, is_error = _run_utility(block.name, block.input)
            emit(
                {
                    "type": "tool_result",
                    "name": block.name,
                    "output": output,
                    "is_error": is_error,
                    "seconds": time.perf_counter() - started,
                }
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": results})

    save_history(conversation_id, history)
    return "".join(block.text for block in message.content if block.type == "text")


def _dump_content(message):
    # Plain dicts, so the blocks can be saved as JSON and sent back to the API
    return [block.model_dump(exclude_none=True) for block in message.content]


def _create_message(messages):
    return client.messages.create(
        model=model_version,
        max_tokens=1024,
        system=content,
        messages=messages,
        tools=UTILITY_TOOLS + [
        {
            "name": "web_fetch",
            "type": "web_fetch_20260318",
            "allowed_callers": ["direct"],
        },
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
        {"type": "computer_toolset_20260801"},
        ],
        output_config={"effort": "medium"},
    )


if __name__ == "__main__":
    print(send_message("What GPU do I have, and what is the weather for me, moon phase, and sunrise (sunrise tommorow)?", "demo"))