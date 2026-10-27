# Jarvis

A command-line AI assistant powered by Claude, with built-in utilities for everyday info.

## Features

- Weather, forecast, air quality, and sun/moon phases
- Date and time
- Finance and sports scores
- Dictionary lookups
- System specs and status
- Windows media control

## Setup

1. Install Python 3 and the dependencies (`anthropic`, etc.).
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

   Set `show_cost = True` to show the token usage and cost of each reply.

3. Run it:

   ```
   python main.py
   ```

Type a message at the `>` prompt and Jarvis replies.

## License

See [LICENSE](LICENSE).
