"""Where Jarvis keeps your own files, apart from the program itself.

Installed with pipx, the program lives in a read-only environment, so your settings, Google sign-in, voices and saved
conversation go in %APPDATA%\\Jarvis instead. Running from a checkout of the repository that already has its own
config.conf keeps using the project folder, so an existing setup doesn't change. Set JARVIS_HOME to choose a folder.
"""
import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent  # the program: prompts, the bundled voice, the tools
PROJECT_DIR = PACKAGE_DIR.parent  # a checkout's top folder (where main.py is); site-packages when installed


def _data_dir():
    override = os.environ.get("JARVIS_HOME")
    if override:
        return Path(override).expanduser()
    if (PROJECT_DIR / "config.conf").exists():
        return PROJECT_DIR
    return Path(os.environ.get("APPDATA") or Path.home()) / "Jarvis"


DATA_DIR = _data_dir()
CONFIG_PATH = DATA_DIR / "config.conf"
GOOGLE_CREDENTIALS_PATH = DATA_DIR / "google_credentials.json"
GOOGLE_TOKEN_PATH = DATA_DIR / "google_token.json"
VOICES_DIR = DATA_DIR / "voices"  # voices you add yourself; the bundled one stays in the package
# In a checkout the conversation stays where it always was
CONVERSATIONS_DIR = PACKAGE_DIR / "models" / "conversations" if DATA_DIR == PROJECT_DIR else DATA_DIR / "conversations"
