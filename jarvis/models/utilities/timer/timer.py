import json
import threading
import time
import winsound

# Timers live in memory only, so they don't survive a restart.
_timers = {}
_lock = threading.Lock()
_next_id = 1


def _format_duration(seconds):
    hours, remainder = divmod(int(round(seconds)), 3600)
    minutes, secs = divmod(remainder, 60)
    parts = [f"{hours}h" if hours else "", f"{minutes}m" if minutes else "", f"{secs}s" if secs or not (hours or minutes) else ""]
    return " ".join(part for part in parts if part)


def _fire(timer_id):
    with _lock:
        timer = _timers.pop(timer_id, None)
    if not timer:
        return
    print(f"\n[Timer finished: {timer['label']} ({_format_duration(timer['seconds'])})]\n> ", end="", flush=True)
    winsound.MessageBeep()


def set_timer(seconds, label="Timer"):
    global _next_id
    seconds = float(seconds)
    if seconds <= 0:
        return {"error": "Duration must be greater than zero."}
    with _lock:
        timer_id = _next_id
        _next_id += 1
        thread = threading.Timer(seconds, _fire, args=(timer_id,))
        thread.daemon = True
        _timers[timer_id] = {
            "label": label or "Timer",
            "seconds": seconds,
            "ends_at": time.time() + seconds,
            "thread": thread,
        }
    thread.start()
    return {"id": timer_id, "label": label or "Timer", "duration": _format_duration(seconds)}


def list_timers():
    with _lock:
        timers = [
            {
                "id": timer_id,
                "label": timer["label"],
                "remaining": _format_duration(max(0, timer["ends_at"] - time.time())),
                "remaining_seconds": round(max(0, timer["ends_at"] - time.time())),
            }
            for timer_id, timer in sorted(_timers.items())
        ]
    return {"timers": timers}


def cancel_timer(timer_id=None, label=None):
    with _lock:
        if timer_id is None and label:
            timer_id = next((i for i, t in _timers.items() if t["label"].lower() == label.strip().lower()), None)
        timer = _timers.pop(timer_id, None) if timer_id is not None else None
    if not timer:
        return {"error": "No matching timer."}
    timer["thread"].cancel()
    return {"cancelled": timer["label"], "id": timer_id}


if __name__ == "__main__":
    print(json.dumps(set_timer(2, "test"), indent=2))
    print(json.dumps(list_timers(), indent=2))
    time.sleep(3)
