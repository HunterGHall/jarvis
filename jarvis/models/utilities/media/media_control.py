import ctypes
import json
import subprocess

# Virtual-key codes for the Windows media keys.
MEDIA_KEYS = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "stop": 0xB2,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "mute": 0xAD,
}

KEYEVENTF_KEYUP = 0x0002

NOW_PLAYING_SCRIPT = """
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
[void][Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]
$manager = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
$session = $manager.GetCurrentSession()
if ($session) {
    $props = Await ($session.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
    [pscustomobject]@{
        title = $props.Title
        artist = $props.Artist
        album = $props.AlbumTitle
        app = $session.SourceAppUserModelId
        status = $session.GetPlaybackInfo().PlaybackStatus.ToString()
    } | ConvertTo-Json -Compress
}
"""


def _press(key_code, times=1):
    for _ in range(times):
        ctypes.windll.user32.keybd_event(key_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key_code, 0, KEYEVENTF_KEYUP, 0)


def media_control(action, times=1):
    action = action.strip().lower()
    key_code = MEDIA_KEYS.get(action)
    if key_code is None:
        return {"error": f"Unknown action: {action}", "actions": list(MEDIA_KEYS)}
    # Each volume key press moves the volume by 2%.
    _press(key_code, max(1, int(times)) if action.startswith("volume") else 1)
    return {"action": action, "ok": True}


def get_now_playing():
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", NOW_PLAYING_SCRIPT],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}


if __name__ == "__main__":
    print(json.dumps(get_now_playing(), indent=2))
