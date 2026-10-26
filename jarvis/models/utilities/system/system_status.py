import ctypes
import json
import os
import shutil
import subprocess
import time


def _powershell_json(query):
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"{query} | ConvertTo-Json -Compress"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return data if isinstance(data, list) else [data]


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _FileTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]


class _PowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def _to_gb(num_bytes):
    return round(num_bytes / 1024**3, 2)


def _filetime_to_int(filetime):
    return (filetime.dwHighDateTime << 32) | filetime.dwLowDateTime


def _cpu_times():
    idle, kernel, user = _FileTime(), _FileTime(), _FileTime()
    ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    )
    # Kernel time already includes idle time.
    idle_time = _filetime_to_int(idle)
    total_time = _filetime_to_int(kernel) + _filetime_to_int(user)
    return idle_time, total_time


def get_cpu_usage(interval=0.5):
    idle_start, total_start = _cpu_times()
    time.sleep(interval)
    idle_end, total_end = _cpu_times()
    total = total_end - total_start
    if total <= 0:
        return 0.0
    return round(100 * (1 - (idle_end - idle_start) / total), 1)


def get_memory_usage():
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(_MemoryStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return {
        "total_gb": _to_gb(status.ullTotalPhys),
        "used_gb": _to_gb(status.ullTotalPhys - status.ullAvailPhys),
        "available_gb": _to_gb(status.ullAvailPhys),
        "used_percent": status.dwMemoryLoad,
    }


def get_disk_usage():
    disks = []
    for letter in range(ord("A"), ord("Z") + 1):
        path = f"{chr(letter)}:\\"
        if not os.path.exists(path):
            continue
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        disks.append(
            {
                "drive": path,
                "used_gb": _to_gb(usage.used),
                "free_gb": _to_gb(usage.free),
                "used_percent": round(100 * usage.used / usage.total, 1),
            }
        )
    return disks


def get_uptime():
    ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    seconds = ctypes.windll.kernel32.GetTickCount64() // 1000
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    return {"days": days, "hours": hours, "minutes": minutes, "total_seconds": seconds}


def get_battery():
    status = _PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return {}
    # BatteryFlag 128 means no battery; BatteryLifePercent 255 means unknown.
    if status.BatteryFlag == 128 or status.BatteryLifePercent == 255:
        return {}
    # BatteryLifeTime is 0xFFFFFFFF when unknown (e.g. while charging).
    remaining = status.BatteryLifeTime
    return {
        "percent": status.BatteryLifePercent,
        "plugged_in": status.ACLineStatus == 1,
        "minutes_remaining": None if remaining == 0xFFFFFFFF else remaining // 60,
    }


def get_top_processes(count=5):
    processes = _powershell_json(
        f"Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First {count} "
        "Name,Id,WorkingSet64"
    )
    return [
        {
            "name": process.get("Name"),
            "pid": process.get("Id"),
            "memory_mb": round(process.get("WorkingSet64", 0) / 1024**2, 1),
        }
        for process in processes
    ]


def get_system_status():
    return {
        "cpu_usage_percent": get_cpu_usage(),
        "memory": get_memory_usage(),
        "disks": get_disk_usage(),
        "uptime": get_uptime(),
        "battery": get_battery(),
        "top_processes": get_top_processes(),
    }


if __name__ == "__main__":
    print(json.dumps(get_system_status(), indent=2))
