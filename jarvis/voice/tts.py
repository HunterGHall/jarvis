"""Text-to-speech through Fish Audio. Each piece of text is sent to their service and comes back as speech, in the
voice model picked with `reference_id` (settings are in the [voice] section of config.conf, the key in [fish])."""
import struct
import time
from configparser import ConfigParser

import numpy as np
import requests

from jarvis.models.default.default_model import CONFIG_PATH

URL = "https://api.fish.audio/v1/tts"
LATENCIES = {"low", "normal", "balanced"}
RETRY_CODES = {429, 500, 502, 503, 504}


def api_key():
    config = ConfigParser()
    config.read(CONFIG_PATH)
    return config.get("fish", "api_key", fallback="").strip().strip('"')


def available():
    """Raises a readable error if speech isn't set up yet."""
    if not api_key():
        raise RuntimeError("Speech needs a Fish Audio key. Add it to config.conf under [fish] as api_key = ... (get one at fish.audio).")


def _decode(wav):
    """16-bit WAV bytes -> (float32 samples shaped (n, channels), sample rate).

    Fish streams its WAV, so the header's length fields are placeholders (about 4 billion bytes). The audio is simply
    everything after the 'data' marker, which is why Python's wave module can't be used.
    """
    if wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise RuntimeError("Fish Audio sent back something that isn't audio.")
    position, rate, channels, bits = 12, None, 1, 16
    samples = None
    while position + 8 <= len(wav):
        kind, size = wav[position : position + 4], struct.unpack("<I", wav[position + 4 : position + 8])[0]
        body = position + 8
        if kind == b"fmt ":
            _, channels, rate, _, _, bits = struct.unpack("<HHIIHH", wav[body : body + 16])
        elif kind == b"data":
            samples = wav[body:] if size > len(wav) - body else wav[body : body + size]
            break
        position = body + size + (size & 1)
    if samples is None:
        raise RuntimeError("Fish Audio's reply had no audio in it.")
    if bits != 16 or rate is None:
        raise RuntimeError(f"Unexpected audio format from Fish Audio ({bits}-bit).")
    audio = np.frombuffer(samples[: len(samples) // 2 * 2], dtype="<i2").astype(np.float32) / 32768
    return audio.reshape(-1, channels), rate


def _error(response):
    if response.status_code == 401:
        return "Fish Audio rejected the key. Check api_key under [fish] in config.conf."
    if response.status_code == 402:
        return "Your Fish Audio account is out of credit."
    if response.status_code == 429:
        return "Fish Audio is limiting how fast speech can be requested. Wait a moment and try again."
    return f"Fish Audio error {response.status_code}: {response.text[:200]}"


def synthesize(text, s):
    """Returns (samples shaped (n, 1) float32, sample rate) for `text`, using the settings dict `s`."""
    available()
    body = {
        "text": text,
        "reference_id": s["reference_id"],
        "format": "wav",
        "latency": s["latency"] if s["latency"] in LATENCIES else "normal",
        "normalize": bool(s["normalize"]),
        "temperature": min(max(s["temperature"], 0.0), 1.0),
        "top_p": min(max(s["top_p"], 0.0), 1.0),
        "prosody": {"speed": min(max(s["speed"], 0.5), 2.0), "volume": s["volume"]},
    }
    headers = {"Authorization": f"Bearer {api_key()}", "model": s["model"]}
    response = None
    for attempt in range(2):
        try:
            response = requests.post(URL, headers=headers, json=body, timeout=60)
        except requests.RequestException as error:
            if attempt == 0:
                time.sleep(0.5)
                continue
            raise RuntimeError(f"Couldn't reach Fish Audio ({type(error).__name__}).")
        if response.status_code in RETRY_CODES and attempt == 0:
            time.sleep(0.5)  # one quiet retry for a hiccup on their side
            continue
        break
    if response.status_code != 200:
        raise RuntimeError(_error(response))
    return _decode(response.content)
