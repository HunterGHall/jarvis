import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from location import get_coordinates

BASE_URL = "https://news.google.com/rss"
EDITION = "hl=en-US&gl=US&ceid=US:en"

TOPICS = {
    "top": None,
    "world": "WORLD",
    "us": "NATION",
    "business": "BUSINESS",
    "tech": "TECHNOLOGY",
    "entertainment": "ENTERTAINMENT",
    "sports": "SPORTS",
    "science": "SCIENCE",
    "health": "HEALTH",
    "local": "local",
}

# Related-coverage entries inside each item's description: a headline link followed by its outlet.
RELATED_PATTERN = re.compile(r'<a href="[^"]*"[^>]*>(.*?)</a>\s*<font[^>]*>(.*?)</font>')


def _age(published):
    try:
        seconds = (datetime.now(timezone.utc) - parsedate_to_datetime(published)).total_seconds()
    except (TypeError, ValueError):
        return None
    minutes = int(seconds // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    if minutes < 60 * 24:
        return f"{minutes // 60}h ago"
    return f"{minutes // (60 * 24)}d ago"


def _parse_story(item):
    title = item.findtext("title", "")
    headline, _, outlet = title.rpartition(" - ")
    if not headline:
        headline, outlet = title, ""
    source = item.findtext("source") or outlet

    related = RELATED_PATTERN.findall(html.unescape(item.findtext("description", "")))
    # The story's own entry is listed first among its related coverage, so skip the lead outlet.
    others = []
    for _, other_source in related:
        other_source = html.unescape(other_source).strip()
        if other_source and other_source != source and other_source not in others:
            others.append(other_source)

    return {
        "headline": headline.strip(),
        "source": source.strip(),
        "published": _age(item.findtext("pubDate")),
        "also_reported_by": others[:5],
        "link": item.findtext("link"),
    }


def _fetch_stories(url, limit):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            items = ET.fromstring(response.read()).findall("./channel/item")
    except (OSError, ValueError, ET.ParseError, urllib.error.URLError):
        return []

    stories, seen = [], set()
    for item in items:
        story = _parse_story(item)
        key = story["headline"].lower()
        if key in seen:
            continue
        seen.add(key)
        stories.append(story)
        if len(stories) >= max(1, min(int(limit), 20)):
            break
    return stories


def get_headlines(topic="top", limit=8, zip_code=None):
    topic = topic.strip().lower()
    if topic not in TOPICS:
        return {"error": f"Unknown topic '{topic}'.", "topics": list(TOPICS)}

    if topic == "top":
        url = f"{BASE_URL}?{EDITION}"
    elif topic == "local":
        location = get_coordinates(zip_code)
        if not location:
            return {"error": "Couldn't work out your location for local news."}
        place = urllib.parse.quote(f"{location['city']}, {location['state']}")
        url = f"{BASE_URL}/headlines/section/geo/{place}?{EDITION}"
    else:
        url = f"{BASE_URL}/headlines/section/topic/{TOPICS[topic]}?{EDITION}"

    stories = _fetch_stories(url, limit)
    if not stories:
        return {}
    return {"topic": topic, "stories": stories}


def search_news(query, days=3, limit=8):
    days = max(1, min(int(days), 30))
    search = urllib.parse.quote(f"{query.strip()} when:{days}d")
    stories = _fetch_stories(f"{BASE_URL}/search?q={search}&{EDITION}", limit)
    if not stories:
        return {}
    return {"query": query.strip(), "days": days, "stories": stories}


if __name__ == "__main__":
    print(json.dumps(get_headlines("top", 3), indent=2))
    print(json.dumps(search_news("NASA", 2, 3), indent=2))
