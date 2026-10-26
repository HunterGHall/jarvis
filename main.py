from jarvis.models.default.default_model import send_message

while True:
    message = input("> ")
    print(send_message(message, "default"))