import json
import tkinter

MAX_CHARS = 5000


def read_clipboard():
    root = tkinter.Tk()
    root.withdraw()
    try:
        text = root.clipboard_get()
    except tkinter.TclError:
        # Empty, or holds something that isn't text (e.g. an image).
        return {"text": "", "empty": True}
    finally:
        root.destroy()
    return {"text": text[:MAX_CHARS], "truncated": len(text) > MAX_CHARS, "empty": not text}


def write_clipboard(text):
    root = tkinter.Tk()
    root.withdraw()
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        # The clipboard is only handed to Windows once the event loop has run.
        root.update()
    finally:
        root.destroy()
    return {"copied_characters": len(text)}


if __name__ == "__main__":
    print(json.dumps(read_clipboard(), indent=2))
