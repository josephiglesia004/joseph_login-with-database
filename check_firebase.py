"""
check_firebase.py
-----------------
Checks that the Firebase setup is correct before running the app.

Run:
    python check_firebase.py

Shows [OK] when everything is good and [X] with a fix when something is missing.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

import requests

load_dotenv()

OK = "[OK]"
FAIL = "[X]"


def line(status, message):
    print(f" {status} {message}")


def main():
    print("\n=== Firebase setup checker ===\n")
    problems = []

    # 1) .env
    if Path(".env").exists():
        line(OK, ".env file found.")
    else:
        line(FAIL, "No .env file. Run: Copy-Item .env.example .env")
        problems.append("env")

    # 2) service account key
    key_file = Path(os.getenv("FIREBASE_CREDENTIALS", "serviceAccountKey.json"))
    project_id = None
    if not key_file.exists():
        line(FAIL, f"Service account key not found: {key_file}")
        line(" ", "Firebase Console -> Project settings -> Service accounts -> Generate new private key")
        problems.append("key")
    else:
        try:
            info = json.loads(key_file.read_text(encoding="utf-8"))
            project_id = info.get("project_id")
            line(OK, f"Service account key found. Project: {project_id}")
        except (ValueError, OSError) as error:
            line(FAIL, f"Can't read {key_file}: {error}")
            problems.append("key")

    # 3) web api key
    api_key = os.getenv("FIREBASE_API_KEY", "").strip()
    if api_key and api_key != "ilagay-ang-web-api-key":
        line(OK, "FIREBASE_API_KEY found.")
    else:
        line(FAIL, "FIREBASE_API_KEY is missing from .env.")
        line(" ", "Firebase Console -> Project settings -> General -> Web API key")
        problems.append("api_key")

    if problems:
        print("\nSetup is incomplete. Follow the steps in README.md.\n")
        return 1

    # 4) Firestore + Auth connection
    print("\n--- Testing the connection ---\n")
    try:
        import firebase_admin
        from firebase_admin import auth, credentials, firestore

        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(credentials.Certificate(str(key_file)))

        snapshots = firestore.client().collection("users").limit(1).get()
        total = len(list(snapshots))
        line(OK, f"Connected to Firestore. Users docs read: {total}")
    except Exception as error:  # noqa: BLE001
        line(FAIL, f"Firestore error: {error}")
        line(" ", "Have you created the Firestore Database in the Firebase Console?")
        return 1

    try:
        users = list(auth.list_users(max_results=1).iterate_all())
        line(OK, f"Connected to Authentication. Users: {len(users)} (max 1 checked)")
    except Exception as error:  # noqa: BLE001
        line(FAIL, f"Authentication error: {error}")
        return 1

    # 5) Is Email/Password sign-in enabled?
    try:
        response = requests.post(
            "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
            params={"key": api_key},
            json={
                "email": "check@example.com",
                "password": "hindi-totoong-password",
                "returnSecureToken": True,
            },
            timeout=15,
        )
        code = ""
        try:
            code = response.json().get("error", {}).get("message", "")
        except ValueError:
            pass

        if code == "OPERATION_NOT_ALLOWED":
            line(FAIL, "Email/Password sign-in is OFF.")
            line(" ", "Firebase Console -> Authentication -> Sign-in method -> Email/Password -> Enable")
            return 1
        if code in {"EMAIL_NOT_FOUND", "INVALID_PASSWORD", "INVALID_LOGIN_CREDENTIALS"}:
            line(OK, "Email/Password sign-in is enabled.")
        elif code:
            line(" ", f"Note: the sign-in test returned {code}")
    except requests.RequestException:
        line(FAIL, "Can't reach Firebase Authentication. Check your internet connection.")
        return 1

    print("\nAll good! You can now run: python app.py\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
