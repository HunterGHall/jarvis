import json
import re
import urllib.error
import urllib.request
from configparser import ConfigParser
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[4] / "config.conf"
API_URL = "https://api.github.com/graphql"
MAX_MESSAGE_CHARS = 80  # GitHub's limit for a status message


class _GitHubError(Exception):
    pass


def _token():
    config = ConfigParser()
    config.read(CONFIG_PATH)
    token = config.get("github", "token", fallback="").strip().strip('"')
    # The first-run config template leaves a placeholder here
    return "" if token.upper().startswith("YOUR_") else token


def _post(payload, token):
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "Jarvis"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def _graphql(query, variables=None):
    token = _token()
    if not token:
        raise _GitHubError(
            "No GitHub token yet. Under [github] in config.conf, set token = ... to a classic personal access "
            "token with the 'user' scope."
        )
    try:
        reply = _post({"query": query, "variables": variables or {}}, token)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise _GitHubError("GitHub rejected the token. Check that it's current and has the 'user' scope.")
        raise _GitHubError(f"GitHub returned HTTP {error.code}.")
    except (OSError, ValueError):
        raise _GitHubError("Couldn't reach GitHub.")
    if reply.get("errors"):
        raise _GitHubError("; ".join(error.get("message", "Unknown error") for error in reply["errors"]))
    return reply["data"]


def _emoji(value):
    """Accepts a unicode emoji, ':computer:', or just 'computer'."""
    value = (value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_+\-]+", value):
        return f":{value}:"
    return value or None


def _describe(status):
    if not status:
        return None
    described = {"message": status.get("message"), "emoji": status.get("emoji"), "expires_at": status.get("expiresAt")}
    if status.get("indicatesLimitedAvailability"):
        described["busy"] = True
    return described


def get_github_status():
    """The status currently shown on the user's GitHub profile."""
    try:
        viewer = _graphql("query { viewer { login status { message emoji expiresAt } } }")["viewer"]
    except _GitHubError as error:
        return {"error": str(error)}
    return {"user": viewer["login"], "status": _describe(viewer["status"])}


def set_github_status(message, emoji=None, minutes=None, busy=False):
    """Sets the status on the user's GitHub profile. minutes makes it clear itself; busy shows the 'busy' indicator."""
    message = (message or "").strip()
    if len(message) > MAX_MESSAGE_CHARS:
        return {"error": f"A GitHub status can be at most {MAX_MESSAGE_CHARS} characters; this one is {len(message)}."}
    expires_at = None
    if minutes:
        if float(minutes) <= 0:
            return {"error": "minutes must be more than zero."}
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=float(minutes))).strftime("%Y-%m-%dT%H:%M:%SZ")

    # The busy flag is only sent when asked for, so a problem with it can't affect ordinary status changes
    flag_argument, flag_variable, flag_field = ("limitedAvailability: $busy", ", $busy: Boolean", " indicatesLimitedAvailability") if busy else ("", "", "")
    query = (
        "mutation($message: String, $emoji: String, $expiresAt: DateTime" + flag_variable + ") { "
        "changeUserStatus(input: {message: $message, emoji: $emoji, expiresAt: $expiresAt" + (", " + flag_argument if busy else "") + "}) "
        "{ status { message emoji expiresAt" + flag_field + " } } }"
    )
    variables = {"message": message, "emoji": _emoji(emoji), "expiresAt": expires_at}
    if busy:
        variables["busy"] = True
    try:
        status = _graphql(query, variables)["changeUserStatus"]["status"]
    except _GitHubError as error:
        return {"error": str(error)}
    return {"set": True, "status": _describe(status)}


def clear_github_status():
    """Removes the status from the user's GitHub profile."""
    query = "mutation($message: String, $emoji: String) { changeUserStatus(input: {message: $message, emoji: $emoji}) { status { message emoji } } }"
    try:
        # An empty status is how GitHub clears it. Check afterwards instead of assuming it worked.
        _graphql(query, {"message": "", "emoji": ""})
        remaining = _graphql("query { viewer { status { message emoji } } }")["viewer"]["status"]
    except _GitHubError as error:
        return {"error": str(error)}
    if remaining:
        return {"error": "GitHub still shows a status after trying to clear it.", "status": _describe(remaining)}
    return {"cleared": True}


if __name__ == "__main__":
    print(json.dumps(get_github_status(), indent=2))
