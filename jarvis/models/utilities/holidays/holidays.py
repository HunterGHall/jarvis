import json
import urllib.error
import urllib.request
from datetime import date

# Nager.Date, a free public-holiday API that needs no key.
BASE_URL = "https://date.nager.at/api/v3"


def _fetch(path):
    try:
        with urllib.request.urlopen(f"{BASE_URL}/{path}", timeout=10) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return []


def _format(holiday, today):
    holiday_date = date.fromisoformat(holiday["date"])
    days = (holiday_date - today).days
    return {
        "name": holiday["name"],
        "local_name": holiday["localName"] if holiday["localName"] != holiday["name"] else None,
        "date": holiday["date"],
        "weekday": holiday_date.strftime("%A"),
        "days_until": days,
        "nationwide": holiday.get("global", True),
    }


def get_holidays(country="US", year=None, limit=10):
    """Upcoming public holidays by default, or every holiday in a given year."""
    country = country.strip().upper()
    today = date.today()
    if year:
        raw = _fetch(f"PublicHolidays/{int(year)}/{country}")
    else:
        raw = _fetch(f"NextPublicHolidays/{country}")
    if not raw:
        return {"error": f"No holiday data for '{country}'. Use a two-letter country code like US or GB."}
    holidays = [_format(holiday, today) for holiday in raw]
    if not year:
        holidays = holidays[: max(1, min(int(limit), 30))]
    return {"country": country, "year": int(year) if year else None, "holidays": holidays}


if __name__ == "__main__":
    print(json.dumps(get_holidays(limit=3), indent=2))
