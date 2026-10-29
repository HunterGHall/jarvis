import base64
import html
import re
from email.message import EmailMessage

from google_auth import api
from google_common import approve, clip, declined, safe

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_BODY_CHARS = 8000
HEADER_NAMES = ["From", "To", "Cc", "Subject", "Date"]


def _headers(message):
    return {header["name"].lower(): header["value"] for header in message.get("payload", {}).get("headers", [])}


def _decode(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _strip_html(text):
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def _body_and_attachments(part, bodies=None, attachments=None):
    """Walks a message's parts: plain text and HTML bodies, plus the names of any attachments."""
    bodies = {"text/plain": [], "text/html": []} if bodies is None else bodies
    attachments = [] if attachments is None else attachments
    mime = part.get("mimeType", "")
    if part.get("filename"):
        attachments.append(part["filename"])
    elif mime in bodies and part.get("body", {}).get("data"):
        bodies[mime].append(_decode(part["body"]["data"]))
    for child in part.get("parts", []):
        _body_and_attachments(child, bodies, attachments)
    return bodies, attachments


@safe
def gmail_search(query="", limit=10):
    """Finds messages with Gmail's own search syntax (from:, is:unread, newer_than:2d, has:attachment...)."""
    limit = max(1, min(int(limit), 25))
    listing = api("GET", f"{BASE}/messages", params={"q": query, "maxResults": limit})
    results = []
    for entry in listing.get("messages", []):
        message = api(
            "GET",
            f"{BASE}/messages/{entry['id']}",
            params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
        )
        headers = _headers(message)
        results.append(
            {
                "id": message["id"],
                "from": headers.get("from"),
                "subject": headers.get("subject"),
                "date": headers.get("date"),
                "unread": "UNREAD" in message.get("labelIds", []),
                "snippet": message.get("snippet"),
            }
        )
    return {"query": query, "count": len(results), "messages": results}


@safe
def gmail_read(message_id):
    """The full text of one message, with who it's from, to, and its attachment names."""
    message = api("GET", f"{BASE}/messages/{message_id}", params={"format": "full"})
    headers = _headers(message)
    bodies, attachments = _body_and_attachments(message.get("payload", {}))
    text = "\n".join(bodies["text/plain"]).strip() or _strip_html("\n".join(bodies["text/html"]))
    result = {name.lower(): headers.get(name.lower()) for name in HEADER_NAMES}
    result.update({"id": message["id"], "thread_id": message.get("threadId"), "body": clip(text, MAX_BODY_CHARS)})
    if attachments:
        result["attachments"] = attachments
    return result


def _build(to, subject, body, cc=None, bcc=None, reply_to=None):
    email = EmailMessage()
    email["To"] = to
    if cc:
        email["Cc"] = cc
    if bcc:
        email["Bcc"] = bcc
    email["Subject"] = subject
    thread_id = None
    if reply_to:
        original = api("GET", f"{BASE}/messages/{reply_to}", params={"format": "metadata", "metadataHeaders": ["Message-ID", "References", "Subject"]})
        headers = _headers(original)
        thread_id = original.get("threadId")
        if headers.get("message-id"):
            email["In-Reply-To"] = headers["message-id"]
            email["References"] = f"{headers.get('references', '')} {headers['message-id']}".strip()
    email.set_content(body)
    payload = {"raw": base64.urlsafe_b64encode(email.as_bytes()).decode()}
    if thread_id:
        payload["threadId"] = thread_id
    return payload


@safe
def gmail_send(to, subject, body, cc=None, bcc=None, reply_to_message_id=None):
    """Sends an email (as a reply in the same thread if reply_to_message_id is given), after the user approves it."""
    preview = clip(body, 1500)
    message = (
        f"Send this email?\n\n    To: {to}\n" + (f"    Cc: {cc}\n" if cc else "") + (f"    Bcc: {bcc}\n" if bcc else "")
        + f"    Subject: {subject}\n\n" + "\n".join(f"    {line}" for line in preview.splitlines()) + "\n"
    )
    if not approve(message, f"Shall I send an email to {to} with the subject {subject}?"):
        return declined()
    sent = api("POST", f"{BASE}/messages/send", body=_build(to, subject, body, cc, bcc, reply_to_message_id))
    return {"sent": True, "id": sent.get("id"), "thread_id": sent.get("threadId"), "to": to, "subject": subject}


@safe
def gmail_create_draft(to, subject, body, cc=None):
    """Saves a draft in Gmail without sending it."""
    draft = api("POST", f"{BASE}/drafts", body={"message": _build(to, subject, body, cc)})
    return {"drafted": True, "draft_id": draft.get("id"), "to": to, "subject": subject, "note": "It's in the Drafts folder, not sent."}


@safe
def gmail_trash(message_id):
    """Moves a message to Gmail's Trash (it can be restored from there), after the user approves."""
    message = api("GET", f"{BASE}/messages/{message_id}", params={"format": "metadata", "metadataHeaders": ["From", "Subject"]})
    headers = _headers(message)
    subject, sender = headers.get("subject") or "(no subject)", headers.get("from") or "someone"
    if not approve(f"Move this email to the Trash?\n\n    From: {sender}\n    Subject: {subject}\n", f"Shall I move the email from {sender} about {subject} to the trash?"):
        return declined()
    api("POST", f"{BASE}/messages/{message_id}/trash")
    return {"trashed": True, "subject": subject, "note": "It's in Gmail's Trash and can be restored."}
