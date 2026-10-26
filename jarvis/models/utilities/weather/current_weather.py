import json
import urllib.error
import urllib.parse
import urllib.request

from location import get_coordinates

# WMO weather interpretation codes used by Open-Meteo.
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def get_weather(zip_code=None):
    location = get_coordinates(zip_code)
    if not location:
        return {}
    query = urllib.parse.urlencode(
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
            "precipitation,weather_code,wind_speed_10m",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
        }
    )
    try:
        with urllib.request.urlopen(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=10) as response:
            current = json.load(response)["current"]
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return {}
    return {
        "location": f"{location['city']}, {location['state']}",
        "conditions": WEATHER_CODES.get(current["weather_code"], "Unknown"),
        "temperature_f": current["temperature_2m"],
        "feels_like_f": current["apparent_temperature"],
        "humidity_percent": current["relative_humidity_2m"],
        "precipitation_in": current["precipitation"],
        "wind_mph": current["wind_speed_10m"],
    }


if __name__ == "__main__":
    print(json.dumps(get_weather(), indent=2))
