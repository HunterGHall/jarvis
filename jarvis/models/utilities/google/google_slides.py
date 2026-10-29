import secrets

from google_auth import api
from google_common import extract_id, safe
from web_images import DOCS_TYPES, ImageError, check_image

BASE = "https://slides.googleapis.com/v1/presentations"
EMU_PER_POINT = 12700

# Where a picture goes, as fractions of the slide: (left, top, right, bottom). All of them keep clear of a title at
# the top, and leave a strip underneath for a caption.
POSITIONS = {
    "center": (0.10, 0.22, 0.90, 0.89),
    "right": (0.52, 0.22, 0.95, 0.89),
    "left": (0.05, 0.22, 0.48, 0.89),
    "full": (0.0, 0.0, 1.0, 1.0),
}
LAYOUTS = {"title_and_body": "TITLE_AND_BODY", "title_only": "TITLE_ONLY"}


def _url(presentation_id):
    return f"https://docs.google.com/presentation/d/{presentation_id}/edit"


def _shape_text(shape):
    return "".join(run.get("textRun", {}).get("content", "") for run in shape.get("text", {}).get("textElements", [])).strip()


def _slide_requests(title, body, insertion_index=None, layout="title_and_body"):
    """The batch of requests that adds one slide and fills in its text boxes."""
    key = secrets.token_hex(4)
    slide_id, title_id, body_id = f"slide_{key}", f"title_{key}", f"body_{key}"
    create = {
        "objectId": slide_id,
        "slideLayoutReference": {"predefinedLayout": LAYOUTS[layout]},
        # Naming the placeholders lets the next requests fill them in without looking anything up
        "placeholderIdMappings": [{"layoutPlaceholder": {"type": "TITLE", "index": 0}, "objectId": title_id}]
        + ([{"layoutPlaceholder": {"type": "BODY", "index": 0}, "objectId": body_id}] if layout == "title_and_body" else []),
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
def slides_add_slide(presentation, title, body="", position=None, layout="title_and_body"):
    """Adds a slide to a presentation (at the end unless position says where, counting from 1). 'title_only' leaves room for a picture."""
    if layout not in LAYOUTS:
        return {"error": f"layout must be one of: {', '.join(LAYOUTS)}."}
    if body and layout == "title_only":
        return {"error": "The title_only layout has no body text. Leave body out, or use title_and_body."}
    presentation_id = extract_id(presentation)
    index = None if position is None else max(0, int(position) - 1)
    api("POST", f"{BASE}/{presentation_id}:batchUpdate", body={"requests": _slide_requests(title, body, index, layout)})
    return {"added": True, "title": title, "layout": layout, "link": _url(presentation_id)}


def _points(size):
    """A slide dimension from the API as points (it's usually given in EMU)."""
    return size["magnitude"] / EMU_PER_POINT if size.get("unit", "EMU") == "EMU" else size["magnitude"]


def _box(left, top, width, height):
    return {
        "size": {"width": {"magnitude": width, "unit": "PT"}, "height": {"magnitude": height, "unit": "PT"}},
        "transform": {"scaleX": 1, "scaleY": 1, "translateX": left, "translateY": top, "unit": "PT"},
    }


@safe
def slides_insert_image(presentation, image_url, slide=None, position="center", caption=None):
    """Puts a picture from the web on a slide (the last one unless `slide` says which), with an optional caption under it."""
    if position not in POSITIONS:
        return {"error": f"position must be one of: {', '.join(POSITIONS)}."}
    try:
        check_image(image_url, DOCS_TYPES)  # Slides only takes PNG, JPEG and GIF, and has to be able to fetch the link itself
    except ImageError as error:
        return {"error": str(error)}
    presentation_id = extract_id(presentation)
    deck = api("GET", f"{BASE}/{presentation_id}", params={"fields": "title,pageSize,slides(objectId)"})
    slides = deck.get("slides", [])
    if not slides:
        return {"error": "That presentation has no slides yet. Add one first."}
    number = len(slides) if slide is None else int(slide)
    if not 1 <= number <= len(slides):
        return {"error": f"There's no slide {number}; the presentation has {len(slides)}."}
    page_id = slides[number - 1]["objectId"]

    width, height = _points(deck["pageSize"]["width"]), _points(deck["pageSize"]["height"])
    left, top, right, bottom = POSITIONS[position]
    key = secrets.token_hex(4)
    # The picture is scaled to fit inside this box and centered in it, so its shape is never squashed
    requests = [
        {
            "createImage": {
                "objectId": f"image_{key}",
                "url": image_url,
                "elementProperties": {"pageObjectId": page_id, **_box(left * width, top * height, (right - left) * width, (bottom - top) * height)},
            }
        }
    ]
    if caption:
        caption_id = f"caption_{key}"
        requests += [
            {
                "createShape": {
                    "objectId": caption_id,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {"pageObjectId": page_id, **_box(left * width, 0.90 * height, (right - left) * width, 0.08 * height)},
                }
            },
            {"insertText": {"objectId": caption_id, "text": caption}},
            {"updateTextStyle": {"objectId": caption_id, "textRange": {"type": "ALL"}, "style": {"fontSize": {"magnitude": 9, "unit": "PT"}}, "fields": "fontSize"}},
        ]
    api("POST", f"{BASE}/{presentation_id}:batchUpdate", body={"requests": requests})
    return {"inserted": True, "slide": number, "position": position, "link": _url(presentation_id)}
