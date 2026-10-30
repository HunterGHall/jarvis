import configparser
import json
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[4] / "config.conf"


def get_zip_code():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config.get("personal", "zip_code", fallback="").strip().strip('"')


def get_coordinates(zip_code=None):
    zip_code = zip_code or get_zip_code()
    if not zip_code:
        return {}
    try:
        with urllib.request.urlopen(f"https://api.zippopotam.us/us/{zip_code}", timeout=10) as response:
            data = json.load(response)
        place = data["places"][0]
        return {
            "zip_code": zip_code,
            "city": place["place name"],
            "state": place["state abbreviation"],
            "latitude": float(place["latitude"]),
            "longitude": float(place["longitude"]),
        }
    except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError):
        return {}


if __name__ == "__main__":
    print(json.dumps(get_coordinates(), indent=2))
