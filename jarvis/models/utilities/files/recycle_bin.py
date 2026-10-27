import ctypes
import json
from ctypes import wintypes

import file_operations

SHERB_NOCONFIRMATION = 0x00000001
SHERB_NOPROGRESSUI = 0x00000002
SHERB_NOSOUND = 0x00000004


class _BinInfo(ctypes.Structure):
    # Default alignment: the 64-bit fields sit on 8-byte boundaries, so this is 24 bytes.
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


def _format_size(num_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024


def _query():
    info = _BinInfo()
    info.cbSize = ctypes.sizeof(_BinInfo)
    # A null root path asks about the Recycle Bins on all drives combined.
    result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
    if result != 0:
        return None
    return info.i64NumItems, info.i64Size


def get_recycle_bin():
    info = _query()
    if info is None:
        return {"error": "Couldn't read the Recycle Bin."}
    items, size = info
    return {"items": items, "size": _format_size(size), "empty": items == 0}


def empty_recycle_bin():
    """Permanently erase everything in the Recycle Bin, after the user approves."""
    info = _query()
    if info is None:
        return {"error": "Couldn't read the Recycle Bin."}
    items, size = info
    if items == 0:
        return {"emptied": False, "reason": "The Recycle Bin is already empty."}

    message = (
        f"PERMANENTLY erase {items} item{'s' if items != 1 else ''} ({_format_size(size)}) "
        "from the Recycle Bin? This can't be undone."
    )
    confirm = file_operations.CONFIRM
    if confirm is None or not confirm(message):
        return {"emptied": False, "reason": "The user declined, or confirmation wasn't available."}

    result = ctypes.windll.shell32.SHEmptyRecycleBinW(
        None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
    )
    if result != 0:
        return {"error": f"Windows couldn't empty the Recycle Bin (code {result & 0xFFFFFFFF:#x})."}
    return {"emptied": True, "items_erased": items, "size_freed": _format_size(size), "note": "This is permanent."}


if __name__ == "__main__":
    print(json.dumps(get_recycle_bin(), indent=2))
