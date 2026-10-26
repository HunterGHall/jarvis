import ctypes
import json
import os
import platform
import shutil
import subprocess


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


def _to_gb(num_bytes):
    return round(num_bytes / 1024**3, 2)


def get_os():
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.machine(),
        "hostname": platform.node(),
    }


def get_cpu():
    info = {
        "name": platform.processor(),
        "physical_cores": None,
        "logical_cores": os.cpu_count(),
        "max_clock_mhz": None,
    }
    for cpu in _powershell_json(
        "Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,MaxClockSpeed"
    ):
        info["name"] = cpu.get("Name", "").strip()
        info["physical_cores"] = cpu.get("NumberOfCores")
        info["max_clock_mhz"] = cpu.get("MaxClockSpeed")
    return info


def get_memory():
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(_MemoryStatus)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return {
        "total_gb": _to_gb(status.ullTotalPhys),
        "available_gb": _to_gb(status.ullAvailPhys),
        "used_percent": status.dwMemoryLoad,
    }


def get_gpus():
    return [
        {
            "name": gpu.get("Name"),
            "driver_version": gpu.get("DriverVersion"),
            "vram_gb": _to_gb(gpu["AdapterRAM"]) if gpu.get("AdapterRAM") else None,
        }
        for gpu in _powershell_json(
            "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion"
        )
    ]


def get_disks():
    disks = []
    for letter in range(ord("A"), ord("Z") + 1):
        path = f"{chr(letter)}:\\"
        if not os.path.exists(path):
            continue
        usage = shutil.disk_usage(path)
        disks.append(
            {
                "drive": path,
                "total_gb": _to_gb(usage.total),
                "used_gb": _to_gb(usage.used),
                "free_gb": _to_gb(usage.free),
            }
        )
    return disks


def get_motherboard():
    boards = _powershell_json(
        "Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product"
    )
    if not boards:
        return {}
    return {"manufacturer": boards[0].get("Manufacturer"), "model": boards[0].get("Product")}


def get_bios():
    bios = _powershell_json(
        "Get-CimInstance Win32_BIOS | Select-Object Manufacturer,SMBIOSBIOSVersion"
    )
    if not bios:
        return {}
    return {"manufacturer": bios[0].get("Manufacturer"), "version": bios[0].get("SMBIOSBIOSVersion")}


def get_system_specifications():
    return {
        "os": get_os(),
        "cpu": get_cpu(),
        "memory": get_memory(),
        "gpus": get_gpus(),
        "disks": get_disks(),
        "motherboard": get_motherboard(),
        "bios": get_bios(),
        "python_version": platform.python_version(),
    }


if __name__ == "__main__":
    print(json.dumps(get_system_specifications(), indent=2))
