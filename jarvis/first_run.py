"""Creating config.conf the first time Jarvis runs."""
import getpass
import sys

TEMPLATE = """[anthropic]
anthropic_api_key = {api_key}
model = claude-haiku-5-5

[personal]
name = {name}
zip_code = {zip_code}

[settings]
show_cost = False

# Optional: a classic GitHub personal access token with the 'user' scope, to change your GitHub status
[github]
token =
"""


def render(api_key="YOUR_KEY", name="YOUR_NAME", zip_code="YOUR_ZIP"):
    return TEMPLATE.format(api_key=api_key, name=name, zip_code=zip_code)


def write(path, **fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(**fields), encoding="utf-8")


def ensure_config(path, ask=input, ask_secret=getpass.getpass, interactive=None):
    """Makes sure config.conf exists, asking for the essentials if it doesn't. Returns False if it couldn't (nobody to ask)."""
    if path.exists():
        return True
    if interactive is None:
        interactive = sys.stdin is not None and sys.stdin.isatty()
    if not interactive:
        return False

    print("Welcome to Jarvis. Let's set it up; this only happens once.\n")
    key = ""
    for _ in range(3):
        key = ask_secret("Claude API key (create one at https://console.anthropic.com/settings/keys): ").strip()
        if key:
            break
        print("A key is needed to talk to Claude.")
    if not key:
        return False
    name = ask("Your name (optional, Enter to skip): ").strip()
    zip_code = ask("Your US zip code, for weather and local news (optional, Enter to skip): ").strip()
    write(path, api_key=key, name=name, zip_code=zip_code)
    print(f"\nSaved to {path}\nYou can change any setting later with: jarvis config\n")
    return True
