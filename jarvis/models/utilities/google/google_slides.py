import secrets

from google_auth import api
from google_common import extract_id, safe

BASE = "https://slides.googleapis.com/v1/presentations"


def _url(presentation_id):
    return f"https://docs.google.com/presentation/d/{presentation_id}/edit"


def _shape_text(shape):
    return "".join(run.get("textRun", {}).get("content", "") for run in shape.get("text", {}).get("textElements", [])).strip()


def _slide_requests(title, body, insertion_index=None):
    """The batch of requests that adds one 'title and body' slide and fills in its two text boxes."""
    key = secrets.token_hex(4)
    slide_id, title_id, body_id = f"slide_{key}", f"title_{key}", f"body_{key}"
    create = {
        "objectId": slide_id,
        "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"},
        # Naming the placeholders lets the next requests fill them in without looking anything up
        "placeholderIdMappings": [
            {"layoutPlaceholder": {"type": "TITLE", "index": 0}, "objectId": title_id},
            {"layoutPlaceholder": {"type": "BODY", "index": 0}, "objectId": body_id},
        ],
    }
    if insertion_index is not None:
        create["insertionIndex"] = insertion_index
    requests = [{"createSlide": create}]
    if title:
        requests.append({"insertText": {"objectId": title_id, "text": title}})
    if body:
        requests.append({"insertText": {"objectId": body_id, "text": body}})
    return requests


@safe
def slides_read(presentation):
    """The text on each slide of a Google Slides presentation, and its speaker notes."""
    presentation_id = extract_id(presentation)
    deck = api("GET", f"{BASE}/{presentation_id}")
    slides = []
    for number, slide in enumerate(deck.get("slides", []), 1):
        texts = [_shape_text(element["shape"]) for element in slide.get("pageElements", []) if "shape" in element]
        entry = {"slide": number, "text": [text for text in texts if text]}
        notes = slide.get("slideProperties", {}).get("notesPage", {}).get("pageElements", [])
        note_text = [_shape_text(element["shape"]) for element in notes if "shape" in element]
        if any(note_text):
            entry["notes"] = " ".join(text for text in note_text if text)
        slides.append(entry)
    return {"title": deck.get("title"), "id": presentation_id, "slide_count": len(slides), "slides": slides, "link": _url(presentation_id)}


@safe
def slides_create(title, slides=None):
    """Creates a presentation with a 'title and body' slide for each entry in `slides` (each has a title and body)."""
    deck = api("POST", BASE, body={"title": title})
    presentation_id = deck["presentationId"]
    if slides:
        requests = []
        for slide in slides:
            requests += _slide_requests(slide.get("title", ""), slide.get("body", ""))
        # A new presentation starts with one empty slide; remove it so the deck begins with the first real one
        requests.append({"deleteObject": {"objectId": deck["slides"][0]["objectId"]}})
        api("POST", f"{BASE}/{presentation_id}:batchUpdate", body={"requests": requests})
    return {"created": True, "title": title, "id": presentation_id, "slides": len(slides or []), "link": _url(presentation_id)}


@safe
def slides_add_slide(presentation, title, body="", position=None):
    """Adds a 'title and body' slide to a presentation (at the end unless position says where, counting from 1)."""
    presentation_id = extract_id(presentation)
    index = None if position is None else max(0, int(position) - 1)
    api("POST", f"{BASE}/{presentation_id}:batchUpdate", body={"requests": _slide_requests(title, body, index)})
    return {"added": True, "title": title, "link": _url(presentation_id)}
