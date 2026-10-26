import json
import urllib.error
import urllib.parse
import urllib.request

from location import get_coordinates

AQI_LEVELS = [
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for sensitive groups"),
    (200, "Unhealthy"),
    (300, "Very unhealthy"),
]

UV_LEVELS = [
    (2, "Low"),
    (5, "Moderate"),
    (7, "High"),
    (10, "Very high"),
]


def _level(value, levels, top):
    return next((label for limit, label in levels if value <= limit), top)


def get_air_quality(zip_code=None):
    location = get_coordinates(zip_code)
    if not location:
        return {}
    query = urllib.parse.urlencode(
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": "us_aqi,pm10,pm2_5,ozone,nitrogen_dioxide,carbon_monoxide,uv_index",
            "timezone": "auto",
        }
    )
    try:
        with urllib.request.urlopen(
            f"https://air-quality-api.open-meteo.com/v1/air-quality?{query}", timeout=10
        ) as response:
            current = json.load(response)["current"]
        aqi, uv_index = current["us_aqi"], current["uv_index"]
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return {}
    return {
        "location": f"{location['city']}, {location['state']}",
        "us_aqi": aqi,
        "aqi_level": _level(aqi, AQI_LEVELS, "Hazardous") if aqi is not None else None,
        "pm2_5": current.get("pm2_5"),
        "pm10": current.get("pm10"),
        "ozone": current.get("ozone"),
        "nitrogen_dioxide": current.get("nitrogen_dioxide"),
        "carbon_monoxide": current.get("carbon_monoxide"),
        "uv_index": uv_index,
        "uv_level": _level(uv_index, UV_LEVELS, "Extreme") if uv_index is not None else None,
    }


if __name__ == "__main__":
    print(json.dumps(get_air_quality(), indent=2))
