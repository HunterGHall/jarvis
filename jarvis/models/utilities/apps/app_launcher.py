import json
import os
import re
import webbrowser
from pathlib import Path

START_MENU_DIRS = [
    Path(os.environ.get("ProgramData", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
]

# Built-in tools whose Start Menu names are awkward to match.
ALIASES = {
    "calculator": "calc",
    "notepad": "notepad",
    "paint": "mspaint",
    "task manager": "taskmgr",
    "file explorer": "explorer",
    "explorer": "explorer",
    "command prompt": "cmd",
    "terminal": "wt",
    "settings": "ms-settings:",
    "snipping tool": "snippingtool",
}

FOLDERS = ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"]


def _find_shortcut(name):
    name = name.lower()
    matches = []
    for directory in START_MENU_DIRS:
        for shortcut in directory.rglob("*.lnk"):
            stem = shortcut.stem.lower()
            if name in stem:
                matches.append((len(stem), shortcut))
    # Prefer the closest match, i.e. the shortest name containing the query.
    return min(matches)[1] if matches else None


def _find_folder(name):
    home = Path.home()
    for folder in FOLDERS:
        if name.lower() in (folder.lower(), folder.lower().rstrip("s")):
            for base in (home, home / "OneDrive"):
                if (base / folder).is_dir():
                    return base / folder
    return None


def open_app(name):
    name = name.strip()
    if re.match(r"https?://", name, re.IGNORECASE):
        webbrowser.open(name)
        return {"opened": name, "type": "url"}

    key = name.lower()
    folder = _find_folder(key)
    if folder:
        os.startfile(folder)
        return {"opened": str(folder), "type": "folder"}

    if key in ALIASES:
        os.startfile(ALIASES[key])
        return {"opened": name, "type": "app"}

    shortcut = _find_shortcut(key)
    if shortcut:
        os.startfile(shortcut)
        return {"opened": shortcut.stem, "type": "app"}

    # Fall back to anything Windows can resolve on its own, e.g. an exe on PATH.
    try:
        os.startfile(name)
    except OSError:
        return {"error": f"Couldn't find an app called '{name}'."}
    return {"opened": name, "type": "app"}


if __name__ == "__main__":
    print(json.dumps({"spotify": str(_find_shortcut("spotify")), "downloads": str(_find_folder("downloads"))}, indent=2))
