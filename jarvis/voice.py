"""Voice mode: microphone -> faster-whisper -> Jarvis -> built-in OmniVoice text-to-speech -> speakers. Fully local."""
import io
import queue
import re
import threading
import time
import wave
from configparser import ConfigParser

import numpy as np
import sounddevice as sd

from jarvis import tts
from jarvis.paths import CONFIG_PATH

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
# name: (default, type, what it does). Defaults give the original-quality cloned voice with polish on.
OPTIONS = {
    "voice": ("jar", str, "voice name (a bundled one, or a .pt or .mp3 + .txt in your voices folder)"),
    "num_step": ("45", int, "voice refinement passes, 1-128 (more is higher quality but slower)"),
    "guidance_scale": ("2.0", float, "prompt guidance, 0-20"),
    "t_shift": ("0.10", float, "refinement timing"),
    "position_temperature": ("5.0", float, "sampling order variation"),
    "class_temperature": ("0.0", float, "sound variation"),
    "layer_penalty_factor": ("5.0", float, "coarse-to-fine balance"),
    "speed": ("1.0", float, "speaking speed, 0.25-4"),
    "denoise": ("true", _bool, "clean reference noise"),
    "postprocess_output": ("true", _bool, "polish generated audio"),
    "effect_preset": ("broadcast", str, "even out volume: broadcast, podcast, warm, cinematic, raw..."),
        "seed": ("", int, "fixed seed for repeatable delivery (blank = random)"),
    "instruct": ("", str, "style instruction, e.g. calm, warm British butler"),
    "language": ("", str, "language code such as en (blank = auto)"),
    "silence": ("0.8", float, "seconds of quiet that end your turn when listening"),
}
settings = {}
for _name, (_default, _type, _help) in OPTIONS.items():
    _raw = _setting(_name, _default)
    try:
        settings[_name] = _type(_raw) if _raw != "" else None
    except ValueError:
        settings[_name] = _type(_default) if _default != "" else None


def set_option(name, value):
    """Changes a voice setting and saves it to config.conf; returns the stored value."""
    if name not in OPTIONS:
        raise KeyError(name)
    kind = OPTIONS[name][1]
    cleared = value.strip().lower() in {"", "none", "auto", "default"} and name in {"seed", "instruct", "language"}
    settings[name] = None if cleared else kind(value)
    if not _config.has_section(SECTION):
        _config.add_section(SECTION)
    _config.set(SECTION, name, "" if settings[name] is None else str(settings[name]))
    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        _config.write(file)
    return settings[name]


def check_ready():
    """Raises a readable error if the packages voice mode needs are missing."""
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        raise RuntimeError("Listening needs faster-whisper. Run: pip install -r requirements.txt")
    tts.available()


def preload():
    """Loads the speech and listening models and runs one throwaway line, so voice is ready when the chat starts.

    Returns an error message if something failed (None otherwise); does nothing when `preload = false` in config.conf.
    """
    if _setting("preload", "true").lower() not in {"true", "yes", "on", "1"}:
        return None
    try:
        check_ready()
        _whisper_model()
        tts.synthesize("Ready.", settings)
    except Exception as error:
        return f"{type(error).__name__}: {error}"
    if not tts.on_gpu():
        return "no CUDA GPU found, so speech runs on the CPU and will be slow (NVIDIA users: install the CUDA build of torch, see requirements.txt)"
    return None


def _to_wav(samples):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(samples.tobytes())
    return buffer.getvalue()


def listen(on_state=None):
    """Blocks until the user speaks and then pauses; returns WAV bytes (None if it was only a blip)."""
    if on_state:
        on_state("listening")
    recent = []  # rolling pre-roll, so the first word is not clipped
    blocks = []
    noise = []
    threshold = None
    speech = quiet = 0
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=BLOCK) as stream:
        while True:
            data, _ = stream.read(BLOCK)
            frame = data[:, 0].copy()
            level = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
            if threshold is None:
                # The first ~0.3 s measures the room's background level.
                noise.append(level)
                recent.append(frame)
                if len(noise) >= CALIBRATION_BLOCKS:
                    threshold = max(np.mean(noise) * 3, 400.0)
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

            # Downloads the small English model once (~150 MB), then runs offline.
            _whisper = WhisperModel(_setting("whisper_model", "base.en"), device="cpu", compute_type="int8")
        return _whisper


def _transcribe_local(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as wav:
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768
    segments, _ = _whisper_model().transcribe(samples, language=settings["language"] or None, vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe(wav_bytes):
    return _transcribe_local(wav_bytes)


def list_voices():
    return [{"name": name, "kind": "clone"} for name in tts.voices()]


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


def speak(text, on_state=None):
    """Speaks text, synthesizing the next chunk while the current one plays."""
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
                stream.write(np.ascontiguousarray(audio, dtype=np.float32))
            pending = []
        if stream is not None:
            # Trailing silence so the device buffer drains before the stream closes, or the last word gets clipped.
            stream.write(np.zeros((int(stream.samplerate * 0.4), stream.channels), dtype=np.float32))
            stream.stop()
    finally:
        stop.set()
        if stream is not None:
            stream.close()
