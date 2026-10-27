import ctypes
import json
import os
import shutil
from ctypes import wintypes
from pathlib import Path

from file_search import get_major_folders

# Set by the front end to ask the user before anything is deleted: confirm(message) -> bool.
# Left as None, deletes are refused, so nothing destructive can happen without a person saying yes.
CONFIRM = None

FO_DELETE = 0x0003
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400


class _FileOperation(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


class _OperationError(Exception):
    pass


def _resolve(path):
    """Turn user input into an absolute path that is inside one of the main folders."""
    folders = {name: folder.resolve() for name, folder in get_major_folders().items()}
    path = os.path.expandvars(os.path.expanduser(path.strip().strip('"')))
    candidate = Path(path)
    if not candidate.is_absolute():
        # "Downloads/report.pdf" means the Downloads folder, wherever it really lives.
        first, _, rest = path.replace("\\", "/").partition("/")
        match = next((folder for name, folder in folders.items() if name.lower() == first.lower()), None)
        if match is None:
            raise _OperationError(f"Use a full path or start with one of: {', '.join(folders)}.")
        candidate = match / rest
    candidate = candidate.resolve()
    if not any(candidate == root or root in candidate.parents for root in folders.values()):
        raise _OperationError(f"Only files inside {', '.join(folders)} can be changed.")
    return candidate, folders


def _check_not_root(path, folders):
    if path in folders.values():
        raise _OperationError("That's one of the main folders itself, which can't be changed.")


def _describe(path):
    if path.is_dir():
        count = sum(len(files) for _, _, files in os.walk(path))
        return f"the folder '{path}' and its {count} file{'s' if count != 1 else ''}"
    return f"the file '{path}' ({path.stat().st_size / 1024**2:.2f} MB)"


def _run(operation, *args):
    try:
        return operation(*args)
    except _OperationError as error:
        return {"error": str(error)}
    except OSError as error:
        return {"error": f"{type(error).__name__}: {error}"}


def delete_file(path):
    def operation(path):
        target, folders = _resolve(path)
        _check_not_root(target, folders)
        if not target.exists():
            raise _OperationError(f"Nothing at '{target}'.")
        description = _describe(target)
        if CONFIRM is None or not CONFIRM(f"Move {description} to the Recycle Bin?"):
            return {"deleted": False, "reason": "The user declined, or confirmation wasn't available."}

        request = _FileOperation()
        request.wFunc = FO_DELETE
        # The path list must end with two nulls; Python adds one terminator itself.
        request.pFrom = str(target) + "\0"
        request.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(request))
        if result != 0 or request.fAnyOperationsAborted:
            raise _OperationError(f"Windows couldn't delete it (code {result}).")
        return {"deleted": True, "path": str(target), "note": "Sent to the Recycle Bin, so it can be restored."}

    return _run(operation, path)


def _destination(source, destination, folders):
    """Where source ends up: inside destination if that's an existing folder, otherwise at destination."""
    target, _ = _resolve(destination)
    if target.is_dir():
        target = target / source.name
    if target.exists():
        raise _OperationError(f"'{target}' already exists. Nothing was overwritten.")
    if not target.parent.is_dir():
        raise _OperationError(f"The folder '{target.parent}' doesn't exist.")
    if source.is_dir() and (target == source or source in target.parents):
        raise _OperationError("A folder can't go inside itself.")
    return target


def move_file(source, destination):
    def operation(source, destination):
        origin, folders = _resolve(source)
        _check_not_root(origin, folders)
        if not origin.exists():
            raise _OperationError(f"Nothing at '{origin}'.")
        target = _destination(origin, destination, folders)
        shutil.move(str(origin), str(target))
        return {"moved": True, "from": str(origin), "to": str(target)}

    return _run(operation, source, destination)


def copy_file(source, destination):
    def operation(source, destination):
        origin, folders = _resolve(source)
        if not origin.exists():
            raise _OperationError(f"Nothing at '{origin}'.")
        target = _destination(origin, destination, folders)
        if origin.is_dir():
            shutil.copytree(origin, target)
        else:
            shutil.copy2(origin, target)
        return {"copied": True, "from": str(origin), "to": str(target)}

    return _run(operation, source, destination)


def rename_file(path, new_name):
    def operation(path, new_name):
        origin, folders = _resolve(path)
        _check_not_root(origin, folders)
        if not origin.exists():
            raise _OperationError(f"Nothing at '{origin}'.")
        if not new_name.strip() or Path(new_name).name != new_name.strip():
            raise _OperationError("Give just a new name, not a path. Use move_file to change folders.")
        target = origin.with_name(new_name.strip())
        if target.exists():
            raise _OperationError(f"'{target}' already exists. Nothing was overwritten.")
        origin.rename(target)
        return {"renamed": True, "from": str(origin), "to": str(target)}

    return _run(operation, path, new_name)


def create_folder(path):
    def operation(path):
        target, _ = _resolve(path)
        if target.exists():
            raise _OperationError(f"'{target}' already exists.")
        target.mkdir(parents=True)
        return {"created": True, "path": str(target)}

    return _run(operation, path)


if __name__ == "__main__":
    print(json.dumps(create_folder("Downloads/jarvis_demo_folder"), indent=2))
