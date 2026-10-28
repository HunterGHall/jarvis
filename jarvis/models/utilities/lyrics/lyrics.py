import json
import urllib.error
import urllib.parse
import urllib.request

from media_control import get_now_playing

# LRCLIB, a free lyrics database that needs no key. It asks clients to identify themselves.
BASE_URL = "https://lrclib.net/api"
HEADERS = {"User-Agent": "Jarvis CLI assistant (https://github.com/HunterGHall/jarvis)"}


def _search(params):
    url = f"{BASE_URL}/search?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=10) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return []


def _best_match(results, artist):
    usable = [r for r in results if r.get("plainLyrics") or r.get("instrumental")]
    if artist:
        artist = artist.lower()
        for result in usable:
            if artist in (result.get("artistName") or "").lower():
                return result
    return usable[0] if usable else None


def get_lyrics(song=None, artist=None, synced=False):
    """Lyrics for a song. With no song given, uses whatever is playing right now."""
    if not song:
        playing = get_now_playing()
        if not playing or not playing.get("title"):
            return {"error": "Nothing is playing right now. Give a song title (and artist if you can)."}
        song, artist = playing["title"], artist or playing.get("artist")

    song, artist = song.strip(), (artist or "").strip()
    params = {"track_name": song}
    if artist:
        params["artist_name"] = artist
    match = _best_match(_search(params), artist)
    if match is None:
        # The exact fields found nothing, so try a looser free-text search.
        match = _best_match(_search({"q": f"{artist} {song}".strip()}), artist)
    if match is None:
        return {"error": f"No lyrics found for '{song}'" + (f" by {artist}." if artist else ".")}

    result = {
        "title": match.get("trackName"),
        "artist": match.get("artistName"),
        "album": match.get("albumName"),
        "duration_seconds": round(match["duration"]) if match.get("duration") else None,
        "instrumental": bool(match.get("instrumental")),
        "has_synced_lyrics": bool(match.get("syncedLyrics")),
    }
    if result["instrumental"]:
        return result
    if synced and match.get("syncedLyrics"):
        result["synced_lyrics"] = match["syncedLyrics"]
    else:
        result["lyrics"] = match["plainLyrics"]
    return result


if __name__ == "__main__":
    print(json.dumps(get_lyrics("Bohemian Rhapsody", "Queen"), indent=2)[:600])
