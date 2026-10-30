"""The back end of the Jarvis desktop app (app/): the same model and tools as the terminal, over JSON lines.

The window starts this with `python -m jarvis.server`. Each line on stdin is a command from the window and each line
on stdout is an event for it. Anything the tools print goes to stderr, so it can't be mistaken for an event.
"""
import difflib
import io
import itertools
import json
import re
import sys
import threading
import time
from datetime import datetime

# Keep the real stdout for events; tools and timers print, and that must not end up in the protocol.
_events = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
sys.stdout = sys.stderr
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")

_write_lock = threading.Lock()


def emit(event):
    with _write_lock:
        _events.write(json.dumps(event, ensure_ascii=False) + "\n")


try:
    from jarvis import config_file

    config_file.create_if_missing()  # first run: the settings page is where the keys get entered
    from jarvis.models.default import default_model as model
    from jarvis.pricing import estimate_cost, format_cost, format_tokens

    # The utility folders are added to the path by the model module imported above.
    import file_operations
except (Exception, SystemExit) as error:
    emit({"type": "fatal", "message": f"{type(error).__name__}: {error}" if isinstance(error, Exception) else str(error)})
    sys.exit(1)

# How you and Jarvis talk: what you do (type or speak) and what it does (type or speak)
MODES = {
    "type_text": "You type, Jarvis types back.",
    "voice_text": "You speak, Jarvis types back.",
    "type_voice": "You type, Jarvis speaks back.",
    "voice_voice": "You speak, Jarvis speaks back.",
}
THEMES = {"light", "dark"}
UI = {"mode": "type_text", "theme": "light"}

_turn_lock = threading.Lock()  # one question at a time
_answers = {}  # confirmation id -> (event, [approved])
_answers_lock = threading.Lock()
_ids = itertools.count(1)
_cancel_listen = None  # set while the listening loop is running; setting the event stops that loop
_listen_lock = threading.Lock()


def _input_voice():
    return UI["mode"].startswith("voice")


def _output_voice():
    return UI["mode"].endswith("_voice")


def _load_ui():
    parser = config_file.read()
    mode = parser.get("app", "mode", fallback="").strip()
    theme = parser.get("app", "theme", fallback="").strip()
    UI["mode"] = mode if mode in MODES else "type_text"
    UI["theme"] = theme if theme in THEMES else "light"


def _wake_word():
    word = config_file.read().get("voice", "wake_word", fallback="jarvis").strip().strip('"').lower() or "jarvis"
    return "" if word in {"none", "off"} else word


def _needs_setup():
    key = model.anthropic_api_key
    return not key or key == "YOUR_KEY"


def _greeting():
    hour = datetime.now().hour
    period = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
    name = model.user_name
    first_name = name.split()[0] if name and name != "YOUR_NAME" else ""
    return f"Good {period}, {first_name}." if first_name else f"Good {period}."


def _profile():
    """What the window shows about the current setup."""
    return {
        "model": model.model_version,
        "tools": len(model.UTILITY_TOOLS),
        "greeting": _greeting(),
        "needs_setup": _needs_setup(),
        "wake_word": _wake_word(),
        "mode": UI["mode"],
        "theme": UI["theme"],
    }


def _confirm(message, spoken=None):
    """Asks the window and waits for the answer. Closing the window or a timeout counts as no."""
    ask_id = next(_ids)
    waiter = (threading.Event(), [False])
    with _answers_lock:
        _answers[ask_id] = waiter
    emit({"type": "confirm", "id": ask_id, "message": message})
    waiter[0].wait(timeout=600)
    with _answers_lock:
        _answers.pop(ask_id, None)
    return waiter[1][0]


file_operations.CONFIRM = _confirm


class _Usage:
    """Adds up what one reply cost, for the line under it."""

    def __init__(self):
        self.tokens_in = self.tokens_out = self.cached = self.searches = 0
        self.cost = [0.0, 0.0]  # None once a model without known prices was used

    def add(self, event):
        usage = event["usage"]
        self.tokens_in += sum(usage.get(key) or 0 for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        self.cached += usage.get("cache_read_input_tokens") or 0
        self.tokens_out += usage.get("output_tokens") or 0
        self.searches += (usage.get("server_tool_use") or {}).get("web_search_requests") or 0
        call_cost = estimate_cost(event["model"], usage)
        if call_cost is None or self.cost is None:
            self.cost = None
        else:
            self.cost = [self.cost[0] + call_cost[0], self.cost[1] + call_cost[1]]

    def summary(self):
        if self.cost is None:
            parts = [f"{format_tokens(self.tokens_in)} in / {format_tokens(self.tokens_out)} out"]
        else:
            parts = [
                f"{format_tokens(self.tokens_in)} in {format_cost(self.cost[0])}",
                f"{format_tokens(self.tokens_out)} out {format_cost(self.cost[1])}",
                f"{format_cost(sum(self.cost))} total",
            ]
        if self.cached:
            parts.append(f"{format_tokens(self.cached)} cached")
        if self.searches:
            parts.append(f"+{self.searches} web search{'es' if self.searches != 1 else ''}")
        return " · ".join(parts)


def _voice_state(name):
    emit({"type": "voice_state", "state": name})


def _voice_level(bands, loudness, delay):
    emit({"type": "levels", "bands": bands, "loudness": loudness, "delay": delay})


def _empty_reply_note(stop):
    reason = stop["stop_reason"] if stop else "unknown"
    details = (stop or {}).get("details") or {}
    explanation = details.get("explanation") or details.get("category") or ""
    if reason == "max_tokens":
        hint = "The reply was cut off before it finished."
    elif reason == "refusal":
        hint = "Claude declined this request."
    else:
        hint = "Claude finished without saying anything."
    return f"*(no response)*\n\n{hint} Stop reason: `{reason}`" + (f" ({explanation})" if explanation else "") + ". Try asking again."


def _run_turn(message):
    """Asks Jarvis (the turn lock is already held) and, in the modes where it talks back, reads the reply aloud."""
    started = time.perf_counter()
    usage = _Usage()
    stop = None
    calls = 0
    speaking = _output_voice()

    def on_event(event):
        nonlocal stop, calls
        if event["type"] == "usage":
            usage.add(event)
            return
        if event["type"] == "stop":
            stop = event
            return
        if event["type"] == "tool_call":
            calls += 1
        emit({**event, "output": str(event["output"])} if "output" in event else event)

    try:
        reply = model.send_message(message, "default", on_event=on_event, voice=speaking)
        if not reply.strip():
            reply = _empty_reply_note(stop)
        emit({"type": "reply", "text": reply, "seconds": time.perf_counter() - started, "calls": calls, "cost": usage.summary() if model.show_cost else ""})
        if speaking and reply.strip():
            from jarvis import voice

            try:
                voice.speak(reply, _voice_state, _voice_level)
            finally:
                _voice_state("idle")
    except Exception as error:
        emit({"type": "error", "message": f"{type(error).__name__}: {error}"})
    finally:
        _turn_lock.release()
        emit({"type": "idle"})


def _start_turn(message):
    if not _turn_lock.acquire(blocking=False):
        emit({"type": "error", "message": "Jarvis is still working on the last message."})
        return
    emit({"type": "busy"})
    threading.Thread(target=_run_turn, args=(message,), daemon=True).start()


def _after_wake(text, wake_word):
    """What was said after the wake word ("" if only the wake word was said), or None if it wasn't said.

    The wake word has to be one of the first three words ("Jarvis, ...", "Hey Jarvis, ..."), so talking about Jarvis
    doesn't wake it. Speech recognition often mishears a name a little, so close spellings count too.
    """
    for number, match in enumerate(re.finditer(r"[A-Za-z']+", text)):
        if number >= 3:
            break
        word = match.group().lower()
        if word == wake_word or difflib.SequenceMatcher(None, word, wake_word).ratio() >= 0.75:
            return text[match.end():].strip(" ,.:;!?-")
    return None


def _ensure_listening():
    """Starts the listening loop if it isn't running. It runs for as long as the mode is one where you speak."""
    global _cancel_listen
    with _listen_lock:
        if _cancel_listen is not None:
            return
        cancel = _cancel_listen = threading.Event()
    # The loop is handed its own event: by the time the thread runs, _cancel_listen may already have been cleared
    # again (a mode change or new settings arriving at that moment)
    threading.Thread(target=_listen_loop, args=(cancel,), daemon=True).start()


def _stop_listening():
    global _cancel_listen
    with _listen_lock:
        event, _cancel_listen = _cancel_listen, None
    if event is not None:
        event.set()
        emit({"type": "listening", "on": False})


def _listen_loop(cancel):
    """Listens for you for as long as the mode is one where you speak (it starts by itself, with no button).

    Jarvis only reacts after hearing the wake word. With wake_mode "every_time" (the default) that is true for every
    request: it answers one request and goes straight back to sleep. With "stay_awake" it keeps the conversation going
    without the wake word until `idle_timeout` seconds pass without you saying anything (counted from the end of its
    last answer), and then goes back to sleep.
    """
    global _cancel_listen
    from jarvis import voice

    wake_word = str(voice.settings["wake_word"] or "jarvis").strip().lower()
    gated = wake_word not in {"none", "off"}
    timeout = float(voice.settings["idle_timeout"] or 45)
    stay_awake = str(voice.settings["wake_mode"]).strip().lower() == "stay_awake"
    awake = not gated
    last_activity = time.monotonic()

    def asleep():
        return gated and not awake

    def show(state):
        # While asleep the window says Jarvis is standing by for its name, even when the microphone picks up sound.
        # Only once it has been woken does it show that it is listening to you.
        _voice_state("waiting" if state in {"listening", "hearing"} and asleep() else state)

    emit({"type": "listening", "on": True})
    try:
        # Loading the listening model takes a few seconds the first time. Doing it at start-up instead would hold up
        # the first question, so it waits for the first use of the microphone.
        _voice_state("loading")
        voice._whisper_model()
        while not cancel.is_set() and _input_voice():
            wait = None
            if gated and awake:
                wait = timeout - (time.monotonic() - last_activity)
                if wait <= 0:
                    awake = False
                    emit({"type": "note", "text": f"Asleep. Say \u201c{wake_word.title()}\u201d to wake me."})
                    wait = None
            audio = voice.listen(show, cancel, wait)
            _voice_state("waiting" if asleep() else "idle")
            if audio is None or cancel.is_set():
                continue
            if not asleep():
                _voice_state("loading")
            heard = voice.transcribe(audio, prompt=wake_word.title() if gated else None)
            _voice_state("waiting" if asleep() else "idle")
            if not heard:
                continue
            if not awake:
                request = _after_wake(heard, wake_word)
                if request is None:
                    continue  # not addressed to Jarvis
                awake = True
                last_activity = time.monotonic()
                heard = request
                if not heard:
                    continue  # just its name: it is awake and waiting for the request
            last_activity = time.monotonic()
            if voice.is_exit(heard):
                # "Stop listening": back to sleep, still ready for its name. With no wake word there is no sleep.
                if gated:
                    awake = False
                    emit({"type": "note", "text": f"Asleep. Say \u201c{wake_word.title()}\u201d to wake me."})
                continue
            emit({"type": "heard", "text": heard})
            _turn_lock.acquire()
            emit({"type": "busy"})
            _run_turn(heard)  # releases the lock
            last_activity = time.monotonic()
            if gated and not stay_awake:
                awake = False  # every request needs the wake word
    except Exception as error:
        emit({"type": "error", "message": f"{type(error).__name__}: {error}"})
    finally:
        _voice_state("idle")
        # Only say it stopped if nothing else already did (the mode changing, or a restart after new settings)
        with _listen_lock:
            current = _cancel_listen is cancel
            if current:
                _cancel_listen = None
        if current:
            emit({"type": "listening", "on": False})


# ---- settings -----------------------------------------------------------------------------------------------------
MODEL_CHOICES = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"]
VOICE_CHOICES = {
    "wake_mode": ["every_time", "stay_awake"],
    "latency": ["normal", "balanced", "low"],
    "model": ["s1", "s2-pro", "s2.1-pro", "s2.1-pro-free", "drama-3"],
}
PLACEHOLDERS = {"YOUR_KEY", "YOUR_NAME", "YOUR_ZIP"}


def _settings_schema():
    """Every setting the settings page shows, with its current value. Secrets are never sent back out in full."""
    from jarvis import voice

    parser = config_file.read()

    def current(section, key, default=""):
        value = parser.get(section, key, fallback=default).strip().strip('"')
        return "" if value in PLACEHOLDERS else value

    def secret(section, key, label, help_text, required=False):
        value = current(section, key)
        hint = f"saved · ends in {value[-4:]}" if len(value) > 8 else ("saved" if value else "")
        return {"id": f"{section}.{key}", "label": label, "type": "secret", "set": bool(value), "hint": hint, "help": help_text, "required": required}

    def field(section, key, label, kind, help_text, default="", options=None):
        return {"id": f"{section}.{key}", "label": label, "type": kind, "value": current(section, key, default), "help": help_text, "options": options}

    voice_fields = []
    for name, (default, kind, help_text) in voice.OPTIONS.items():
        shown = voice.settings.get(name)
        if kind is voice._bool:
            voice_fields.append({"id": f"voice.{name}", "label": name.replace("_", " "), "type": "bool", "value": "true" if shown else "false", "help": help_text})
        else:
            voice_fields.append(
                {
                    "id": f"voice.{name}",
                    "label": name.replace("_", " "),
                    "type": "select" if name in VOICE_CHOICES else "number" if kind is float else "text",
                    "value": "" if shown is None else str(shown),
                    "help": help_text,
                    "options": VOICE_CHOICES.get(name),
                }
            )

    return [
        {
            "title": "Keys",
            "note": "Stored in config.conf on this PC. They are only ever sent to the service they belong to.",
            "fields": [
                secret("anthropic", "anthropic_api_key", "Anthropic API key", "Needed for Jarvis to think. Get one at console.anthropic.com.", required=True),
                secret("fish", "api_key", "Fish Audio API key", "Needed for Jarvis to speak aloud. Get one at fish.audio."),
                secret("github", "token", "GitHub token", "Optional. A classic token with the user scope lets Jarvis set your GitHub status."),
            ],
        },
        {
            "title": "Assistant",
            "fields": [
                field("anthropic", "model", "Model", "text", "Which Claude model answers. Haiku is cheapest and fastest; larger ones reason better.", "claude-sonnet-5-5", MODEL_CHOICES),
                field("personal", "name", "Your name", "text", "How Jarvis knows you."),
                field("personal", "zip_code", "Zip code", "text", "Your US zip code, the default place for weather, local news and earthquakes."),
                field("settings", "history_turns", "Messages remembered", "number", "How many of your recent messages (with the replies) are sent along with a new one. Lower is cheaper.", "12"),
                field("settings", "show_cost", "Show cost", "bool", "Show what each reply cost under it.", "false"),
            ],
        },
        {"title": "Voice", "note": "Listening happens on this PC. Speaking goes through Fish Audio.", "fields": voice_fields},
    ]


def _save_settings(values):
    """Writes the changed settings to config.conf and applies them straight away."""
    from jarvis import voice

    allowed = {}
    for section in _settings_schema():
        for item in section["fields"]:
            allowed[item["id"]] = item
    changes = {}
    for setting_id, raw in values.items():
        item = allowed.get(setting_id)
        if item is None:
            continue
        section, key = setting_id.split(".", 1)
        text = str(raw).strip()
        if item["type"] == "bool":
            text = "true" if text.lower() in {"true", "yes", "on", "1"} else "false"
        elif item["type"] == "number" and text:
            try:
                float(text)
            except ValueError:
                raise ValueError(f"'{text}' isn't a number for {item['label']}.")
        if section == "voice":
            try:
                voice.OPTIONS[key][1](text)
            except ValueError:
                raise ValueError(f"'{text}' isn't a valid value for {item['label']}.")
        changes.setdefault(section, {})[key] = text
    if changes:
        config_file.update(changes)
        model.apply_config()
        voice.reload()
        if "voice" in changes and _cancel_listen is not None:
            _stop_listening()  # the loop reads the wake word, timeout and sensitivity when it starts
            if _input_voice():
                _ensure_listening()
    emit({"type": "settings", "sections": _settings_schema()})
    emit({"type": "profile", **_profile()})


def _mode_problem(mode):
    """Why a mode can't be used yet (None if it can)."""
    if mode.startswith("voice"):
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return "Listening needs faster-whisper. Run: pip install -r requirements.txt"
    if mode.endswith("_voice"):
        from jarvis.voice import tts

        if not tts.api_key():
            return "Speaking needs a Fish Audio key. Add it under Settings > Keys."
    return None


def _set_ui(command):
    mode = command.get("mode")
    theme = command.get("theme")
    changes = {}
    if mode is not None:
        if mode not in MODES:
            raise ValueError(f"Unknown mode '{mode}'.")
        problem = _mode_problem(mode)
        if problem:
            emit({"type": "error", "message": problem})
            emit({"type": "ui", "mode": UI["mode"], "theme": UI["theme"]})
            return
        UI["mode"] = mode
        changes["mode"] = mode
        if _input_voice():
            _ensure_listening()
        else:
            _stop_listening()
    if theme is not None:
        if theme not in THEMES:
            raise ValueError(f"Unknown theme '{theme}'.")
        UI["theme"] = theme
        changes["theme"] = theme
    if changes:
        config_file.update({"app": changes})
    emit({"type": "ui", "mode": UI["mode"], "theme": UI["theme"]})


def _handle(command):
    kind = command.get("type")
    if kind == "message":
        _start_turn(str(command.get("text", "")).strip())
    elif kind == "confirm":
        with _answers_lock:
            waiter = _answers.get(command.get("id"))
        if waiter:
            waiter[1][0] = bool(command.get("approved"))
            waiter[0].set()
    elif kind == "get_settings":
        emit({"type": "settings", "sections": _settings_schema()})
    elif kind == "save_settings":
        try:
            _save_settings(command.get("values") or {})
        except ValueError as error:
            emit({"type": "error", "message": str(error)})
            emit({"type": "settings", "sections": _settings_schema()})
    elif kind == "set_ui":
        _set_ui(command)
    elif kind == "voice_test":
        def test():
            from jarvis import voice
            from jarvis.voice import tts

            try:
                tts.available()
                voice.speak(command.get("text") or "Good evening, sir. How does this sound?", _voice_state, _voice_level)
            except Exception as error:
                emit({"type": "error", "message": f"{type(error).__name__}: {error}"})
            finally:
                _voice_state("idle")

        threading.Thread(target=test, daemon=True).start()


def main():
    _load_ui()
    emit({"type": "ready", **_profile()})
    if _input_voice():
        _ensure_listening()  # the saved mode is one where you speak, so start listening for the wake word
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            _handle(json.loads(line))
        except Exception as error:
            emit({"type": "error", "message": f"{type(error).__name__}: {error}"})
    # The window closed: decline anything still waiting for an answer.
    with _answers_lock:
        for event, _ in _answers.values():
            event.set()


if __name__ == "__main__":
    main()
