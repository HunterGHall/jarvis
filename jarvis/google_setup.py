"""One-time Google sign-in: jarvis google-setup [path\\to\\downloaded\\credentials.json]"""
import shutil
import sys
from pathlib import Path

UTILITIES = Path(__file__).resolve().parent / "models" / "utilities"
for folder in ("google", "files"):
    sys.path.insert(0, str(UTILITIES / folder))

import google_auth  # noqa: E402
from google_auth import GoogleError, api  # noqa: E402

ENABLE_APIS = (
    "https://console.cloud.google.com/flows/enableapi?apiid="
    "gmail.googleapis.com,calendar-json.googleapis.com,drive.googleapis.com,docs.googleapis.com,sheets.googleapis.com,slides.googleapis.com"
)

INSTRUCTIONS = f"""
Jarvis needs a Google credentials file before you can sign in. This takes about five minutes, once:

  1. Go to https://console.cloud.google.com/projectcreate and make a project (any name, e.g. "Jarvis").
  2. Turn on the six Google APIs it uses, all at once, with this link (pick your project, then Enable):
       {ENABLE_APIS}
  3. Open "APIs & Services" > "OAuth consent screen" (or "Google Auth Platform").
       - User type: External. App name: Jarvis. Use your own email for the contact fields.
       - Under "Audience", add your own Google account as a test user. (Skip this and Google shows
         "Error 403: access_denied" when you sign in.) Use the same account you'll pick in the browser.
       - Then press "Publish app" (Audience page) so the sign-in doesn't expire every 7 days. Google will
         say the app is unverified when you sign in; that's expected for your own app. Choose
         Advanced > "Go to Jarvis (unsafe)".
  4. Open "APIs & Services" > "Credentials" > Create credentials > OAuth client ID.
       - Application type: Desktop app. Name: Jarvis. Create.
       - Click "Download JSON".
  5. Run this again, with the path to that file:
       jarvis google-setup "C:\\Users\\you\\Downloads\\client_secret_....json"

Nothing is shared with a bot: Jarvis signs in as you, so it can reach whatever you can.
"""

CHECKS = [
    ("Gmail", "https://gmail.googleapis.com/gmail/v1/users/me/profile"),
    ("Calendar", "https://www.googleapis.com/calendar/v3/users/me/calendarList?maxResults=1"),
    ("Drive", "https://www.googleapis.com/drive/v3/about?fields=user"),
    ("Docs", "https://docs.googleapis.com/v1/documents/does-not-exist"),
    ("Sheets", "https://sheets.googleapis.com/v4/spreadsheets/does-not-exist"),
    ("Slides", "https://slides.googleapis.com/v1/presentations/does-not-exist"),
]


def main(args=None):
    args = sys.argv[1:] if args is None else args
    if args:
        source = Path(args[0].strip('"'))
        if not source.is_file():
            sys.exit(f"Can't find {source}")
        shutil.copyfile(source, google_auth.CREDENTIALS_PATH)
        print(f"Saved your credentials as {google_auth.CREDENTIALS_PATH.name}.")
    if not google_auth.CREDENTIALS_PATH.exists():
        print(INSTRUCTIONS)
        return

    print("Opening your browser to sign in to Google. Approve every permission it lists.\n")
    try:
        google_auth.authorize()
    except GoogleError as error:
        sys.exit(f"Sign-in failed: {error}")

    print("Signed in. Checking each service...\n")
    failures = 0
    for name, url in CHECKS:
        try:
            api("GET", url)
            status = "ready"
        except GoogleError as error:
            message = str(error)
            # Asking for a document that doesn't exist is how Docs, Sheets and Slides are tested: "not found" means the API works
            if name in {"Docs", "Sheets", "Slides"} and ("not found" in message.lower() or "requested entity" in message.lower() or "invalid" in message.lower()):
                status = "ready"
            else:
                status, failures = f"problem: {message}", failures + 1
        print(f"  {name:<9} {status}")

    try:
        email = api("GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile").get("emailAddress")
        print(f"\nConnected as {email}.")
    except GoogleError:
        pass
    if failures:
        print("\nA service that says 'problem' usually just needs its API switched on with the link in step 2:\n  " + ENABLE_APIS)
    print("\nRestart Jarvis and the Google tools will be there.")


if __name__ == "__main__":
    main()
