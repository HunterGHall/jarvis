import json
import os
import time
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from file_operations import _OperationError, _format_size, _recycle, _resolve, _run, check_writable, confirm

DEFAULT_CHARS = 20_000
MAX_CHARS = 100_000
MAX_ITEMS = 1000
LIST_TIME_BUDGET_SECONDS = 20
WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _read_docx(path):
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.iter(f"{WORD_NAMESPACE}p"):
        paragraphs.append("".join(node.text or "" for node in paragraph.iter(f"{WORD_NAMESPACE}t")))
    return "\n".join(paragraphs)


def _read_pdf(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise _OperationError("Reading PDFs needs the pypdf package: pip install pypdf")
    reader = PdfReader(str(path))
    return "\n\n".join(f"[Page {number}]\n{page.extract_text() or ''}" for number, page in enumerate(reader.pages, 1))


def _read_text(path):
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        raise _OperationError(f"'{path.name}' looks like a binary file, not text.")
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _list_folder(target, recursive, limit):
    limit = max(1, min(int(limit), MAX_ITEMS))
    deadline = time.monotonic() + LIST_TIME_BUDGET_SECONDS
    entries, timed_out = [], False
    for current, folders, files in os.walk(target):
        base = Path(current)
        for is_folder, names in ((True, folders), (False, files)):
            for name in names:
                path = base / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                entries.append((is_folder, path.relative_to(target), 0 if is_folder else stat.st_size, stat.st_mtime))
        if not recursive:
            break
        if time.monotonic() > deadline:
            timed_out = True
            break

    # Folders first, then by name
    entries.sort(key=lambda entry: (not entry[0], str(entry[1]).lower()))
    result = {
        "path": str(target),
        "folders": sum(1 for entry in entries if entry[0]),
        "files": sum(1 for entry in entries if not entry[0]),
        "total_size": _format_size(sum(entry[2] for entry in entries)),
        "items": [
            {
                "name": relative.as_posix(),
                "type": "folder" if is_folder else "file",
                **({} if is_folder else {"size": _format_size(size)}),
                "modified": datetime.fromtimestamp(modified).strftime("%Y-%m-%d %H:%M"),
            }
            for is_folder, relative, size, modified in entries[:limit]
        ],
    }
    if len(entries) > limit:
        result["truncated"] = f"Showing {limit} of {len(entries)} items. Raise limit to see more."
    if timed_out:
        result["incomplete"] = f"Stopped after {LIST_TIME_BUDGET_SECONDS}s, so there may be more items."
    return result


def list_folder(path, recursive=False, limit=200):
    """List what's inside a folder: names, sizes, and dates. recursive=True includes everything in the subfolders too."""

    def operation(path, recursive, limit):
        target = _resolve(path)
        if not target.is_dir():
            raise _OperationError(f"No folder at '{target}'.")
        return _list_folder(target, recursive, limit)

    return _run(operation, path, recursive, limit)


def read_file(path, offset=0, max_chars=DEFAULT_CHARS):
    """Read a text, code, .docx, or .pdf file, or list a folder. Use offset to page through long files."""

    def operation(path, offset, max_chars):
        target = _resolve(path)
        if target.is_dir():
            return _list_folder(target, recursive=False, limit=200)
        if not target.is_file():
            raise _OperationError(f"No file at '{target}'.")
        suffix = target.suffix.lower()
        try:
            if suffix == ".docx":
                text = _read_docx(target)
            elif suffix == ".pdf":
                text = _read_pdf(target)
            else:
                text = _read_text(target)
        except zipfile.BadZipFile:
            raise _OperationError(f"'{target.name}' isn't a valid {suffix} file.")

        offset = max(0, int(offset))
        max_chars = max(1, min(int(max_chars), MAX_CHARS))
        chunk = text[offset : offset + max_chars]
        result = {
            "path": str(target),
            "total_chars": len(text),
            "offset": offset,
            "content": chunk,
        }
        if offset + max_chars < len(text):
            result["truncated"] = f"Showing characters {offset}-{offset + len(chunk)}. Call again with offset={offset + len(chunk)} for more."
        return result

    return _run(operation, path, offset, max_chars)


def write_file(path, content, mode="create"):
    """Write text to a file. mode: create (new files only), append, or overwrite (asks first)."""

    def operation(path, content, mode):
        target = _resolve(path)
        check_writable(target)
        mode = mode.strip().lower()
        if mode not in {"create", "append", "overwrite"}:
            raise _OperationError("mode must be create, append, or overwrite.")
        if target.is_dir():
            raise _OperationError(f"'{target}' is a folder.")
        exists = target.exists()

        if mode == "create" and exists:
            raise _OperationError(f"'{target}' already exists. Use mode 'append' or 'overwrite'.")
        if mode == "append" and not exists:
            mode = "create"

        if mode == "overwrite" and exists:
            message = f"Overwrite '{target}' ({_format_size(target.stat().st_size)}) with {len(content)} new characters? The old version goes to the Recycle Bin."
            if not confirm(message, f"Shall I replace {target.name}? The old version goes to the Recycle Bin."):
                return {"written": False, "reason": "The user declined, or confirmation wasn't available."}
            # Recycle the old file first so its content can be restored.
            _recycle([target])

        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a" if mode == "append" else "w", encoding="utf-8", newline="") as file:
            file.write(content)
        return {"written": True, "path": str(target), "mode": mode, "characters": len(content)}

    return _run(operation, path, content, mode)


if __name__ == "__main__":
    print(json.dumps(read_file(__file__, 0, 200), indent=2))
