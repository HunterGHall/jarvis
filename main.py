from jarvis.models.default.default_model import send_message
from rich import print

try:
    while True:
        message = input("> ")
        print(send_message(message, "default"))
except KeyboardInterrupt:
    print("\n[dim]Goodbye sir.[/dim]")
