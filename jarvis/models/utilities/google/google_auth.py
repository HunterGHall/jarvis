"""Google sign-in and a small client for the Google REST APIs, using only the standard library.

One-time setup (jarvis google-setup) opens a browser tab where you approve access. Jarvis then acts as you, so
it can reach your own mail, calendar and files without anything being shared with a bot account. The sign-in is kept
in google_token.json, next to the credentials file you download from Google Cloud.
"""
import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from jarvis.paths import GOOGLE_CREDENTIALS_PATH as CREDENTIALS_PATH, GOOGLE_TOKEN_PATH as TOKEN_PATH

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",  # read, draft, send, and trash mail (not delete it for good)
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/presentations",
]
SETUP_HINT = "Run 'jarvis google-setup' (or 'python main.py google-setup') to sign in again."

_lock = threading.Lock()
_token = None  # the saved sign-in, loaded on first use


class GoogleError(Exception):
    pass


def is_ready():
    """True once the credentials file is in place and someone has signed in."""
    return CREDENTIALS_PATH.exists() and TOKEN_PATH.exists()


# ---------------------------------------------------------------------------------------------- the sign-in

def _client():
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise GoogleError(f"Couldn't read {CREDENTIALS_PATH.name}. Download it again from Google Cloud (see the README).")
    client = data.get("installed") or data.get("web")
    if not client or "client_id" not in client:
        raise GoogleError(f"{CREDENTIALS_PATH.name} isn't an OAuth client file. Create a 'Desktop app' client and download that one.")
    return client


def _post_form(url, fields):
    """Posts a form to Google's token endpoint and returns its JSON reply (errors included)."""
    request = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), headers={"User-Agent": "Jarvis"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            return json.load(error)
        except ValueError:
            return {"error": f"http_{error.code}"}
    except (OSError, ValueError):
        raise GoogleError("Couldn't reach Google.")


def _save(token):
    TOKEN_PATH.write_text(json.dumps(token, indent=2), encoding="utf-8")


def authorize(open_browser=webbrowser.open, timeout=300):
    """Opens the consent page, waits for Google to send the browser back, and saves the sign-in."""
    client = _client()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    reply = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = {key: values[0] for key, values in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
            if "code" in query or "error" in query:  # ignores things like the browser asking for a favicon
                reply.update(query)
            ok = "code" in query
            message = "You're connected. You can close this tab and go back to Jarvis." if ok else "Something went wrong. Go back to Jarvis."
            page = f"<html><body style='font-family:sans-serif;margin:4em'><h2>{message}</h2></body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 1
    redirect = f"http://127.0.0.1:{server.server_address[1]}"
    url = AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": client["client_id"],
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",  # makes Google hand back a refresh token every time
            "state": state,
        }
    )
    open_browser(url)
    print(f"If a browser tab didn't open, go to:\n{url}\n")

    deadline = time.monotonic() + timeout
    try:
        while not reply and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if not reply:
        raise GoogleError(
            "Timed out waiting for you to approve access in the browser. If Google showed 'Error 403: access_denied' "
            "or said the app is being tested, add this Google account under Audience > Test users in Google Cloud "
            "(and press Publish app), then run the setup again."
        )
    if reply.get("error"):
        hint = " The account may not be allowed yet: add it under Audience > Test users in Google Cloud, and press Publish app." if reply["error"] == "access_denied" else ""
        raise GoogleError(f"Google said: {reply['error']}.{hint}")
    if reply.get("state") != state:
        raise GoogleError("The sign-in reply didn't match the request, so it was ignored.")

    fields = {
        "client_id": client["client_id"],
        "client_secret": client.get("client_secret", ""),
        "code": reply["code"],
        "code_verifier": verifier,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    }
    token = _post_form(TOKEN_URL, fields)
    if "refresh_token" not in token:
        raise GoogleError(f"Google didn't complete the sign-in ({token.get('error_description') or token.get('error') or 'no refresh token'}).")
    saved = {
        "refresh_token": token["refresh_token"],
        "access_token": token["access_token"],
        "expires_at": time.time() + int(token.get("expires_in", 3600)),
        "scope": token.get("scope", ""),
    }
    _save(saved)
    global _token
    _token = saved
    return saved


def access_token():
    """A valid access token, refreshed from the saved sign-in when it has run out."""
    global _token
    with _lock:
        if _token is None:
            try:
                _token = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise GoogleError(f"Not signed in to Google yet. {SETUP_HINT}")
        if _token.get("expires_at", 0) - 60 > time.time():
            return _token["access_token"]

        client = _client()
        refreshed = _post_form(
            TOKEN_URL,
            {
                "client_id": client["client_id"],
                "client_secret": client.get("client_secret", ""),
                "refresh_token": _token["refresh_token"],
                "grant_type": "refresh_token",
            },
        )
        if "access_token" not in refreshed:
            # Apps still in "Testing" on Google Cloud have their sign-in expire after 7 days
            raise GoogleError(f"Google sign-in has expired ({refreshed.get('error', 'unknown')}). {SETUP_HINT}")
        _token = {**_token, "access_token": refreshed["access_token"], "expires_at": time.time() + int(refreshed.get("expires_in", 3600))}
        _save(_token)
        return _token["access_token"]


def _forget_access_token():
    global _token
    with _lock:
        if _token:
            _token["expires_at"] = 0


# ---------------------------------------------------------------------------------------------- calling the APIs

def _open(request):
    """Sends a request and returns (status, body bytes). Kept separate so tests can stand in for Google."""
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, response.read()


def _message(error):
    try:
        detail = json.loads(error.read()).get("error", {})
        text = detail.get("message") if isinstance(detail, dict) else str(detail)
    except (ValueError, AttributeError):
        text = None
    if error.code == 403 and text and "insufficient" in text.lower():
        text += f" Approve every permission when signing in. {SETUP_HINT}"
    return text or f"Google returned HTTP {error.code}."


def api(method, url, *, params=None, body=None, data=None, content_type=None, raw=False):
    """Calls a Google API. Returns the parsed JSON (or the raw bytes with raw=True); raises GoogleError."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    payload = data if data is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
    for attempt in range(2):
        headers = {"Authorization": f"Bearer {access_token()}", "User-Agent": "Jarvis"}
        if payload is not None:
            headers["Content-Type"] = content_type or "application/json"
        try:
            _, content = _open(urllib.request.Request(url, data=payload, method=method, headers=headers))
        except urllib.error.HTTPError as error:
            if error.code == 401 and attempt == 0:
                _forget_access_token()  # the token may have been revoked or aged out early; get a fresh one once
                continue
            raise GoogleError(_message(error))
        except (OSError, ValueError):
            raise GoogleError("Couldn't reach Google.")
        break
    if raw:
        return content
    return json.loads(content) if content else {}
