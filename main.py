from jarvis.models.default.default_model import send_message

try:
    while True:
        message = input("> ")
        print(send_message(message, "default"))
except KeyboardInterrupt:
    print("\nGoodbye sir.")
