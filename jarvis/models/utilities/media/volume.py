import json
import subprocess

# Talks to the default speakers through the Windows Core Audio COM interfaces. The numbered
# placeholder methods keep the vtable order right for the ones that aren't used.
AUDIO_SCRIPT = r"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {
    int _0(); int _1(); int _2(); int _3();
    int SetMasterVolumeLevelScalar(float level, Guid context);
    int _5();
    int GetMasterVolumeLevelScalar(out float level);
    int _7(); int _8(); int _9(); int _10();
    int SetMute([MarshalAs(UnmanagedType.Bool)] bool mute, Guid context);
    int GetMute(out bool mute);
}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {
    int Activate(ref Guid id, int clsCtx, int activationParams, out IAudioEndpointVolume endpoint);
}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {
    int _0();
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device);
}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorComObject { }
public class Audio {
    static IAudioEndpointVolume Endpoint() {
        var enumerator = new MMDeviceEnumeratorComObject() as IMMDeviceEnumerator;
        IMMDevice device;
        Marshal.ThrowExceptionForHR(enumerator.GetDefaultAudioEndpoint(0, 1, out device));
        IAudioEndpointVolume endpoint;
        var id = typeof(IAudioEndpointVolume).GUID;
        Marshal.ThrowExceptionForHR(device.Activate(ref id, 23, 0, out endpoint));
        return endpoint;
    }
    public static float Volume {
        get { float level; Marshal.ThrowExceptionForHR(Endpoint().GetMasterVolumeLevelScalar(out level)); return level; }
        set { Marshal.ThrowExceptionForHR(Endpoint().SetMasterVolumeLevelScalar(value, Guid.Empty)); }
    }
    public static bool Mute {
        get { bool mute; Marshal.ThrowExceptionForHR(Endpoint().GetMute(out mute)); return mute; }
        set { Marshal.ThrowExceptionForHR(Endpoint().SetMute(value, Guid.Empty)); }
    }
}
'@
"""


def _run_audio(commands):
    script = AUDIO_SCRIPT + commands + "\n[pscustomobject]@{ level = [math]::Round([Audio]::Volume * 100); muted = [Audio]::Mute } | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=20
        )
        data = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"error": "Couldn't reach the audio device."}
    return {"volume_percent": int(data["level"]), "muted": bool(data["muted"])}


def get_volume():
    return _run_audio("")


def set_volume(level=None, muted=None):
    commands = []
    if level is not None:
        level = max(0, min(100, int(level)))
        commands.append(f"[Audio]::Volume = {level / 100}")
    if muted is not None:
        commands.append(f"[Audio]::Mute = ${'true' if muted else 'false'}")
    if not commands:
        return {"error": "Give a level (0-100) and/or muted true/false."}
    return _run_audio("\n".join(commands))


if __name__ == "__main__":
    print(json.dumps(get_volume(), indent=2))
