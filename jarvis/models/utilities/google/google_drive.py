import io
import json
import secrets

from google_auth import GoogleError, api
from google_common import approve, declined, extract_id, safe

BASE = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER = "application/vnd.google-apps.folder"
FIELDS = "id,name,mimeType,modifiedTime,size,parents,webViewLink"
MAX_READ_CHARS = 20_000

# What people say, and the Drive file type it means
KINDS = {
    "folder": FOLDER,
    "doc": "application/vnd.google-apps.document",
    "sheet": "application/vnd.google-apps.spreadsheet",
    "slides": "application/vnd.google-apps.presentation",
    "pdf": "application/pdf",
}
# Google's own formats can't be downloaded as is, so they're exported as text
EXPORTS = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _quote(text):
    return str(text).replace("\\", "\\\\").replace("'", "\\'")


def _file(raw):
    kind = next((name for name, mime in KINDS.items() if mime == raw.get("mimeType")), raw.get("mimeType"))
    result = {"id": raw["id"], "name": raw["name"], "type": kind, "modified": (raw.get("modifiedTime") or "")[:16].replace("T", " ")}
    if raw.get("size"):
        result["size_bytes"] = int(raw["size"])
    if raw.get("webViewLink"):
        result["link"] = raw["webViewLink"]
    return result


def _list(query, limit, order="modifiedTime desc"):
    params = {
        "q": query,
        "pageSize": max(1, min(int(limit), 100)),
        "orderBy": order,
        "fields": f"files({FIELDS})",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    return [_file(raw) for raw in api("GET", f"{BASE}/files", params=params).get("files", [])]


@safe
def drive_search(name=None, text=None, kind=None, folder_id=None, limit=15):
    """Finds files by name, by what's inside them, or by type (doc, sheet, slides, pdf, folder), newest first."""
    clauses = ["trashed = false"]
    if name:
        clauses.append(f"name contains '{_quote(name)}'")
    if text:
        clauses.append(f"fullText contains '{_quote(text)}'")
    if kind:
        mime = KINDS.get(kind.strip().lower())
        if not mime:
            return {"error": f"kind must be one of: {', '.join(KINDS)}."}
        clauses.append(f"mimeType = '{mime}'")
    if folder_id:
        clauses.append(f"'{extract_id(folder_id)}' in parents")
    files = _list(" and ".join(clauses), limit)
    return {"count": len(files), "files": files}


@safe
def drive_list_folder(folder_id="root", limit=50):
    """What's inside a Drive folder ('root' is My Drive), folders first."""
    files = _list(f"'{extract_id(folder_id)}' in parents and trashed = false", limit, order="folder,name")
    return {"count": len(files), "files": files}


def _pdf_text(content):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise GoogleError("Reading PDFs needs the pypdf package: pip install pypdf")
    reader = PdfReader(io.BytesIO(content))
    return "\n\n".join(f"[Page {number}]\n{page.extract_text() or ''}" for number, page in enumerate(reader.pages, 1))


@safe
def drive_read(file_id, offset=0, max_chars=MAX_READ_CHARS):
    """Reads a file's text: Docs, Sheets (as CSV), Slides, PDFs, and text files. A folder gets listed instead."""
    file_id = extract_id(file_id)
    info = api("GET", f"{BASE}/files/{file_id}", params={"fields": "id,name,mimeType,size,webViewLink", "supportsAllDrives": "true"})
    mime = info["mimeType"]
    if mime == FOLDER:
        return {"name": info["name"], "type": "folder", **drive_list_folder(file_id)}
    if mime in EXPORTS:
        content = api("GET", f"{BASE}/files/{file_id}/export", params={"mimeType": EXPORTS[mime]}, raw=True)
        text = content.decode("utf-8", errors="replace")
    elif mime == "application/pdf":
        text = _pdf_text(api("GET", f"{BASE}/files/{file_id}", params={"alt": "media", "supportsAllDrives": "true"}, raw=True))
    elif mime.startswith("text/") or mime in {"application/json", "application/xml", "application/javascript"}:
        text = api("GET", f"{BASE}/files/{file_id}", params={"alt": "media", "supportsAllDrives": "true"}, raw=True).decode("utf-8", errors="replace")
    else:
        return {"name": info["name"], "type": mime, "error": "That kind of file can't be read as text.", "link": info.get("webViewLink")}

    offset, max_chars = max(0, int(offset)), max(1, min(int(max_chars), 100_000))
    chunk = text[offset : offset + max_chars]
    result = {"name": info["name"], "type": mime, "total_chars": len(text), "offset": offset, "content": chunk}
    if offset + max_chars < len(text):
        result["truncated"] = f"Call again with offset={offset + len(chunk)} for more."
    return result


@safe
def drive_create_folder(name, parent_id=None):
    """Makes a new folder in Drive (in My Drive unless parent_id is given)."""
    body = {"name": name, "mimeType": FOLDER}
    if parent_id:
        body["parents"] = [extract_id(parent_id)]
    return {"created": True, **_file(api("POST", f"{BASE}/files", params={"fields": FIELDS, "supportsAllDrives": "true"}, body=body))}


@safe
def drive_upload_text(name, content, folder_id=None, mime_type="text/plain"):
    """Saves a new text file to Drive (notes, CSV, JSON, Markdown...). Never replaces a file that's already there."""
    metadata = {"name": name}
    if folder_id:
        metadata["parents"] = [extract_id(folder_id)]
    boundary = secrets.token_hex(16)
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Type: {mime_type}; charset=UTF-8\r\n\r\n{content}\r\n--{boundary}--"
    ).encode("utf-8")
    created = api(
        "POST", UPLOAD, params={"uploadType": "multipart", "fields": FIELDS, "supportsAllDrives": "true"},
        data=body, content_type=f"multipart/related; boundary={boundary}",
    )
    return {"uploaded": True, **_file(created)}


@safe
def drive_update(file_id, new_name=None, move_to_folder_id=None):
    """Renames a file and/or moves it to another folder."""
    file_id = extract_id(file_id)
    if not new_name and not move_to_folder_id:
        return {"error": "Give a new_name and/or a move_to_folder_id."}
    params = {"fields": FIELDS, "supportsAllDrives": "true"}
    if move_to_folder_id:
        current = api("GET", f"{BASE}/files/{file_id}", params={"fields": "parents", "supportsAllDrives": "true"})
        params["addParents"] = extract_id(move_to_folder_id)
        params["removeParents"] = ",".join(current.get("parents", []))
    updated = api("PATCH", f"{BASE}/files/{file_id}", params=params, body={"name": new_name} if new_name else {})
    return {"updated": True, **_file(updated)}


@safe
def drive_trash(file_id):
    """Moves a file or folder to the Drive trash (it can be restored from there), after the user approves."""
    file_id = extract_id(file_id)
    info = api("GET", f"{BASE}/files/{file_id}", params={"fields": FIELDS, "supportsAllDrives": "true"})
    if not approve(f"Move this to the Drive trash?\n\n    {info['name']}\n", f"Shall I move {info['name']} to the Drive trash?"):
        return declined()
    api("PATCH", f"{BASE}/files/{file_id}", params={"supportsAllDrives": "true"}, body={"trashed": True})
    return {"trashed": True, "name": info["name"], "note": "It's in the Drive trash and can be restored."}


@safe
def drive_share(file_id, email, role="reader", notify=True):
    """Gives someone access to a file or folder (role: reader, commenter, or writer), after the user approves."""
    file_id = extract_id(file_id)
    if role not in {"reader", "commenter", "writer"}:
        return {"error": "role must be reader, commenter, or writer."}
    info = api("GET", f"{BASE}/files/{file_id}", params={"fields": "id,name", "supportsAllDrives": "true"})
    if not approve(
        f"Share this?\n\n    {info['name']}\n    With: {email} ({role})\n" + ("    They'll get an email.\n" if notify else ""),
        f"Shall I share {info['name']} with {email} as a {role}?",
    ):
        return declined()
    api(
        "POST", f"{BASE}/files/{file_id}/permissions",
        params={"sendNotificationEmail": str(bool(notify)).lower(), "supportsAllDrives": "true"},
        body={"type": "user", "role": role, "emailAddress": email},
    )
    return {"shared": True, "name": info["name"], "with": email, "role": role}
