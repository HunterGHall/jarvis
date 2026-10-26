import json
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request


def _local_ip():
    # Connecting a UDP socket sends nothing; it just picks the outbound interface.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            return None


def _public_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as response:
            return response.read().decode().strip()
    except (OSError, urllib.error.URLError):
        return None


def _latency_ms(host="1.1.1.1", port=53):
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=3):
            return round((time.perf_counter() - start) * 1000)
    except OSError:
        return None


def _wifi():
    try:
        output = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}

    def field(name):
        match = re.search(rf"^\s*{name}\s*:\s*(.+)$", output, re.MULTILINE)
        return match.group(1).strip() if match else None

    ssid = field("SSID")
    if not ssid:
        return {}
    signal = field("Signal")
    return {
        "ssid": ssid,
        "signal_percent": int(signal.rstrip("%")) if signal else None,
        "band": field("Band"),
        "link_speed_mbps": field("Receive rate \\(Mbps\\)"),
    }


def get_network_status():
    latency = _latency_ms()
    return {
        "connected": latency is not None,
        "latency_ms": latency,
        "hostname": socket.gethostname(),
        "local_ip": _local_ip(),
        "public_ip": _public_ip(),
        "wifi": _wifi(),
    }


def ping_host(host, count=4):
    host = host.strip()
    # A hostname or IP only; this also keeps anything that looks like a flag out of the command.
    if not re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?", host):
        return {"error": f"Invalid host: {host!r}"}
    count = max(1, min(int(count), 10))
    try:
        output = subprocess.run(
            ["ping", "-n", str(count), host], capture_output=True, text=True, timeout=count * 5 + 5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {"host": host, "reachable": False}

    received = re.search(r"Received = (\d+)", output)
    average = re.search(r"Average = (\d+)ms", output)
    minimum = re.search(r"Minimum = (\d+)ms", output)
    maximum = re.search(r"Maximum = (\d+)ms", output)
    packets = int(received.group(1)) if received else 0
    return {
        "host": host,
        "reachable": packets > 0,
        "packets_sent": count,
        "packets_received": packets,
        "min_ms": int(minimum.group(1)) if minimum else None,
        "avg_ms": int(average.group(1)) if average else None,
        "max_ms": int(maximum.group(1)) if maximum else None,
    }


if __name__ == "__main__":
    print(json.dumps(get_network_status(), indent=2))
    print(json.dumps(ping_host("google.com", 2), indent=2))
