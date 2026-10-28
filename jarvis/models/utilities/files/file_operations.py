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


def confirm(message, spoken=None):
    """Asks the user to approve an action. False if they decline or there is no way to ask."""
    return CONFIRM is not None and bool(CONFIRM(message, spoken))


def spoken_size(num_bytes):
    """A size the way it's said aloud: '3.9 kilobytes', not '3.9 KB'."""
    for unit in ("bytes", "kilobytes", "megabytes", "gigabytes"):
        if num_bytes < 1024 or unit == "gigabytes":
            return f"{num_bytes:.0f} {unit}" if unit == "bytes" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024


def check_writable(target):
    """Refuses paths inside Windows or Program Files, where writing would only break the system."""
    for variable in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(variable)
        if value:
            root = Path(value).resolve()
            if target == root or root in target.parents:
                raise _OperationError(f"Files inside '{root}' aren't written to.")

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


def _protected_paths():
    """Paths that are never deleted, moved, or renamed: whole drives, Windows, Program Files, the home folder."""
    paths = {Path.home().resolve()}
    for variable in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(variable)
        if value:
            paths.add(Path(value).resolve())
    return paths


def _resolve(path):
    """Turn user input into an absolute path."""
    path = os.path.expandvars(os.path.expanduser(str(path).strip().strip('"')))
    candidate = Path(path)
    if not candidate.is_absolute():
        # "Downloads/report.pdf" means the Downloads folder, wherever it really lives.
        folders = get_major_folders()
        first, _, rest = path.replace("\\", "/").partition("/")
        match = next((folder for name, folder in folders.items() if name.lower() == first.lower()), None)
        if match is None:
            raise _OperationError(f"Use a full path, or start with one of: {', '.join(folders)}.")
        candidate = match / rest
    return candidate.resolve()


def _check_not_protected(path):
    if path == Path(path.anchor) or path in _protected_paths():
        raise _OperationError(f"'{path}' is a drive or core system folder and isn't touched.")


def _size(path):
    if path.is_file():
        return path.stat().st_size
    total = 0
    for current, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(current) / name).stat().st_size
            except OSError:
                pass
    return total


def _format_size(num_bytes):
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024


def _run(operation, *args):
    try:
        return operation(*args)
    except _OperationError as error:
        return {"error": str(error)}
    except OSError as error:
        return {"error": f"{type(error).__name__}: {error}"}


def _recycle(targets):
    """Send paths to the Recycle Bin. Callers are responsible for getting the user's approval first."""
    request = _FileOperation()
    request.wFunc = FO_DELETE
    # The path list is null-separated and ends with two nulls; Python adds the last one itself.
    request.pFrom = "\0".join(str(target) for target in targets) + "\0"
    request.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(request))
    if result != 0 or request.fAnyOperationsAborted:
        raise _OperationError(f"Windows couldn't delete everything (code {result}). Some items may remain.")


def delete_file(paths, contents_only=False):
    """Send files or folders to the Recycle Bin after the user approves. One approval covers the whole batch."""

    def operation(paths, contents_only):
        if isinstance(paths, str):
            paths = [paths]
        targets = []
        for path in paths:
            target = _resolve(path)
            if not target.exists():
                raise _OperationError(f"Nothing at '{target}'.")
            if contents_only:
                if not target.is_dir():
                    raise _OperationError(f"'{target}' isn't a folder.")
                targets.extend(sorted(target.iterdir()))
            else:
                _check_not_protected(target)
                targets.append(target)
        if not targets:
            return {"deleted": False, "reason": "There was nothing to delete."}

        total = sum(_size(target) for target in targets)
        names = ", ".join(target.name for target in targets[:4]) + (", ..." if len(targets) > 4 else "")
        where = f" from '{_resolve(paths[0])}'" if contents_only else ""
        message = (
            f"Move {len(targets)} item{'s' if len(targets) != 1 else ''}{where} "
            f"({_format_size(total)}: {names}) to the Recycle Bin?"
        )
        if len(targets) == 1:
            what = targets[0].name
        elif len(targets) <= 3:
            what = ", ".join(target.name for target in targets[:-1]) + f" and {targets[-1].name}"
        else:
            what = f"{len(targets)} items, {spoken_size(total)}, starting with {targets[0].name}"
        if not confirm(message, f"Shall I send {what} to the Recycle Bin?"):
            return {"deleted": False, "reason": "The user declined, or confirmation wasn't available."}

        _recycle(targets)
        return {
            "deleted": True,
            "count": len(targets),
            "size": _format_size(total),
            "note": "Sent to the Recycle Bin, so it can be restored.",
        }

    return _run(operation, paths, contents_only)


def _destination(source, destination):
    """Where source ends up: inside destination if that's an existing folder, otherwise at destination."""
    target = _resolve(destination)
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
        origin = _resolve(source)
        _check_not_protected(origin)
        if not origin.exists():
            raise _OperationError(f"Nothing at '{origin}'.")
        target = _destination(origin, destination)
        shutil.move(str(origin), str(target))
        return {"moved": True, "from": str(origin), "to": str(target)}

    return _run(operation, source, destination)


def copy_file(source, destination):
    def operation(source, destination):
        origin = _resolve(source)
        if not origin.exists():
            raise _OperationError(f"Nothing at '{origin}'.")
        target = _destination(origin, destination)
        if origin.is_dir():
            shutil.copytree(origin, target)
        else:
            shutil.copy2(origin, target)
        return {"copied": True, "from": str(origin), "to": str(target)}

    return _run(operation, source, destination)


def rename_file(path, new_name):
    def operation(path, new_name):
        origin = _resolve(path)
        _check_not_protected(origin)
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
        target = _resolve(path)
        if target.exists():
            raise _OperationError(f"'{target}' already exists.")
        target.mkdir(parents=True)
        return {"created": True, "path": str(target)}

    return _run(operation, path)


if __name__ == "__main__":
    print(json.dumps(create_folder("Downloads/jarvis_demo_folder"), indent=2))
