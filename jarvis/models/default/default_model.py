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
        "zip_code = YOUR_ZIP\n",
        encoding="utf-8",
    )
    sys.exit(f"Created {CONFIG_PATH}. Fill in your details and run again.")

# Get API key and model version
config = ConfigParser()
config.read(CONFIG_PATH)
anthropic_api_key = config["anthropic"]["anthropic_api_key"]
client = anthropic.Anthropic(api_key=anthropic_api_key)
model_version = config["anthropic"].get("model", "claude-sonnet-5-5")

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
from app_launcher import open_app
from clipboard import read_clipboard, write_clipboard
from dictionary import define
from file_search import FOLDERS, search_files
from finance import convert_currency, get_crypto_price, get_stock_price
from forecast import get_daily_forecast, get_hourly_forecast
from media_control import MEDIA_KEYS, get_now_playing, media_control
from network_status import get_network_status, ping_host
from scores import LEAGUES, get_scores
from sun_moon import get_sun_and_moon
from system_specifications import get_system_specifications
from system_status import get_system_status
from timer import cancel_timer, list_timers, set_timer

UTILITY_FUNCTIONS = {
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


def send_message(user_input, conversation_id="default"):
    history = load_history(conversation_id)
    history.append({"role": "user", "content": user_input})

    # Tool turns are kept in history so later turns can see what was actually looked up
    messages = history

    while True:
        message = _create_message(messages)
        messages.append({"role": "assistant", "content": _dump_content(message)})
        if message.stop_reason != "tool_use":
            break

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
        ],
        output_config={"effort": "medium"},
    )


if __name__ == "__main__":
    print(send_message("What GPU do I have, and what is the weather for me, moon phase, and sunrise (sunrise tommorow)?", "demo"))