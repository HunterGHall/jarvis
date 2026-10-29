import anthropic
import json
import re
import sys
import time
from configparser import ConfigParser
from pathlib import Path

from jarvis.first_run import render
from jarvis.paths import CONFIG_PATH, CONVERSATIONS_DIR

# The prompts and tools live next to this file; your own files (config, conversation) are found by jarvis.paths
MODELS_DIR = Path(__file__).resolve().parent.parent
CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

# Normally `jarvis` has already asked for your details (see launch.py). This is the fallback when there is nobody to ask.
if not CONFIG_PATH.exists():
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(render(), encoding="utf-8")
    sys.exit(f"Created {CONFIG_PATH}. Fill in your details and run again.")

# Get API key and model version
config = ConfigParser()
config.read(CONFIG_PATH)
anthropic_api_key = config["anthropic"]["anthropic_api_key"]
client = anthropic.Anthropic(api_key=anthropic_api_key)
model_version = config["anthropic"].get("model", "claude-sonnet-5-5")
show_cost = config.get("settings", "show_cost", fallback="").strip().strip('"').lower() in {"true", "yes", "on", "1"}
# Redraw the screen at the new width when the terminal window is resized
auto_resize = config.get("settings", "auto_resize", fallback="true").strip().strip('"').lower() not in {"false", "no", "off", "0"}
# How many of your most recent messages (and Jarvis's replies to them) are kept and sent along with a new one
try:
    history_turns = max(2, int(config.get("settings", "history_turns", fallback="").strip().strip('"') or 12))
except ValueError:
    history_turns = 12

# Get training data: the normal prompt, and the one used when replies are spoken aloud (voice mode)
with open(MODELS_DIR / "training_data" / "jarvis.txt", "r", encoding="utf-8") as file:
    content = file.read()
with open(MODELS_DIR / "training_data" / "jarvis-voice.txt", "r", encoding="utf-8") as file:
    voice_content = file.read()

# Tell the model who it is talking to
user_name = config.get("personal", "name", fallback="").strip().strip('"')
if user_name:
    name_note = f"\n\nThe user's name is {user_name}, but address them as sir, never say there name unless directly asked."
    content += name_note
    voice_content += name_note

# The bash tool is declared by name only, so how it behaves here has to be explained in the system prompt
shell_note = (
    "\n\nYou have a bash tool, but it runs commands in Windows PowerShell on the user's own PC, not in bash. Use "
    "PowerShell syntax. It starts in their home folder and remembers the working directory between commands, but not "
    "variables. The user is shown every command and must approve it, so when they ask for something that needs the "
    "terminal, just call the tool without asking permission in chat. Prefer your dedicated tools (files, apps, "
    "volume and so on) when one fits, and summarize command output rather than reading it out."
)
content += shell_note
voice_content += shell_note

# Utilities import each other by bare module name (e.g. `from location import ...`),
# so each utility folder has to be on the path
UTILITIES_DIR = MODELS_DIR / "utilities"
for folder in UTILITIES_DIR.iterdir():
    if folder.is_dir():
        # Front of the path so a utility's name wins over installed modules (pywin32 ships its own `timer`)
        sys.path.insert(0, str(folder))

from current_date import get_date
from current_time import get_time
from current_weather import get_weather
from air_quality import get_air_quality
from app_launcher import close_app, open_app
from calculator import calculate, convert_units
from clipboard import read_clipboard, write_clipboard
from dictionary import define
from earthquakes import get_earthquakes
from file_io import list_folder, read_file, write_file
from file_operations import copy_file, create_folder, delete_file, move_file, rename_file
from holidays import get_holidays
from file_search import search_files
from recycle_bin import empty_recycle_bin, get_recycle_bin
from finance import convert_currency, get_crypto_price, get_stock_price
from focus_mode import get_do_not_disturb, set_do_not_disturb
from forecast import get_daily_forecast, get_hourly_forecast
from github_status import clear_github_status, get_github_status, set_github_status
from lyrics import get_lyrics
from media_control import MEDIA_KEYS, get_now_playing, media_control
from volume import get_volume, set_volume
from network_status import get_network_status, ping_host
from news import TOPICS as NEWS_TOPICS, get_headlines, search_news
from randomizer import flip_coin, pick_random, random_number, roll_dice
from recipes import get_recipe, random_recipe, search_recipes
from scores import LEAGUES, get_scores
from space import get_apod, get_iss
from sun_moon import get_sun_and_moon
from system_specifications import get_system_specifications
from system_status import get_system_status
from terminal import run_bash
from web_images import search_images
from timer import cancel_timer, list_timers, set_timer
from google_tools import FUNCTIONS as GOOGLE_FUNCTIONS, NOTE as GOOGLE_NOTE, TOOLS as GOOGLE_TOOLS, google_ready

# The Google tools (Gmail, Calendar, Drive, Docs, Sheets, Slides) are only offered once the one-time setup has been
# run: jarvis google-setup
if google_ready():
    content += GOOGLE_NOTE
    voice_content += GOOGLE_NOTE

UTILITY_FUNCTIONS = {
    "search_images": search_images,
    "get_github_status": get_github_status,
    "set_github_status": set_github_status,
    "clear_github_status": clear_github_status,
    "get_apod": get_apod,
    "get_iss": get_iss,
    "get_earthquakes": get_earthquakes,
    "get_lyrics": get_lyrics,
    "get_holidays": get_holidays,
    "get_volume": get_volume,
    "set_volume": set_volume,
    "list_folder": list_folder,
    "read_file": read_file,
    "write_file": write_file,
    "get_recycle_bin": get_recycle_bin,
    "empty_recycle_bin": empty_recycle_bin,
    "search_recipes": search_recipes,
    "get_recipe": get_recipe,
    "random_recipe": random_recipe,
    "delete_file": delete_file,
    "move_file": move_file,
    "copy_file": copy_file,
    "rename_file": rename_file,
    "create_folder": create_folder,
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

_FILE_PATH = (
    "Full path to anywhere on this computer, or a shortcut starting with Desktop, Documents, "
    "Downloads, Pictures, Music or Videos (e.g. Downloads/report.pdf)."
)

UTILITY_TOOLS = [
    {
        "name": "search_images",
        "description": "Find pictures on the web that are free to reuse (Wikimedia Commons, then Openverse), each with a direct image link, size, and the credit its license asks to be shown. Use it to find a picture to put in a Google Doc, Sheet, or Slides deck; pass the image url to docs_insert_image, sheets_insert_image, or slides_insert_image, and the credit as the caption (Docs and Slides). Works for subjects, places, animals, and public figures, but not for brand logos or recent news photos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What the picture should show."},
                "limit": {"type": "integer", "description": "How many to return, up to 10. Defaults to 5."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_github_status",
        "description": "Check what status (emoji and message) is currently shown on the user's GitHub profile.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "set_github_status",
        "description": "Set the status shown on the user's GitHub profile, e.g. 'Coding' with a computer emoji. Give minutes if it should clear itself (like 120 for two hours). Replaces any status already there.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "What to show, up to 80 characters."},
                "emoji": {"type": "string", "description": "An emoji, or its name such as computer, coffee, palm_tree. Optional."},
                "minutes": {"type": "number", "description": "Clear the status automatically after this many minutes. Leave out to keep it until it's changed."},
                "busy": {"type": "boolean", "description": "Show GitHub's 'busy' indicator, for when the user is unavailable."},
            },
            "required": ["message"],
        },
    },
    {
        "name": "clear_github_status",
        "description": "Remove the status from the user's GitHub profile.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "get_apod",
        "description": "Get NASA's Astronomy Picture of the Day: title, a short explanation, credit, and a link to the image or video. Defaults to today.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string", "description": "Optional date as YYYY-MM-DD, any day since 1995-06-16."}},
        },
    },
    {
        "name": "get_iss",
        "description": "Get where the International Space Station is right now: latitude and longitude, what it's over, altitude, speed, and whether it's in sunlight.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "get_earthquakes",
        "description": "Get recent earthquakes from the USGS, newest first or strongest first, worldwide or within a radius of the user's location. Includes magnitude, location, depth, how long ago, tsunami messages, felt reports, and the USGS impact alert color. total_matches counts every match even when fewer are returned.",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_magnitude": {"type": "number", "description": "Smallest magnitude to include. Defaults to 4.5 (use 2.5 or lower for near-me)."},
                "days": {"type": "integer", "description": "How many days back, up to 30. Defaults to 1."},
                "limit": {"type": "integer", "description": "How many to return, up to 50. Defaults to 10."},
                "sort_by": {"type": "string", "enum": ["time", "magnitude"], "description": "Newest first (default) or strongest first."},
                "near_me": {"type": "boolean", "description": "Only earthquakes near the user's zip code."},
                "radius_miles": {"type": "number", "description": "With near_me, how far to look. Defaults to 200."},
                **_ZIP_CODE,
            },
        },
    },
    {
        "name": "get_lyrics",
        "description": "Look up a song's lyrics (from LRCLIB). With no song given, it looks up whatever is playing on the user's computer right now. Use it to answer questions about a song's lyrics or meaning, or to quote a few lines; don't reproduce a whole song's lyrics in a reply.",
        "input_schema": {
            "type": "object",
            "properties": {
                "song": {"type": "string", "description": "Song title. Leave out to use the song that's playing."},
                "artist": {"type": "string", "description": "Artist, which helps pick the right version."},
                "synced": {"type": "boolean", "description": "Return line-by-line timestamps ([mm:ss.xx]) instead of plain lyrics."},
            },
        },
    },
    {
        "name": "get_holidays",
        "description": "Get public holidays: the upcoming ones by default (with days until each), or every holiday in a given year. Defaults to the US; use a two-letter country code for others.",
        "input_schema": {
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "Two-letter country code, e.g. US, GB, CA. Defaults to US."},
                "year": {"type": "integer", "description": "List the whole year instead of just upcoming holidays."},
                "limit": {"type": "integer", "description": "How many upcoming holidays, up to 30. Defaults to 10."},
            },
        },
    },
    {
        "name": "get_volume",
        "description": "Get the computer's current speaker volume (0-100) and whether it's muted.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "set_volume",
        "description": "Set the computer's speaker volume to an exact percentage (0-100) and/or mute or unmute it. Use media_control instead for small up/down steps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "integer", "description": "Volume from 0 to 100."},
                "muted": {"type": "boolean", "description": "true to mute, false to unmute."},
            },
        },
    },
    {
        "name": "list_folder",
        "description": "Look inside a folder anywhere on the computer: every file and subfolder in it, with sizes and modified dates, folders first. Set recursive to include everything in the subfolders too. To read what's inside the files, follow up with read_file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": _FILE_PATH},
                "recursive": {"type": "boolean", "description": "Include everything in the subfolders. Defaults to false."},
                "limit": {"type": "integer", "description": "Max items to list, up to 1000. Defaults to 200."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a text, code, CSV/JSON, .docx, or .pdf file anywhere on the computer. Long files come back in pages: use the offset from the truncated note to continue. Given a folder, it lists what's inside instead.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": _FILE_PATH},
                "offset": {"type": "integer", "description": "Character to start from. Defaults to 0."},
                "max_chars": {"type": "integer", "description": "Characters to return, up to 100000. Defaults to 20000."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write text to a file. mode 'create' (default) makes a new file and refuses if it exists; 'append' adds to the end; 'overwrite' replaces it, after the user approves in the CLI, with the old version kept in the Recycle Bin. Parent folders are created as needed. Text only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": _FILE_PATH},
                "content": {"type": "string"},
                "mode": {"type": "string", "enum": ["create", "append", "overwrite"]},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "get_recycle_bin",
        "description": "Check how many items are in the Recycle Bin and how much space they take.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "empty_recycle_bin",
        "description": "PERMANENTLY erase everything in the Recycle Bin, which can't be undone (this is how to permanently delete files that delete_file moved there). The CLI asks the user to approve, with a y/N prompt (or out loud in voice mode) showing the item count and size, so when the user has clearly asked to empty or delete the Recycle Bin, call this right away without asking in chat first. Never claim it's emptied until this returns emptied: true.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "search_recipes",
        "description": "Search recipes by dish name or main ingredient, e.g. 'lasagne' or 'chicken'. Returns matching dishes with their category and cuisine.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results, up to 20. Defaults to 8."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_recipe",
        "description": "Get a full recipe (ingredients with measures, instructions, video, source) by dish name, main ingredient, or a recipe id from search_recipes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Dish name or main ingredient."},
                "meal_id": {"type": "string", "description": "Recipe id from search_recipes."},
            },
        },
    },
    {
        "name": "random_recipe",
        "description": "Get a random full recipe, for 'what should I cook' or 'surprise me'.",
        "input_schema": _NO_INPUT,
    },
    {
        "name": "delete_file",
        "description": "Move files or folders to the Recycle Bin (they can be restored). The CLI itself asks the user to approve each delete (a y/N prompt that lists what will go, or a spoken question in voice mode), so when the user has clearly asked for a delete, call this right away: don't ask for confirmation in chat first, and don't comment on file names. Pass many paths in one call for a single approval. To empty a folder, pass the folder with contents_only=true instead of listing its files. Never claim something is deleted until this returns deleted: true.",
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string", "description": _FILE_PATH}},
                "contents_only": {
                    "type": "boolean",
                    "description": "Delete everything inside each given folder but keep the folder itself.",
                },
            },
            "required": ["paths"],
        },
    },
    {
        "name": "move_file",
        "description": "Move a file or folder. If the destination is an existing folder, the item goes inside it; otherwise it's moved to that new path. Never overwrites.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": _FILE_PATH},
                "destination": {"type": "string", "description": _FILE_PATH},
            },
            "required": ["source", "destination"],
        },
    },
    {
        "name": "copy_file",
        "description": "Copy a file or folder. If the destination is an existing folder, the copy goes inside it. Never overwrites.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": _FILE_PATH},
                "destination": {"type": "string", "description": _FILE_PATH},
            },
            "required": ["source", "destination"],
        },
    },
    {
        "name": "rename_file",
        "description": "Rename a file or folder in place. Never overwrites.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": _FILE_PATH},
                "new_name": {"type": "string", "description": "Just the new name, e.g. 'report-final.pdf'."},
            },
            "required": ["path", "new_name"],
        },
    },
    {
        "name": "create_folder",
        "description": "Create a folder (and any missing parent folders), optionally with text files already inside it. Use files to write a whole project or set of notes in one call. Existing files are never overwritten, and files can be added to a folder that already exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": _FILE_PATH},
                "files": {
                    "type": "object",
                    "description": "Files to create inside the folder: each key is a file name, which may include subfolders such as 'src/main.py', and each value is that file's text.",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["path"],
        },
    },
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
        "description": "Search for files by name and/or extension, newest first. With no folder it searches the user's main folders (Desktop, Documents, Downloads, Pictures, Music, Videos); give a folder name or any full path, even a whole drive like C:\\, to search anywhere. With no query it lists the most recently modified files. Compare total_matches with returned and raise limit if results were cut off. Lists files only, not empty folders.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to match in the file name."},
                "folder": {"type": "string", "description": "A main folder name (e.g. Downloads) or any full folder path."},
                "extension": {"type": "string", "description": "File extension, e.g. pdf."},
                "limit": {"type": "integer", "description": "Max results, up to 500. Defaults to 20."},
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

if google_ready():
    UTILITY_FUNCTIONS.update(GOOGLE_FUNCTIONS)
    UTILITY_TOOLS += GOOGLE_TOOLS



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


def _trim_history(history):
    """Keeps only the most recent turns, since the whole conversation is re-sent with every request.

    It trims in chunks, once the history is half again as long as the limit, instead of dropping one turn each time,
    because every change to the start of the history starts the prompt cache over.
    """
    turn_starts = [i for i, message in enumerate(history) if message["role"] == "user" and isinstance(message["content"], str)]
    if len(turn_starts) <= history_turns + history_turns // 2:
        return history

    trimmed = history[turn_starts[-history_turns]:]
    for message in trimmed:
        if message["role"] == "assistant" and isinstance(message["content"], list):
            # Thinking blocks belong to the conversation that came before them, which has just changed
            message["content"] = [block for block in message["content"] if block.get("type") not in {"thinking", "redacted_thinking"}]
    # A turn that was only thinking is now empty, and the API rejects empty messages
    return [message for message in trimmed if message["content"]]


def _first_unpaired_tool_call(history):
    """Index of the first message whose tool calls and tool results don't line up, or None if they all do."""
    for i, message in enumerate(history):
        if not isinstance(message["content"], list):
            continue
        if message["role"] == "assistant":
            wanted = {b["id"] for b in message["content"] if b.get("type") == "tool_use"}
            following = history[i + 1]["content"] if i + 1 < len(history) else None
            answered = {b.get("tool_use_id") for b in following if b.get("type") == "tool_result"} if isinstance(following, list) else set()
            if wanted - answered:
                return i
        else:
            answers = {b.get("tool_use_id") for b in message["content"] if b.get("type") == "tool_result"}
            previous = history[i - 1]["content"] if i > 0 else None
            asked = {b["id"] for b in previous if b.get("type") == "tool_use"} if isinstance(previous, list) and history[i - 1]["role"] == "assistant" else set()
            if answers - asked:
                return i
    return None


def _heal_history(history):
    """Drops any exchange whose tool calls never got their results.

    The API refuses a conversation with a tool call that has no matching result, and it refuses it on every later
    message, so one broken exchange left in the saved file would block every message after it.
    """
    while (broken := _first_unpaired_tool_call(history)) is not None:
        start = max((i for i in range(broken + 1) if history[i]["role"] == "user" and isinstance(history[i]["content"], str)), default=0)
        history = history[:start]
    return history


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


def send_message(user_input, conversation_id="default", on_event=None, voice=False):
    # on_event gets a dict per tool call/result so a front end can show what the model is doing
    emit = on_event or (lambda _: None)
    history = _trim_history(_heal_history(load_history(conversation_id)))
    history.append({"role": "user", "content": user_input})

    # Tool turns are kept in history so later turns can see what was actually looked up
    messages = history

    while True:
        message = _create_message(messages, voice)
        emit({"type": "usage", "model": model_version, "usage": message.usage.model_dump()})
        messages.append({"role": "assistant", "content": _dump_content(message)})
        _emit_server_tools(message, emit)
        if message.stop_reason != "tool_use":
            break

        results = []
        for block in message.content:
            if block.type != "tool_use":
                continue
            # Tools from a toolset (e.g. "browser") must have their results tagged with the toolset's name, or the
            # API rejects the next request. None of the toolsets are run by this app, so they get an error back.
            toolset = getattr(block, "toolset_name", None)
            emit({"type": "tool_call", "name": block.name, "input": block.input})
            started = time.perf_counter()
            if toolset:
                output, is_error = f"The {toolset} tools aren't available in this app.", True
            elif block.name == "bash":
                output, is_error = run_bash(block.input)
            else:
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
            result = {"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": is_error}
            if toolset:
                result["toolset_name"] = toolset
            results.append(result)
        messages.append({"role": "user", "content": results})

    # If the model stopped for any reason other than "tool_use" (running out of room, a refusal) its last message may
    # still hold tool calls that will never get results. Saved as they are, they'd make every later request fail.
    last = messages[-1]
    if last["role"] == "assistant" and any(block.get("type") == "tool_use" for block in last["content"]):
        kept = [block for block in last["content"] if block.get("type") not in {"tool_use", "thinking", "redacted_thinking"}]
        if kept:
            last["content"] = kept
        else:
            messages.pop()

    save_history(conversation_id, history)
    details = getattr(message, "stop_details", None)
    emit({"type": "stop", "stop_reason": message.stop_reason, "details": details.model_dump() if details else None})
    return "".join(block.text for block in message.content if block.type == "text")


def _dump_content(message):
    # Plain dicts, so the blocks can be saved as JSON and sent back to the API
    return [block.model_dump(exclude_none=True) for block in message.content]


CACHE = {"type": "ephemeral"}

# The same list on every request, in the same order: any change to it (or to the system prompt) starts the cache over
TOOLS = UTILITY_TOOLS + [
    {"type": "bash_20250124", "name": "bash"},
    {
        "name": "web_fetch",
        "type": "web_fetch_20260318",
        "allowed_callers": ["direct"],
    },
    {
        "name": "web_search",
        "type": "web_search_20260318",
        "allowed_callers": ["direct"],
    },
]
# A cache breakpoint at the end of the tools, so they stay cached even when the system prompt changes (voice mode)
TOOLS[-1] = {**TOOLS[-1], "cache_control": CACHE}


def _create_message(messages, voice=False):
    return client.messages.create(
        model=model_version,
        max_tokens=20000,
        # Prompt caching: the tools, the system prompt, and the conversation so far are mostly identical from one
        # request to the next, so they're read back from the cache at a tenth of the price
        system=[{"type": "text", "text": voice_content if voice else content, "cache_control": CACHE}],
        messages=messages,
        tools=TOOLS,
        cache_control=CACHE,
        output_config={"effort": "low" if voice else "medium"},
    )


if __name__ == "__main__":
    print(send_message("What GPU do I have, and what is the weather for me, moon phase, and sunrise (sunrise tommorow)?", "demo"))