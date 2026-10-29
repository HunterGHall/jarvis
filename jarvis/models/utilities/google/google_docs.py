from google_auth import api
from google_common import extract_id, safe

BASE = "https://docs.googleapis.com/v1/documents"
MAX_READ_CHARS = 20_000


def _text(elements):
    """The plain text of a list of structural elements: paragraphs, and tables cell by cell."""
    pieces = []
    for element in elements:
        if "paragraph" in element:
            pieces.append("".join(run.get("textRun", {}).get("content", "") for run in element["paragraph"].get("elements", [])))
        elif "table" in element:
            for row in element["table"].get("tableRows", []):
                cells = [_text(cell.get("content", [])).strip().replace("\n", " ") for cell in row.get("tableCells", [])]
                pieces.append("\t".join(cells) + "\n")
    return "".join(pieces)


def _url(document_id):
    return f"https://docs.google.com/document/d/{document_id}/edit"


@safe
def docs_read(document, offset=0, max_chars=MAX_READ_CHARS):
    """The text of a Google Doc, from its id or link."""
    document_id = extract_id(document)
    doc = api("GET", f"{BASE}/{document_id}")
    text = _text(doc.get("body", {}).get("content", []))
    offset, max_chars = max(0, int(offset)), max(1, min(int(max_chars), 100_000))
    chunk = text[offset : offset + max_chars]
    result = {"title": doc.get("title"), "id": document_id, "total_chars": len(text), "offset": offset, "content": chunk}
    if offset + max_chars < len(text):
        result["truncated"] = f"Call again with offset={offset + len(chunk)} for more."
    return result


@safe
def docs_create(title, text=""):
    """Creates a new Google Doc, optionally with text already in it."""
    doc = api("POST", BASE, body={"title": title})
    if text:
        api("POST", f"{BASE}/{doc['documentId']}:batchUpdate", body={"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]})
    return {"created": True, "title": title, "id": doc["documentId"], "link": _url(doc["documentId"])}


@safe
def docs_append(document, text):
    """Adds text to the end of a Google Doc."""
    document_id = extract_id(document)
    doc = api("GET", f"{BASE}/{document_id}", params={"fields": "title,body(content(endIndex))"})
    end = doc["body"]["content"][-1]["endIndex"]
    # The very last character of the body is a newline that can't be written past
    api("POST", f"{BASE}/{document_id}:batchUpdate", body={"requests": [{"insertText": {"location": {"index": end - 1}, "text": text}}]})
    return {"appended": True, "title": doc.get("title"), "characters": len(text), "link": _url(document_id)}


@safe
def docs_replace_text(document, find, replace, match_case=True):
    """Replaces every occurrence of some text in a Google Doc."""
    document_id = extract_id(document)
    reply = api(
        "POST", f"{BASE}/{document_id}:batchUpdate",
        body={"requests": [{"replaceAllText": {"containsText": {"text": find, "matchCase": bool(match_case)}, "replaceText": replace}}]},
    )
    changed = reply.get("replies", [{}])[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    return {"replaced": changed, "link": _url(document_id)}
