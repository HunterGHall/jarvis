<h1 align="center">J.A.R.V.I.S.</h1>
<p align="center">
  <em>Just A Rather Very Intelligent System</em>
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
- Your Google account (optional, one-time setup): read, search, draft, and send Gmail; read and manage Calendar events; search, read, upload, organize, and share Drive files; read and write Docs, Sheets, and Slides, including putting pictures from the web into Docs, Sheets, and Slides

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

   Every setting is explained in [Configuration](#configuration) below.

3. Run it:

   ```
   python main.py
   ```

## Desktop app (Windows)

Jarvis also runs as a normal window, built with Electron (HTML, CSS, and JavaScript in `app/renderer`). It talks to the same Python code through `jarvis/server.py`, so every tool, your `config.conf`, and your saved conversation work the same way as in the terminal. Deleting files and running terminal commands ask for approval in a dialog.

1. Install [Node.js](https://nodejs.org), then set up and build:

   ```
   cd app
   npm install
   npm run build
   ```

2. Run `app\dist\jarvis.exe`. For development, `npm start` in `app` opens the window without building.

That `jarvis.exe` is the window only. It starts Python in the project folder, so it has to stay inside the project (it looks for `jarvis/server.py` next to itself and in the folders above), and the Python requirements above still need to be installed. Set `JARVIS_HOME` to the project folder or `JARVIS_PYTHON` to a Python path if it can't find them.

### Installer

To give Jarvis to someone (or install it like any other Windows app) build the installer instead:

```
cd app
npm run build:setup
```

This produces `app\dist-setup\jarvis-setup.exe` (about 180 MB). It is a normal setup wizard: licence, who it is for, install location, Start menu and desktop shortcuts, a "launch Jarvis" box at the end, and an entry in Apps & features to uninstall it. It carries its own copy of Python and every package, so the PC needs nothing installed first. The build downloads the matching Python runtime and the packages, so it needs the same Python version as the one on the build PC (3.10 here) and an internet connection, and the first run takes a few minutes. `npm run prepare:backend` alone rebuilds just that bundle (`app\backend-build`); `powershell -File scripts\prepare-backend.ps1 -CodeOnly` refreshes only the Jarvis code in it.

An installed Jarvis keeps what is yours (`config.conf` with your keys, the saved conversation, the Google sign-in, and the speech-recognition model it downloads) in `%APPDATA%\jarvis`, not in the install folder, so installing a newer version over it keeps everything. Uninstalling removes all of it, so nothing of yours is left on the PC afterwards. The first time it starts, a welcome screen asks for your Anthropic API key (checked with Anthropic before it is saved, so a typo is caught straight away), and optionally a Fish Audio key, your name and your zip code. Everything can be changed later in Settings.

The installer is not code-signed, so Windows SmartScreen may say "unknown publisher" the first time: choose More info, then Run anyway.

The window is just two things: the Jarvis ring (`app/renderer/core.js`) and the console beside it. In the middle of the ring is a visualizer: at rest its rings turn and a slow wave runs around the bars, and while Jarvis speaks aloud it draws the spectrum of the actual audio (the voice code reports levels to the window). It also ripples while it listens and pulses while it thinks. When a tool runs, a shockwave leaves the logo, a lane of the ring lights up in the tool's color with a comet running along it, and the tool is listed inside the circle; when it ends, the lane flashes green (or red) and fades.

**Modes.** The four buttons above the console choose how you and Jarvis talk:

| Mode | You | Jarvis |
|---|---|---|
| Text | type | types back |
| Dictate | speak | types back |
| Read aloud | type | speaks back |
| Voice | speak | speaks back |

In Dictate and Voice there is no button: as soon as you pick the mode Jarvis listens by itself, and it only reacts after it hears its name, every time: "Jarvis, what's the weather?", or just "Jarvis" and then your request. After it answers it goes straight back to sleep. If you would rather not repeat the name, set `wake_mode` to `stay_awake` in the voice settings: after the name it then keeps the conversation going without it until you have said nothing for 30 seconds (`idle_timeout`, counted from the end of its last answer), and then it needs the name again. Saying "stop listening" also puts it to sleep. The wake word itself, and how sensitive the microphone is (`mic_threshold` and `noise_margin`; lower hears softer voices), are in the voice settings too, and setting the wake word to `none` makes it always listen. Switching to a typing mode turns the microphone off. Speaking needs a Fish Audio key. Listening loads its model the first time, so it takes a few seconds to start. The mode is not a setting and is not saved: Jarvis always starts in Text, so it never starts listening or speaking by surprise.

**Settings.** The gear in the console opens the settings page: dark (the default) or light theme, your Anthropic, Fish Audio and GitHub keys (shown only as "saved, ends in ...", never in full), the model, your name and zip code, how many messages are remembered, whether to show the cost under replies, and every voice setting, with a button to test the voice. Changes are written to `config.conf` and take effect straight away, no restart. On a first run with no key, the settings page opens by itself.


## Configuration

All settings live in `config.conf` in the project folder. It is created the first time you run Jarvis and is gitignored, so your keys stay on your machine. Edit it in any text editor and restart Jarvis to apply changes, or change it from the desktop app's settings page, which applies changes immediately. A missing or blank setting uses its default.

### `[anthropic]`

| Setting | Default | What it does |
|---|---|---|
| `anthropic_api_key` | none (required) | Your Claude API key. |
| `model` | `claude-sonnet-5-5` if missing; the first-run file uses `claude-haiku-5-5` | Which Claude model Jarvis uses. Haiku is the cheapest and fastest; larger models reason better and cost more. |

### `[personal]`

| Setting | Default | What it does |
|---|---|---|
| `name` | none | How Jarvis knows you. It is told your name, and addresses you as "sir". |
| `zip_code` | none | Your US zip code, the default place for weather, forecasts, air quality, sunrise and sunset, local news, and earthquakes near you. |

### `[settings]`

| Setting | Default | What it does |
|---|---|---|
| `show_cost` | `False` | `True` shows what each reply cost: input and output tokens with their price, how many input tokens came from the prompt cache, and the number of web searches. |
| `auto_resize` | `True` | Redraws the screen at the new width when you resize the window, so panels don't fall apart. `False` turns it off. |
| `history_turns` | `12` | How many of your recent messages (with Jarvis's replies) it remembers and re-sends with each new one. Once the history reaches half again as many (18 by default), the oldest are dropped in one go. Lower is cheaper; higher remembers further back. The minimum is 2. |

### `[github]`

| Setting | Default | What it does |
|---|---|---|
| `token` | none | Optional. Lets Jarvis set, check, and clear your GitHub status. Create a *classic* personal access token at github.com/settings/tokens with the `user` scope. It is only ever sent to GitHub. |

### `[fish]`

| Setting | Default | What it does |
|---|---|---|
| `api_key` | none | Needed for Jarvis to speak. Get a key at fish.audio. Speech is made by Fish Audio's service, so each sentence Jarvis speaks is sent to them. It is only ever sent there. |

### `[voice]`

Listening happens on your PC (faster-whisper); speaking goes through Fish Audio. Nothing here is needed to start; every setting has a default. Change them live in Jarvis, or write them in this section:

| Command | What it does |
|---|---|
| `/voice settings` | Lists every voice setting with its current value and a description. |
| `/voice set <name> <value>` | Changes a setting immediately and saves it to `config.conf`, for example `/voice set speed 1.1`. |
| `/voice voices` | Shows the voice model and speech model in use. |
| `/voice test [text]` | Speaks a sample, so you can hear a change. |

| Setting | Default | What it does |
|---|---|---|
| `reference_id` | the Jarvis voice | Which Fish Audio voice model speaks. Copy the id from any voice's page on fish.audio. |
| `model` | `s2.1-pro-free` | Fish Audio's speech model: `s1`, `s2-pro`, `s2.1-pro`, `s2.1-pro-free`, or `drama-3`. |
| `speed` | `1.0` | Speaking pace, 0.5 to 2. |
| `volume` | `0` | Volume change in decibels; positive is louder. |
| `latency` | `normal` | `normal`, `balanced`, or `low`. Lower starts sooner but may sound rougher. |
| `temperature` | `0.7` | How much the delivery varies, 0 to 1. |
| `top_p` | `0.7` | How adventurous the delivery is, 0 to 1. |
| `normalize` | `true` | Says numbers and symbols as words. |
| `silence` | `0.8` | Seconds of quiet that end your turn while you are talking to Jarvis. |
| `preload` | `true` | Loads the listening model when Jarvis starts, so voice is ready right away. `false` starts faster but the first voice use is slow. |
| `whisper_model` | `base.en` | The speech-to-text model that hears you. A larger one is more accurate and slower. |
| `max_chunk` | `120` | Characters spoken per request. Smaller starts speaking sooner. |
| `max_prebuffer` | `10` | The longest wait, in seconds, before playback starts. |

The built-in defaults are listed in `OPTIONS` at the top of `jarvis/voice/__init__.py`.

### Other files

| File | What it is |
|---|---|
| `google_credentials.json`, `google_token.json` | Your Google sign-in, created by `python -m jarvis.google_setup`. Gitignored. |
| `jarvis/models/training_data/jarvis.txt` | The personality and style Jarvis uses when you type. |
| `jarvis/models/training_data/jarvis-voice.txt` | The same, for voice mode, written for short spoken answers. |
| `jarvis/models/conversations/` | Your saved conversation. Gitignored. |

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

Pictures come from `search_images`, which looks on Wikimedia Commons (then Openverse) for pictures that are free to reuse and gives back the credit their license asks for; Jarvis adds that credit as a caption in Docs and Slides. You can also give it a direct link to a PNG, JPEG, or GIF. Google fetches the picture itself, so the link has to be public, and links into your own network are refused.

## Using it

Type a message at the `>` prompt and Jarvis replies. Type `exit` or press Ctrl+C to quit.

```
  • web_search  query="latest Python release"  [server]
  • get_time    [local]
     ╰─ ✓ 0.0s  "9:18:55 PM"
┌─ JARVIS ─────────────────────────────────────────────────┐
│  It's 9:18 PM, sir. The latest Python release is 3.15.2. │
└──────────────────────────────────── 3.4s · 2 tool calls ─┘
```

- Every tool call and web search is shown as it runs, with its arguments, how long it took, and a preview of the result.
- With `show_cost = True`, a line under each reply shows input and output tokens with their cost, plus any web searches (billed per search, on top of the token cost).
- Resize the window whenever you like. Once you stop dragging, Jarvis clears the screen and redraws the whole conversation at the new width. It waits if you have started typing, and if a reply is being written it redraws just before the next prompt, so it never cuts into either. This does clear the terminal's scrollback, and it remembers the last 400 things it printed. Turn it off with `auto_resize = False`.
- Conversations are saved in `jarvis/models/conversations/`.

Some things to try:

- "What's the weather tomorrow, and is the air quality OK?"
- "What's in the news today?" or "Any news about NASA this week?"
- "Set a timer for 10 minutes for pasta."
- "How many cups is 500 ml?"
- "What can I make with chicken?"
- "Find my newest PDFs in Downloads and move them into Documents."
- "Pause the music and turn on Do Not Disturb."

## Voice mode

Talk to Jarvis instead of typing. Start with `python main.py --voice`, or type `/voice` in a running chat.

1. **Listening:** your microphone is heard by faster-whisper, which runs on your PC. Jarvis waits for you to speak, then for a pause (`silence` in `[voice]`).
2. **Thinking:** the words go to Claude like any typed message, using the shorter spoken-style prompt in `jarvis/models/training_data/jarvis-voice.txt`.
3. **Speaking:** the reply is cleaned up (no links or code) and sent to Fish Audio, which sends back speech. Playback starts while the rest is still being made.

Say "exit", "stop", or "goodbye" to leave voice mode. Yes/no questions, such as confirming an email, are asked and answered out loud. Setup is a Fish Audio key under `[fish]` and, optionally, the settings under `[voice]` above.

Code lives in `jarvis/voice/`: `__init__.py` does the listening and playback, `tts.py` talks to Fish Audio.

## Adding a utility

Utilities live in `jarvis/models/utilities/<name>/`. Each is a plain Python module whose functions return a dict (or an empty dict on failure). To give Jarvis a new one, import its function in `jarvis/models/default/default_model.py`, add it to `UTILITY_FUNCTIONS`, and describe it in `UTILITY_TOOLS`. Add an icon in `TOOL_STYLES` in `jarvis/cli.py` if you want one.

## License

See [LICENSE](LICENSE).
