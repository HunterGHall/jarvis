<h1 align="center">J.A.R.V.I.S.</h1>
<p align="center">
  <em>Just A Rather Very Intelligent System — a personal voice assistant built in Python</em>
</p>
<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python version">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/status-active-brightgreen" alt="Status">
</p>

A command-line AI assistant powered by Claude, with built-in utilities for everyday info and controlling your PC. Windows only.

## Features

Jarvis can call these tools on its own whenever a question needs them, and the CLI shows you each call as it happens. It can also search and read the web.

**Info**
- Date and time
- Weather, hourly and multi-day forecast, air quality, UV index, sunrise/sunset, and moon phase
- Stocks, crypto, and currency conversion
- Live sports scores (NFL, NBA, WNBA, MLB, NHL, MLS, Premier League, college football and basketball)
- News headlines by topic (including local news for your zip code) and news search, with the other outlets covering each story
- Space: NASA's Astronomy Picture of the Day and the live position of the International Space Station
- Recent earthquakes from the USGS, worldwide or near you
- Public holidays, upcoming or by year, for any country
- Dictionary definitions, synonyms, and antonyms
- Recipes by dish or ingredient, plus a random recipe

**Your computer**
- System specs and live status (CPU, memory, disks, uptime, battery, top processes)
- Network status (IP addresses, Wi-Fi, latency) and ping
- Media control (play/pause, skip, volume, mute) and now playing
- Song lyrics, for a named song or whatever is playing right now
- Open and close apps, websites, and your main folders
- Clipboard read and write
- Windows Do Not Disturb on and off
- Find files in your main folders by name or extension
- Move, copy, rename, create, and delete files and folders
- Check the Recycle Bin and permanently empty it
- Read files (text, code, CSV/JSON, Word `.docx`, and PDF) and write text files
- Look inside any folder (optionally including its subfolders) and create folders with files already in them
- Set the speaker volume to an exact percentage, or mute it
- Run terminal commands in PowerShell, with your approval for every command
- Set, check, and clear your GitHub profile status, optionally clearing itself after a while ("Coding" for two hours)
- Your Google account (optional, one-time setup): read, search, draft, and send Gmail; read and manage Calendar events; search, read, upload, organize, and share Drive files; read and write Docs, Sheets, and Slides

**Tools**
- Calculator and unit conversion
- Timers (an alert prints in the terminal when one finishes)
- Dice, coin flip, random number, and random pick

### Terminal safety

- Every command is shown to you in full and runs only after you answer `y` at the `y/N` prompt. There is no "always allow".
- Commands run in Windows PowerShell as you, starting in your home folder. The working directory carries over between commands, but variables don't.
- A command is stopped after 120 seconds, and long output is trimmed before it goes to Claude.
- A command can do anything you could do in a terminal, so read what it's about to run. Prompt text from web pages or files can't approve anything for you.

### File safety

Jarvis can search, move, copy, rename, and delete files anywhere on your computer.

- Deleting always asks for your approval (`y/N`) first. The prompt lists how many items, how big, and which ones. One approval covers a whole batch, and a folder can be emptied in one go. Everything goes to the Recycle Bin so it can be restored.
- Emptying the Recycle Bin is permanent, so it asks first too, showing the item count and size.
- In voice mode (`/voice`), these questions are asked out loud and you answer by saying yes or no. An unclear answer, or any "no", leaves everything as it was. Terminal commands are always approved on the keyboard, because you need to read the exact command.
- Writing a file never replaces an existing one by default. Overwriting asks first and sends the old version to the Recycle Bin. Nothing is written inside `C:\Windows` or `Program Files`.
- Moves, copies, and renames never overwrite an existing file.
- Whole drives, `C:\Windows`, `Program Files`, and your user folder itself are never deleted, moved, or renamed.
- A file search with no folder covers your main folders (Desktop, Documents, Downloads, Pictures, Music, Videos). Name any other folder or a whole drive to search there.
- `close_app` closes windows the way the X button does, so unsaved work still prompts. It never closes the terminal Jarvis runs in.

## Setup

1. Install Python 3.10 or newer and the dependencies:

   ```
   pip install -r requirements.txt
   ```

2. Run it once to generate `config.conf` (or create it yourself), then add your details:

   ```ini
   [anthropic]
   anthropic_api_key = YOUR_KEY
   model = claude-sonnet-5-5

   [personal]
   name = YOUR_NAME
   zip_code = YOUR_ZIP

   [settings]
   show_cost = False
   history_turns = 12

   [github]
   token =
   ```

   - `model` is the Claude model Jarvis uses.
   - `name` is how Jarvis addresses you.
   - `zip_code` is your default location for weather, air quality, sun times, and local news.
   - `show_cost = True` shows the token usage and cost of each reply, including how many input tokens came from the prompt cache.
   - `history_turns` is how many of your recent messages (with Jarvis's replies) are remembered and re-sent with each new one. Older ones are dropped in chunks, since the whole conversation is sent every time. The default is 12.
   - `[github] token` is optional and only needed to change your GitHub status. Create a classic personal access token at github.com/settings/tokens with the `user` scope. It's read from `config.conf` (which is gitignored) and never printed or sent anywhere except to GitHub.

3. Run it:

   ```
   python main.py
   ```

## Google (Gmail, Calendar, Drive, Docs, Sheets, Slides)

Optional. Jarvis signs in as you, so it can reach your own mail, calendar, and files without anything being shared with a bot account, and you never have to share a document with it. The setup is done once:

1. Run `python -m jarvis.google_setup`. With no credentials file yet, it prints the steps below with your links.
2. In [Google Cloud](https://console.cloud.google.com/projectcreate), create a project and turn on the six APIs (the setup output has a single link that enables them all).
3. Under "OAuth consent screen", choose External, add your own Google account as a test user, then press **Publish app**. Without that, the sign-in expires every 7 days. Google will call the app unverified; since it's your own, choose Advanced, then "Go to Jarvis".
4. Under "Credentials", create an **OAuth client ID** of type **Desktop app** and download the JSON.
5. Run `python -m jarvis.google_setup "path\to\that\file.json"`. A browser tab opens; approve every permission. It then checks each service and tells you if one still needs its API switched on.
6. Restart Jarvis. The Google tools only appear once setup is done.

Your credentials and sign-in are saved as `google_credentials.json` and `google_token.json` in the project folder, both gitignored. They stay on your machine and go only to Google.

Reading mail and documents sends their text to Claude to be understood, like any other file Jarvis reads. Anything that reaches other people or can't be undone easily asks first, with the full details shown (or spoken, in voice mode): sending an email, inviting people to an event, deleting an event, trashing a file or an email, sharing a file, and overwriting cells in a sheet. Text found inside emails and documents is treated as data, not as instructions.

## Using it

Type a message at the `>` prompt and Jarvis replies. Type `exit` or press Ctrl+C to quit.

```
  🔍 web_search  query="latest Python release"  [server]
  ⚙  get_time    [local]
     ╰─ ✓ 0.0s  "9:18:55 PM"
┌─ JARVIS ─────────────────────────────────────────────────┐
│  It's 9:18 PM, sir. The latest Python release is 3.15.2. │
└──────────────────────────────────── 3.4s · 2 tool calls ─┘
```

- Every tool call and web search is shown as it runs, with its arguments, how long it took, and a preview of the result.
- With `show_cost = True`, a line under each reply shows input and output tokens with their cost, plus any web searches (billed per search, on top of the token cost).
- Conversations are saved in `jarvis/models/conversations/`.

Some things to try:

- "What's the weather tomorrow, and is the air quality OK?"
- "What's in the news today?" or "Any news about NASA this week?"
- "Set a timer for 10 minutes for pasta."
- "How many cups is 500 ml?"
- "What can I make with chicken?"
- "Find my newest PDFs in Downloads and move them into Documents."
- "Pause the music and turn on Do Not Disturb."

## Adding a utility

Utilities live in `jarvis/models/utilities/<name>/`. Each is a plain Python module whose functions return a dict (or an empty dict on failure). To give Jarvis a new one, import its function in `jarvis/models/default/default_model.py`, add it to `UTILITY_FUNCTIONS`, and describe it in `UTILITY_TOOLS`. Add an icon in `TOOL_STYLES` in `jarvis/cli.py` if you want one.

## License

See [LICENSE](LICENSE).
