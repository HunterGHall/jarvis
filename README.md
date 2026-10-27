# Jarvis

A command-line AI assistant powered by Claude, with built-in utilities for everyday info and controlling your PC. Windows only.

## Features

Jarvis can call these tools on its own whenever a question needs them, and the CLI shows you each call as it happens. It can also search and read the web.

**Info**
- Date and time
- Weather, hourly and multi-day forecast, air quality, UV index, sunrise/sunset, and moon phase
- Stocks, crypto, and currency conversion
- Live sports scores (NFL, NBA, WNBA, MLB, NHL, MLS, Premier League, college football and basketball)
- News headlines by topic (including local news for your zip code) and news search, with the other outlets covering each story
- Dictionary definitions, synonyms, and antonyms
- Recipes by dish or ingredient, plus a random recipe

**Your computer**
- System specs and live status (CPU, memory, disks, uptime, battery, top processes)
- Network status (IP addresses, Wi-Fi, latency) and ping
- Media control (play/pause, skip, volume, mute) and now playing
- Open and close apps, websites, and your main folders
- Clipboard read and write
- Windows Do Not Disturb on and off
- Find files in your main folders by name or extension
- Move, copy, rename, create, and delete files and folders
- Check the Recycle Bin and permanently empty it

**Tools**
- Calculator and unit conversion
- Timers (an alert prints in the terminal when one finishes)
- Dice, coin flip, random number, and random pick

### File safety

Jarvis can search, move, copy, rename, and delete files anywhere on your computer.

- Deleting always asks for your approval (`y/N`) first. The prompt lists how many items, how big, and which ones. One approval covers a whole batch, and a folder can be emptied in one go. Everything goes to the Recycle Bin so it can be restored.
- Emptying the Recycle Bin is permanent, so it asks first too, showing the item count and size.
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
   ```

   - `model` is the Claude model Jarvis uses.
   - `name` is how Jarvis addresses you.
   - `zip_code` is your default location for weather, air quality, sun times, and local news.
   - `show_cost = True` shows the token usage and cost of each reply.

3. Run it:

   ```
   python main.py
   ```

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
