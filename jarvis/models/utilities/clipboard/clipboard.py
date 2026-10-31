import ctypes
import json
import time
from ctypes import wintypes

MAX_CHARS = 5000
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
kernel32.GlobalUnlock.restype = wintypes.BOOL


def _open_clipboard():
    # Another program can have the clipboard open for a moment, so try a few times
    for _ in range(20):
        if user32.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise OSError("The clipboard is in use by another program.")


def read_clipboard():
    _open_clipboard()
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            # Empty, or holds something that isn't text (e.g. an image).
            return {"text": "", "empty": True}
        pointer = kernel32.GlobalLock(handle)
        try:
            text = ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    text = text.replace("\r\n", "\n")
    return {"text": text[:MAX_CHARS], "truncated": len(text) > MAX_CHARS, "empty": not text}


def write_clipboard(text):
    data = (text.replace("\r\n", "\n").replace("\n", "\r\n") + "\0").encode("utf-16-le")
    _open_clipboard()
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise MemoryError("Couldn't set aside memory for the clipboard.")
        pointer = kernel32.GlobalLock(handle)
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        # Windows owns the memory once it has been handed over
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise OSError("Windows refused the clipboard text.")
    finally:
        user32.CloseClipboard()
    return {"copied_characters": len(text)}


if __name__ == "__main__":
    print(json.dumps(read_clipboard(), indent=2))
