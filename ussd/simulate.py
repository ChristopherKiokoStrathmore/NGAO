"""Walk the USSD menus in a terminal, like a feature phone.

    python simulate.py [+254712345678]

Uses DevBackend and MemoryStore unless BACKEND_BASE_URL / DB_DSN are set.
Type the option at each prompt; Ctrl-C to quit.
"""

import sys
import uuid

from callback import create_app


def main():
    phone = sys.argv[1] if len(sys.argv) > 1 else "+254700000001"
    client = create_app().test_client()
    while True:
        session, text = uuid.uuid4().hex[:8], ""
        print(f"\n--- dial *384*55# from {phone} (session {session}) ---")
        while True:
            body = client.post("/ussd", data={"sessionId": session, "phoneNumber": phone,
                                              "serviceCode": "*384*55#", "text": text}).get_data(as_text=True)
            print("\n" + body[4:])
            if body.startswith("END"):
                break
            entry = input("> ").strip()
            text = f"{text}*{entry}" if text else entry
        if input("\nDial again? [Y/n] ").strip().lower() == "n":
            return


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print()
