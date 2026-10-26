import json
import urllib.error
import urllib.parse
import urllib.request

from current_weather import WEATHER_CODES
from location import get_coordinates


def _fetch_forecast(location, days):
    query = urllib.parse.urlencode(
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max,precipitation_sum,wind_speed_10m_max,sunrise,sunset",
            "current": "temperature_2m",
            "hourly": "temperature_2m,precipitation_probability,weather_code",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "auto",
            "forecast_days": days,
        }
    )
    try:
        with urllib.request.urlopen(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=10) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return {}


def get_daily_forecast(days=7, zip_code=None):
    location = get_coordinates(zip_code)
    if not location:
        return {}
    data = _fetch_forecast(location, days)
    try:
        daily = data["daily"]
        forecast = [
            {
                "date": daily["time"][i],
                "conditions": WEATHER_CODES.get(daily["weather_code"][i], "Unknown"),
                "high_f": daily["temperature_2m_max"][i],
                "low_f": daily["temperature_2m_min"][i],
                "rain_chance_percent": daily["precipitation_probability_max"][i],
                "precipitation_in": daily["precipitation_sum"][i],
                "wind_mph": daily["wind_speed_10m_max"][i],
                "sunrise": daily["sunrise"][i].split("T")[1],
                "sunset": daily["sunset"][i].split("T")[1],
            }
            for i in range(len(daily["time"]))
        ]
    except (KeyError, IndexError):
        return {}
    return {"location": f"{location['city']}, {location['state']}", "days": forecast}


def get_hourly_forecast(hours=12, zip_code=None):
    location = get_coordinates(zip_code)
    if not location:
        return {}
    data = _fetch_forecast(location, 2)
    try:
        hourly = data["hourly"]
        current_time = data["current"]["time"] if "current" in data else None
        # Open-Meteo hourly entries are local ISO strings, so they sort lexically.
        start = 0
        if current_time:
            start = next((i for i, t in enumerate(hourly["time"]) if t >= current_time), 0)
        forecast = [
            {
                "time": hourly["time"][i].split("T")[1],
                "conditions": WEATHER_CODES.get(hourly["weather_code"][i], "Unknown"),
                "temperature_f": hourly["temperature_2m"][i],
                "rain_chance_percent": hourly["precipitation_probability"][i],
            }
            for i in range(start, min(start + hours, len(hourly["time"])))
        ]
    except (KeyError, IndexError):
        return {}
    return {"location": f"{location['city']}, {location['state']}", "hours": forecast}


if __name__ == "__main__":
    print(json.dumps(get_daily_forecast(), indent=2))
