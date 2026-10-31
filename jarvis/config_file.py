"""config.conf: where it lives, the template made on first run, and one place that changes it.

Everything that edits the file goes through `update`, which reads the file fresh first, so a change made by one part of
Jarvis never overwrites a newer change made by another.
"""
import os
from configparser import ConfigParser
from pathlib import Path

# Where Jarvis keeps what belongs to the user: config.conf, the saved conversation, the Google sign-in. Normally the
# project folder (one level above this package). The installed desktop app has no project folder, so it sets JARVIS_DATA
# to a folder in the user's profile.
DATA_DIR = Path(os.environ["JARVIS_DATA"]) if os.environ.get("JARVIS_DATA") else Path(__file__).resolve().parent.parent
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = DATA_DIR / "config.conf"

TEMPLATE = (
    "[anthropic]\n"
    "anthropic_api_key = YOUR_KEY\n"
    "model = claude-haiku-5-5\n"
    "\n"
    "[personal]\n"
    "name = YOUR_NAME\n"
    "zip_code = YOUR_ZIP\n"
    "\n"
    "[settings]\n"
    "show_cost = False\n"
    "\n"
    "# Optional: a classic GitHub personal access token with the 'user' scope, to change your GitHub status\n"
    "[github]\n"
    "token =\n"
    "\n"
    "# Optional: a Fish Audio key, so Jarvis can speak aloud (fish.audio)\n"
    "[fish]\n"
    "api_key =\n"
)


def create_if_missing():
    """Writes the first-run template if there is no config.conf yet. True if it had to."""
    if CONFIG_PATH.exists():
        return False
    CONFIG_PATH.write_text(TEMPLATE, encoding="utf-8")
    return True


def read():
    parser = ConfigParser(interpolation=None)  # keys and tokens may contain a %
    parser.read(CONFIG_PATH, encoding="utf-8")
    return parser


def update(changes):
    """Saves {section: {key: value}} into config.conf. (Comments in the file are not kept.)"""
    parser = read()
    for section, values in changes.items():
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in values.items():
            parser.set(section, key, str(value))
    temporary = CONFIG_PATH.with_suffix(".tmp")
    with open(temporary, "w", encoding="utf-8") as file:
        parser.write(file)
    temporary.replace(CONFIG_PATH)
