import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

HEADERS = {"User-Agent": "Jarvis/1.0 (personal assistant; https://github.com/HunterGHall/jarvis)"}
OPENVERSE_URL = "https://api.openverse.org/v1/images/"
COMMONS_URL = "https://commons.wikimedia.org/w/api.php"
DOCS_TYPES = {"image/png", "image/jpeg", "image/gif"}  # what Google Docs accepts
MAX_IMAGE_BYTES = 50 * 1024 * 1024  # Google Docs' limit
SEARCH_TYPES = ("image/png", "image/jpeg", "image/gif")


class ImageError(Exception):
    pass


def _get_json(url, timeout=15):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None


def _openverse(query, limit):
    params = {"q": query, "page_size": min(limit * 3, 20), "mature": "false", "extension": "jpg,png,gif"}
    # Openverse is often slow or unreachable, so it only gets a short wait
    data = _get_json(f"{OPENVERSE_URL}?{urllib.parse.urlencode(params)}", timeout=6)
    images = []
    for item in (data or {}).get("results", []):
        extension = (item.get("filetype") or "").lower()
        if extension not in {"jpg", "jpeg", "png", "gif"} or not item.get("url", "").startswith("https://"):
            continue
        images.append(
            {
                "url": item["url"],
                "title": item.get("title") or query,
                "width": item.get("width"),
                "height": item.get("height"),
                # The text a license like CC BY asks you to show next to the picture
                "credit": item.get("attribution") or f"{item.get('title', '')} by {item.get('creator', 'unknown')} ({item.get('license', '').upper()})",
                "license": f"{item.get('license', '')} {item.get('license_version', '')}".strip().upper(),
                "page": item.get("foreign_landing_url"),
            }
        )
    return images[:limit]


def _commons(query, limit):
    params = {
        "action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap {query}", "gsrnamespace": 6, "gsrlimit": min(limit * 3, 20),
        "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata", "iiurlwidth": 1200, "format": "json",
    }
    data = _get_json(f"{COMMONS_URL}?{urllib.parse.urlencode(params)}")
    images = []
    for page in sorted((data or {}).get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("mime") not in SEARCH_TYPES:
            continue
        meta = info.get("extmetadata", {})
        artist = _plain(meta.get("Artist", {}).get("value", "")) or "unknown"
        license_name = meta.get("LicenseShortName", {}).get("value", "")
        title = page.get("title", "").removeprefix("File:")
        images.append(
            {
                # A scaled-down copy, so the file is a sensible size to put in a document
                "url": info.get("thumburl") or info.get("url"),
                "title": title,
                "width": info.get("thumbwidth") or info.get("width"),
                "height": info.get("thumbheight") or info.get("height"),
                "credit": f'"{title}" by {artist} ({license_name}), via Wikimedia Commons',
                "license": license_name,
                "page": info.get("descriptionurl"),
            }
        )
    return images[:limit]


def _plain(html):
    import re

    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def search_images(query, limit=5):
    """Finds pictures on the web that are free to reuse, with direct image links ready to put in a document."""
    limit = max(1, min(int(limit), 10))
    for source, search in (("Wikimedia Commons", _commons), ("Openverse", _openverse)):
        images = search(query, limit)
        if images:
            return {"query": query, "source": source, "count": len(images), "images": images}
    return {"error": f"Couldn't find any usable pictures of '{query}'. Try different words."}


def _check_public(url):
    parts = urllib.parse.urlparse(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ImageError("The image link must start with http:// or https://.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, parts.port or 443)}
    except OSError:
        raise ImageError(f"Couldn't find the website {parts.hostname}.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ImageError("That link points inside a private network, not to a picture on the web.")


def check_image(url, allowed=None):
    """Makes sure a link really is a picture that's publicly reachable. Returns its type (e.g. 'image/png')."""
    url = str(url).strip()
    _check_public(url)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=15) as response:
            mime = response.headers.get_content_type()
            size = int(response.headers.get("Content-Length") or 0)
    except urllib.error.HTTPError as error:
        raise ImageError(f"The website refused to give the picture (HTTP {error.code}). Google needs to be able to fetch it too.")
    except (OSError, ValueError):
        raise ImageError("Couldn't reach that link.")
    if not mime.startswith("image/"):
        raise ImageError(f"That link is a {mime} page, not a picture. It needs to be the direct link to the image file.")
    if allowed and mime not in allowed:
        raise ImageError(f"That picture is {mime}, but only {', '.join(sorted(t.split('/')[1].upper() for t in allowed))} can be used here.")
    if size > MAX_IMAGE_BYTES:
        raise ImageError("That picture is over 50 MB, which is too big.")
    return mime


if __name__ == "__main__":
    print(json.dumps(search_images("golden retriever", 2), indent=2))
