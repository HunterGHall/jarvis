import json
import os
import time
from datetime import datetime
from pathlib import Path

FOLDERS = ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"]
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "AppData"}
MAX_LIMIT = 500
# A search of a whole drive can take minutes, so stop after this long and say so.
TIME_BUDGET_SECONDS = 30


def get_major_folders():
    home = Path.home()
    found = {}
    for folder in FOLDERS:
        # Prefer the OneDrive-redirected copy when it exists, since that's where the files live.
        for base in (home / "OneDrive", home):
            if (base / folder).is_dir():
                found[folder] = base / folder
                break
    return found


def _search_roots(folder):
    majors = get_major_folders()
    if not folder:
        return list(majors.values()), True
    match = next((path for name, path in majors.items() if name.lower() == folder.strip().lower()), None)
    if match:
        return [match], False
    path = Path(os.path.expandvars(os.path.expanduser(folder.strip().strip('"'))))
    if not path.is_dir():
        return None, False
    return [path], False


def search_files(query="", folder=None, extension=None, limit=20):
    roots, default_scope = _search_roots(folder)
    if roots is None:
        return {"error": f"'{folder}' isn't a folder.", "main_folders": FOLDERS}

    query = query.strip().lower()
    extension = extension.strip().lower().lstrip(".") if extension else None
    deadline = time.monotonic() + TIME_BUDGET_SECONDS
    timed_out = False

    # With no query or extension this lists the most recently modified files.
    matches = []
    for root_folder in roots:
        for current, dirs, files in os.walk(root_folder):
            if time.monotonic() > deadline:
                timed_out = True
                break
            if default_scope:
                # The default search covers the main folders only and skips clutter; a named folder is searched in full.
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for file_name in files:
                if query and query not in file_name.lower():
                    continue
                if extension and not file_name.lower().endswith(f".{extension}"):
                    continue
                path = Path(current) / file_name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                matches.append((stat.st_mtime, stat.st_size, path))
        if timed_out:
            break

    matches.sort(reverse=True)
    limit = max(1, min(int(limit), MAX_LIMIT))
    result = {
        "searched": [str(root) for root in roots],
        "total_matches": len(matches),
        "returned": min(limit, len(matches)),
        "files": [
            {
                "name": path.name,
                "path": str(path),
                "size_mb": round(size / 1024**2, 2),
                "modified": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
            }
            for mtime, size, path in matches[:limit]
        ],
    }
    if timed_out:
        result["incomplete"] = f"Stopped after {TIME_BUDGET_SECONDS}s, so there may be more matches."
    return result


if __name__ == "__main__":
    print(json.dumps(search_files(folder="Downloads", limit=5), indent=2))
