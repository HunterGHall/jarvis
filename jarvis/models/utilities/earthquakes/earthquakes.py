import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from location import get_coordinates

BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1"


def _get_json(path, params):
    url = f"{BASE_URL}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return {}


def _distance_miles(lat1, lon1, lat2, lon2):
    # Haversine great-circle distance.
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi, delta_lambda = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def _age(when):
    minutes = int((datetime.now(timezone.utc) - when).total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 0)}m ago"
    if minutes < 60 * 24:
        return f"{minutes // 60}h ago"
    return f"{minutes // (60 * 24)}d ago"


def get_earthquakes(min_magnitude=4.5, days=1, limit=10, sort_by="time", near_me=False, radius_miles=200, zip_code=None):
    """Recent earthquakes worldwide from the USGS, or near the user's location."""
    days = max(1, min(int(days), 30))
    limit = max(1, min(int(limit), 50))
    params = {
        "format": "geojson",
        "minmagnitude": min_magnitude,
        "starttime": (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
        "orderby": "magnitude" if sort_by == "magnitude" else "time",
    }

    origin = None
    if near_me:
        location = get_coordinates(zip_code)
        if not location:
            return {"error": "Couldn't work out your location."}
        origin = (location["latitude"], location["longitude"])
        params.update(latitude=origin[0], longitude=origin[1], maxradiuskm=round(float(radius_miles) * 1.60934))

    data = _get_json("query", {**params, "limit": limit})
    if "features" not in data:
        return {"error": "Couldn't reach the USGS earthquake feed."}
    total = _get_json("count", params).get("count")

    quakes = []
    for feature in data["features"]:
        properties, (longitude, latitude, depth) = feature["properties"], feature["geometry"]["coordinates"]
        when = datetime.fromtimestamp(properties["time"] / 1000, tz=timezone.utc)
        quake = {
            "magnitude": properties["mag"],
            "place": properties["place"],
            "time": when.astimezone().strftime("%Y-%m-%d %H:%M"),
            "ago": _age(when),
            "depth_miles": round(depth * 0.621371, 1),
            "tsunami_message": bool(properties.get("tsunami")),
            "felt_reports": properties.get("felt"),
            "impact_alert": properties.get("alert"),
            "url": properties.get("url"),
        }
        if origin:
            quake["miles_from_you"] = round(_distance_miles(*origin, latitude, longitude))
        quakes.append(quake)

    return {
        "scope": f"within {round(float(radius_miles))} miles of you" if near_me else "worldwide",
        "min_magnitude": min_magnitude,
        "days": days,
        "total_matches": total if total is not None else len(quakes),
        "returned": len(quakes),
        "earthquakes": quakes,
    }


if __name__ == "__main__":
    print(json.dumps(get_earthquakes(limit=3), indent=2))
