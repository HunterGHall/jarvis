import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from location import get_coordinates

SYNODIC_MONTH = 29.530588853
# A known new moon: 2000-01-06 18:14 UTC.
NEW_MOON_REFERENCE = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)

PHASES = [
    "New moon",
    "Waxing crescent",
    "First quarter",
    "Waxing gibbous",
    "Full moon",
    "Waning gibbous",
    "Last quarter",
    "Waning crescent",
]


def get_moon_phase():
    age = ((datetime.now(timezone.utc) - NEW_MOON_REFERENCE).total_seconds() / 86400) % SYNODIC_MONTH
    fraction = age / SYNODIC_MONTH
    # Each phase covers an eighth of the cycle, centered on its own point.
    phase = PHASES[int(fraction * 8 + 0.5) % 8]
    return {
        "phase": phase,
        "age_days": round(age, 1),
        "illumination_percent": round(50 * (1 - math.cos(2 * math.pi * fraction))),
    }


def get_sun_times(zip_code=None):
    location = get_coordinates(zip_code)
    if not location:
        return {}
    query = urllib.parse.urlencode(
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "daily": "sunrise,sunset,daylight_duration,sunshine_duration",
            "timezone": "auto",
            "forecast_days": 1,
        }
    )
    try:
        with urllib.request.urlopen(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=10) as response:
            daily = json.load(response)["daily"]
        daylight_seconds = daily["daylight_duration"][0]
        return {
            "location": f"{location['city']}, {location['state']}",
            "sunrise": daily["sunrise"][0].split("T")[1],
            "sunset": daily["sunset"][0].split("T")[1],
            "daylight_hours": round(daylight_seconds / 3600, 1),
            "sunshine_hours": round(daily["sunshine_duration"][0] / 3600, 1),
        }
    except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError):
        return {}


def get_sun_and_moon(zip_code=None):
    return {"sun": get_sun_times(zip_code), "moon": get_moon_phase()}


if __name__ == "__main__":
    print(json.dumps(get_sun_and_moon(), indent=2))
