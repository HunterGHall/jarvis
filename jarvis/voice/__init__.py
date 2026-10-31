"""Voice mode: microphone -> faster-whisper (on this PC) -> Jarvis -> Fish Audio text-to-speech -> speakers."""
import io
import os
import queue
import re
import threading
import time
import wave
from configparser import ConfigParser

import numpy as np
import sounddevice as sd

from jarvis import config_file
from jarvis.voice import tts
from jarvis.models.default.default_model import CONFIG_PATH

SAMPLE_RATE = 16000
BLOCK = 480  # 30 ms
CALIBRATION_BLOCKS = 10
MIN_SPEECH = 0.3  # shorter than this is treated as a noise blip
MAX_UTTERANCE = 30.0
EXIT_PHRASES = {"exit", "quit", "stop", "goodbye", "stop listening", "exit voice mode", "end voice mode"}

SECTION = "voice"
_config = ConfigParser()
_config.read(CONFIG_PATH)


def _setting(key, default):
    return _config.get(SECTION, key, fallback=default).strip().strip('"') or default


def _bool(text):
    value = str(text).strip().lower()
    if value in {"true", "yes", "on", "1"}:
        return True
    if value in {"false", "no", "off", "0"}:
        return False
    raise ValueError(text)


# Voice settings used for every speech request; change them live with `/voice set <name> <value>`.
# name: (default, type, what it does). The default reference_id is the Jarvis voice model on Fish Audio.
OPTIONS = {
    "reference_id": ("2b16afc295934c50b056b0b942e1c1a5", str, "Fish Audio voice model id (browse voices at fish.audio)"),
    "model": ("s2.1-pro-free", str, "Fish Audio speech model: s1, s2-pro, s2.1-pro, s2.1-pro-free, drama-3"),
    "speed": ("1.0", float, "speaking speed, 0.5-2"),
    "volume": ("0", float, "volume change in decibels (positive is louder)"),
    "latency": ("low", str, "normal, balanced, or low (lower starts sooner, may sound rougher)"),
    "temperature": ("0.7", float, "how much the delivery varies, 0-1"),
    "top_p": ("0.7", float, "how adventurous the delivery is, 0-1"),
    "normalize": ("true", _bool, "say numbers and symbols as words"),
    "silence": ("0.8", float, "seconds of quiet that end your turn when listening"),
    "wake_word": ("jarvis", str, 'the word that wakes Jarvis when you speak to it; "none" skips this and keeps it always listening'),
    "wake_mode": ("every_time", str, "every_time: say the wake word before every request; stay_awake: after the wake word it keeps listening, without it, until idle_timeout seconds of silence"),
    "idle_timeout": ("30", float, "with wake_mode stay_awake, the seconds of silence before Jarvis goes back to sleep and needs the wake word again (also how long it waits for your request after hearing just its name)"),
    "mic_threshold": ("100", float, "the quietest sound that counts as speech; lower hears softer voices"),
    "noise_margin": ("2", float, "how many times louder than the room's background noise your voice must be; lower is more sensitive"),
}
settings = {}


def reload():
    """Reads the [voice] settings from config.conf again (after they were changed somewhere else)."""
    _config.read(CONFIG_PATH)
    for name, (default, kind, _) in OPTIONS.items():
        raw = _setting(name, default)
        try:
            settings[name] = kind(raw) if raw != "" else None
        except ValueError:
            settings[name] = kind(default) if default != "" else None


reload()


def set_option(name, value):
    """Changes a voice setting and saves it to config.conf; returns the stored value."""
    if name not in OPTIONS:
        raise KeyError(name)
    kind = OPTIONS[name][1]
    stored = kind(value)
    config_file.update({SECTION: {name: stored}})
    reload()
    return settings[name]


def check_ready():
    """Raises a readable error if the packages voice mode needs are missing."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        raise RuntimeError("Listening needs faster-whisper. Run: pip install -r requirements.txt")
    tts.available()


def preload():
    """Loads the listening model, so voice is ready when the chat starts.

    Returns an error message if something failed (None otherwise); does nothing when `preload = false` in config.conf.
    """
    if _setting("preload", "true").lower() not in {"true", "yes", "on", "1"}:
        return None
    try:
        check_ready()
        _whisper_model()
    except Exception as error:
        return f"{type(error).__name__}: {error}"
    return None


def _to_wav(samples):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(samples.tobytes())
    return buffer.getvalue()


def listen(on_state=None, cancel=None, max_wait=None):
    """Blocks until the user speaks and then pauses; returns WAV bytes.

    Returns None if it was only a blip, `cancel` was set, or nothing was said for `max_wait` seconds.
    """
    if on_state:
        on_state("listening")
    recent = []  # rolling pre-roll, so the first word is not clipped
    blocks = []
    noise = []
    threshold = None
    speech = quiet = 0
    started = time.monotonic()
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=BLOCK) as stream:
        while True:
            if cancel is not None and cancel.is_set():
                return None
            if max_wait is not None and not blocks and time.monotonic() - started > max_wait:
                return None
            data, _ = stream.read(BLOCK)
            frame = data[:, 0].copy()
            level = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
            if threshold is None:
                # The first ~0.3 s measures the room's background level.
                noise.append(level)
                recent.append(frame)
                if len(noise) >= CALIBRATION_BLOCKS:
                    threshold = max(np.mean(noise) * settings["noise_margin"], settings["mic_threshold"])
                continue
            if not blocks:
                recent = (recent + [frame])[-CALIBRATION_BLOCKS:]
                if level > threshold:
                    blocks = list(recent)
                    speech = 1
                    if on_state:
                        on_state("hearing")
                continue
            blocks.append(frame)
            if level > threshold:
                speech += 1
                quiet = 0
            else:
                quiet += 1
            if quiet * BLOCK / SAMPLE_RATE >= settings["silence"] or len(blocks) * BLOCK / SAMPLE_RATE >= MAX_UTTERANCE:
                break
    if speech * BLOCK / SAMPLE_RATE < MIN_SPEECH:
        return None
    return _to_wav(np.concatenate(blocks))


_whisper = None
_whisper_lock = threading.Lock()


def _whisper_model():
    global _whisper
    with _whisper_lock:
        if _whisper is None:
            from faster_whisper import WhisperModel

            # Downloads the small English model once (~150 MB), then runs offline. The installed app keeps it in its
            # own data folder (so uninstalling removes it); a copy run from the project uses the shared cache.
            folder = os.environ.get("JARVIS_DATA")
            _whisper = WhisperModel(
                _setting("whisper_model", "base.en"),
                device="cpu",
                compute_type="int8",
                download_root=os.path.join(folder, "models") if folder else None,
            )
        return _whisper


def _transcribe_local(wav_bytes, prompt=None):
    with wave.open(io.BytesIO(wav_bytes)) as wav:
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768
    segments, _ = _whisper_model().transcribe(samples, vad_filter=True, initial_prompt=prompt)
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe(wav_bytes, prompt=None):
    return _transcribe_local(wav_bytes, prompt)


def list_voices():
    return [{"name": settings["reference_id"], "kind": f"Fish Audio voice model, speaking with {settings['model']}"}]


def is_exit(text):
    return re.sub(r"[^a-z ]", "", text.lower()).strip() in EXIT_PHRASES


def _speakable(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"[*_`#>|~]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


MAX_CHUNK = int(_setting("max_chunk", "120"))  # characters per request; keeps each wait short so playback can start early
MAX_PREBUFFER = float(_setting("max_prebuffer", "10"))  # never hold playback back longer than this many seconds


def _chunks(text):
    chunks = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if not sentence:
            continue
        if chunks and len(chunks[-1]) + len(sentence) < MAX_CHUNK:
            chunks[-1] += " " + sentence
        else:
            chunks.append(sentence)
    return chunks


def _trim(audio, rate, keep=0.12):
    """Cuts leading/trailing silence the engine adds, leaving a short natural gap."""
    loud = np.flatnonzero(np.abs(audio).max(axis=1) > 0.01)
    if loud.size == 0:
        return audio
    pad = int(rate * keep)
    return audio[max(loud[0] - pad, 0) : loud[-1] + pad]


def _synthesize(text):
    audio, rate = tts.synthesize(text, settings)
    return _trim(audio, rate), rate


BANDS = 40  # how many frequency bands `speak` reports to `on_level`


def _levels(samples, rate):
    """(bands, loudness) for a short slice of audio: BANDS values from 0 to 1, bass first, for a visualizer."""
    mono = samples.mean(axis=1) if samples.ndim > 1 else samples
    n = len(mono)
    if n < 64:
        return None
    spectrum = np.abs(np.fft.rfft(mono * np.hanning(n))) / (n / 4)  # about 0..1 for a full-scale tone
    freqs = np.fft.rfftfreq(n, 1 / rate)
    edges = np.geomspace(80, min(8000, rate / 2 - 1), BANDS + 1)
    bands = []
    for low, high in zip(edges[:-1], edges[1:]):
        picked = spectrum[(freqs >= low) & (freqs < high)]
        bands.append(round(min(1.0, (float(picked.max()) * 5) ** 0.6) if picked.size else 0.0, 3))
    return bands, round(min(1.0, float(np.sqrt(np.mean(mono**2))) * 4), 3)


def _play(stream, audio, rate, on_level):
    """Writes audio to the speakers; with `on_level`, in 30 ms slices that are each reported just before they play."""
    if on_level is None:
        stream.write(audio)
        return
    step = max(256, int(rate * 0.03))
    for start in range(0, len(audio), step):
        piece = audio[start:start + step]
        levels = _levels(piece, rate)
        if levels:
            # The stream buffers ahead of what is audible, so tell the caller how long to wait before showing it
            on_level(levels[0], levels[1], stream.latency)
        stream.write(piece)


def speak(text, on_state=None, on_level=None):
    """Speaks text, synthesizing the next chunk while the current one plays.

    `on_level(bands, loudness, delay_seconds)` is called a few dozen times a second with the sound about to be heard.
    """
    chunks = _chunks(_speakable(text))
    if not chunks:
        return
    if on_state:
        on_state("speaking")
    ready = queue.Queue()
    stop = threading.Event()

    def produce():
        for chunk in chunks:
            if stop.is_set():
                return
            try:
                began = time.perf_counter()
                audio, rate = _synthesize(chunk)
                ready.put((audio, rate, len(chunk), time.perf_counter() - began))
            except Exception as error:
                ready.put(error)
                return
        ready.put(None)

    threading.Thread(target=produce, daemon=True).start()
    total_chars = sum(len(chunk) for chunk in chunks)
    stream = None
    pending = []  # synthesized audio held back until playback can run without gaps
    done_chars = 0
    gen_time = audio_time = 0.0
    waited_from = time.perf_counter()
    finished = False
    try:
        while not (finished and not pending):
            if not finished:
                item = ready.get()
                if item is None:
                    finished = True
                else:
                    if isinstance(item, Exception):
                        raise item
                    audio, rate, chars, took = item
                    pending.append((audio, rate))
                    done_chars += chars
                    gen_time += took
                    audio_time += len(audio) / rate
            if stream is None and not finished:
                # Start once the audio already made covers the time the rest will take to generate.
                left = total_chars - done_chars
                remaining_gen = gen_time / done_chars * left
                remaining_audio = audio_time / done_chars * left
                if audio_time < remaining_gen - remaining_audio and time.perf_counter() - waited_from < MAX_PREBUFFER:
                    continue
            for audio, rate in pending:
                if stream is None:
                    stream = sd.OutputStream(samplerate=rate, channels=audio.shape[1], dtype="float32", latency="high")
                    stream.start()
                _play(stream, np.ascontiguousarray(audio, dtype=np.float32), rate, on_level)
            pending = []
        if stream is not None:
            # Trailing silence so the device buffer drains before the stream closes, or the last word gets clipped.
            stream.write(np.zeros((int(stream.samplerate * 0.4), stream.channels), dtype=np.float32))
            stream.stop()
    finally:
        stop.set()
        if stream is not None:
            stream.close()
