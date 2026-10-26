import json
import os
from datetime import datetime
from pathlib import Path

FOLDERS = ["Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"]
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "AppData"}


def _major_folders():
    home = Path.home()
    found = {}
    for folder in FOLDERS:
        # Prefer the OneDrive-redirected copy when it exists, since that's where the files live.
        for base in (home / "OneDrive", home):
            if (base / folder).is_dir():
                found[folder] = base / folder
                break
    return found


def search_files(query="", folder=None, extension=None, limit=20):
    folders = _major_folders()
    if folder:
        match = next((name for name in folders if name.lower() == folder.strip().lower()), None)
        if not match:
            return {"error": f"Unknown folder '{folder}'.", "folders": list(folders)}
        folders = {match: folders[match]}

    query = query.strip().lower()
    extension = extension.strip().lower().lstrip(".") if extension else None
    # With no query or extension this lists the most recently modified files.
    matches = []
    for root_folder in folders.values():
        for current, dirs, files in os.walk(root_folder):
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

    matches.sort(reverse=True)
    limit = max(1, min(int(limit), 50))
    return {
        "total_matches": len(matches),
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


if __name__ == "__main__":
    print(json.dumps(search_files(folder="Downloads", limit=5), indent=2))
