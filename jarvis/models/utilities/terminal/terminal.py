"""Runs the commands from Claude's bash tool (bash_20250124) in Windows PowerShell, after the user approves each one.

The tool is stateful in Claude's mind, so the working directory is carried from one command to the next. Variables
are not: every command runs in a fresh PowerShell.
"""
import subprocess
from pathlib import Path

import file_operations

TIMEOUT_SECONDS = 120
MAX_OUTPUT_CHARS = 10_000
CWD_MARKER = "<<JARVIS-CWD>>"

_cwd = str(Path.home())


def _wrap(command):
    # The marker line reports where the command left the working directory, so the next one can start there.
    return (
        "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
        f"Set-Location -LiteralPath '{_cwd.replace(chr(39), chr(39) * 2)}'\n"
        f"{command}\n"
        f"Write-Output ('{CWD_MARKER}' + (Get-Location).Path)"
    )


def _clip(text):
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    half = MAX_OUTPUT_CHARS // 2
    return f"{text[:half]}\n... [{len(text) - MAX_OUTPUT_CHARS} characters cut from the middle] ...\n{text[-half:]}"


def run_bash(tool_input, timeout=TIMEOUT_SECONDS):
    """Returns (output, is_error) for one bash tool call."""
    global _cwd
    if tool_input.get("restart"):
        _cwd = str(Path.home())
        return "Terminal restarted. Back in the home folder.", False

    command = str(tool_input.get("command", "")).strip()
    if not command:
        return "No command given.", True

    confirm = file_operations.CONFIRM
    if confirm is None or not confirm(f"Run this in PowerShell?\n\n    {command}\n"):
        return "The user didn't approve this command, so it was not run.", True

    process = subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _wrap(command)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kills PowerShell and anything it started, so a hung command can't linger.
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        process.communicate()
        return f"The command timed out after {timeout} seconds and was stopped.", True

    lines = stdout.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].startswith(CWD_MARKER):
            _cwd = lines[index][len(CWD_MARKER):].strip() or _cwd
            del lines[index]
            break
    output = "\n".join(lines).rstrip()
    errors = stderr.strip()

    parts = [part for part in (_clip(output), f"[stderr]\n{_clip(errors)}" if errors else "") if part]
    if process.returncode:
        parts.append(f"[exit code {process.returncode}]")
    return "\n".join(parts) or "(no output)", False


def current_directory():
    return _cwd
