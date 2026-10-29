"""The `jarvis` command."""
import os
import sys

USAGE = """Jarvis, a command-line assistant.

  jarvis                 start chatting
  jarvis --voice         start in voice mode
  jarvis config          open your settings file (created first if needed)
  jarvis google-setup    connect your Google account (see the README)
  jarvis --help          show this message
"""


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else ""

    if command in {"-h", "--help", "help"}:
        print(USAGE)
        return

    from jarvis import first_run, paths

    if command == "google-setup":
        from jarvis import google_setup

        google_setup.main(args[1:])
        return
    if command == "config":
        if not paths.CONFIG_PATH.exists():
            first_run.write(paths.CONFIG_PATH)
        print(paths.CONFIG_PATH)
        os.startfile(paths.CONFIG_PATH)
        return
    if command and command != "--voice":
        sys.exit(f"Unknown option '{command}'.\n\n{USAGE}")

    # With no config yet, ask for the essentials; if nobody can be asked, the model module writes a template and stops
    first_run.ensure_config(paths.CONFIG_PATH)

    from jarvis.cli import run

    run(start_in_voice="--voice" in args)
