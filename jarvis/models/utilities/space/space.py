import json
import time
import urllib.error
import urllib.parse
import urllib.request

# NASA's shared demo key is rate limited but needs no signup.
APOD_URL = "https://api.nasa.gov/planetary/apod"
ISS_URL = "https://api.wheretheiss.at/v1/satellites/25544"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _get_json(url, attempts=3):
    request = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)
        except (OSError, ValueError, urllib.error.URLError):
            # The NASA API sometimes answers 500 once and then works.
            if attempt < attempts - 1:
                time.sleep(1.5)
    return {}


def get_apod(date=None):
    """NASA's Astronomy Picture of the Day, for today or a given YYYY-MM-DD date."""
    params = {"api_key": "DEMO_KEY"}
    if date:
        params["date"] = date.strip()
    data = _get_json(f"{APOD_URL}?{urllib.parse.urlencode(params)}")
    if not data or "title" not in data:
        return {"error": "Couldn't get the picture of the day. NASA's service may be busy, or the date is out of range."}
    return {
        "date": data.get("date"),
        "title": data["title"],
        "explanation": " ".join((data.get("explanation") or "").split()),
        "media_type": data.get("media_type"),
        "url": data.get("hdurl") or data.get("url"),
        "credit": data.get("copyright", "").strip() or "NASA",
    }


def get_iss():
    """Where the International Space Station is right now."""
    data = _get_json(ISS_URL)
    if "latitude" not in data:
        return {"error": "Couldn't reach the ISS tracker."}
    latitude, longitude = data["latitude"], data["longitude"]
    place = _get_json(f"https://api.wheretheiss.at/v1/coordinates/{latitude},{longitude}")
    country = place.get("country_code")
    return {
        "latitude": round(latitude, 2),
        "longitude": round(longitude, 2),
        # The tracker reports "??" over open water.
        "over": f"country code {country}" if country and country != "??" else "open ocean",
        "altitude_miles": round(data["altitude"] * 0.621371),
        "speed_mph": round(data["velocity"] * 0.621371),
        "sunlight": data.get("visibility"),
        "map": place.get("map_url"),
    }


if __name__ == "__main__":
    print(json.dumps(get_iss(), indent=2))
    print(json.dumps(get_apod(), indent=2)[:500])
