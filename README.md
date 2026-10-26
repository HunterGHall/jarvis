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
2. Add your details to `config.conf`:

   ```ini
   [anthropic]
   anthropic_api_key = YOUR_KEY

   [personal]
   name = YOUR_NAME
   zip_code = YOUR_ZIP
   ```

3. Run it:

   ```
   python main.py
   ```

Type a message at the `>` prompt and Jarvis replies.

## License

See [LICENSE](LICENSE).
