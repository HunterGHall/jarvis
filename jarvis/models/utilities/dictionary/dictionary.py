import json
import urllib.error
import urllib.parse
import urllib.request


def define(word):
    word = word.strip().lower()
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            entry = json.load(response)[0]
    except (OSError, ValueError, IndexError, urllib.error.URLError):
        return {}
    meanings = []
    for meaning in entry.get("meanings", []):
        definitions = meaning.get("definitions", [])
        meanings.append(
            {
                "part_of_speech": meaning.get("partOfSpeech"),
                "definitions": [d["definition"] for d in definitions[:3]],
                "example": next((d["example"] for d in definitions if d.get("example")), None),
                "synonyms": meaning.get("synonyms", [])[:5],
                "antonyms": meaning.get("antonyms", [])[:5],
            }
        )
    return {
        "word": entry.get("word", word),
        "phonetic": entry.get("phonetic"),
        "meanings": meanings,
    }


def get_synonyms(word):
    return sorted({s for m in define(word).get("meanings", []) for s in m["synonyms"]})


def get_antonyms(word):
    return sorted({a for m in define(word).get("meanings", []) for a in m["antonyms"]})


if __name__ == "__main__":
    print(json.dumps(define("serendipity"), indent=2))
