import json
import winreg

# Windows' "Do not disturb" toggle: 1 means notification banners are allowed, 0 means they're muted.
KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
VALUE_NAME = "NOC_GLOBAL_SETTING_TOASTS_ENABLED"


def get_do_not_disturb():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY_PATH) as key:
            toasts_enabled, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        # The value only exists once the setting has been changed, so absent means notifications are on.
        toasts_enabled = 1
    return {"do_not_disturb": toasts_enabled == 0}


def set_do_not_disturb(enabled):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY_PATH) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_DWORD, 0 if enabled else 1)
    return get_do_not_disturb()


if __name__ == "__main__":
    print(json.dumps(get_do_not_disturb(), indent=2))
