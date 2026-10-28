import sys

from jarvis.cli import run

run(start_in_voice="--voice" in sys.argv[1:])
