import json
import os
import re
import subprocess
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


# Names people say that differ from the process name.
PROCESS_ALIASES = {
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "vs code": "code",
    "visual studio code": "code",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
}

# Never closed, so Jarvis can't shut down the terminal it's running in or the desktop shell.
PROTECTED_PROCESSES = {
    "explorer", "python", "pythonw", "windowsterminal", "cmd", "powershell", "pwsh", "conhost", "openconsole",
}


def close_app(name):
    key = name.strip().lower()
    query = PROCESS_ALIASES.get(key, key).replace(" ", "")
    # Match on the process name only. A window title can match unrelated apps, e.g. a browser tab.
    script = (
        "Get-Process | Where-Object { $_.MainWindowHandle -ne 0 } | "
        "Select-Object Id,ProcessName | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=15
        )
        processes = json.loads(result.stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"error": "Couldn't list running apps."}
    if isinstance(processes, dict):
        processes = [processes]

    matches = [p for p in processes if query in p["ProcessName"].lower()]
    if any(p["ProcessName"].lower() in PROTECTED_PROCESSES for p in matches):
        return {"error": f"'{name}' is protected and won't be closed."}
    if not matches:
        return {"error": f"No open app matching '{name}'."}

    # CloseMainWindow asks the app to close like the X button does, so unsaved work still prompts.
    ids = ",".join(str(p["Id"]) for p in matches)
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"Get-Process -Id {ids} | ForEach-Object {{ [void]$_.CloseMainWindow() }}"],
        capture_output=True,
        timeout=15,
    )
    return {"closed": sorted({p["ProcessName"] for p in matches}), "windows": len(matches)}


if __name__ == "__main__":
    print(json.dumps({"spotify": str(_find_shortcut("spotify")), "downloads": str(_find_folder("downloads"))}, indent=2))
