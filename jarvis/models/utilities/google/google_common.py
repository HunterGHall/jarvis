"""Helpers shared by the Google tools."""
import functools
import re

from google_auth import GoogleError

import file_operations


def safe(function):
    """Turns a Google failure into the {"error": ...} reply every Jarvis tool gives, instead of an exception."""

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except GoogleError as error:
            return {"error": str(error)}

    return wrapper


def extract_id(value):
    """The id from a Google link, or the value itself if it already is one."""
    value = str(value).strip()
    match = re.search(r"/d/([A-Za-z0-9_-]+)", value) or re.search(r"[?&]id=([A-Za-z0-9_-]+)", value) or re.search(r"/folders/([A-Za-z0-9_-]+)", value)
    return match.group(1) if match else value


def approve(message, spoken):
    """Asks the user before Jarvis does something that reaches other people or can't be undone easily."""
    return file_operations.confirm(message, spoken)


def declined():
    return {"done": False, "reason": "The user declined, or confirmation wasn't available."}


def clip(text, limit):
    return text if len(text) <= limit else text[:limit] + f"\n... [{len(text) - limit} more characters]"
