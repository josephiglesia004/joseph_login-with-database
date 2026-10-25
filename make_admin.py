"""
make_admin.py
-------------
Gawing admin ang isang existing account.

Gamit:
    python make_admin.py <username-o-email>

Halimbawa:
    python make_admin.py joseph
    python make_admin.py joseph@email.com
"""

import sys

import firebase_db


def main():
    if len(sys.argv) != 2:
        print("Usage: python make_admin.py <username-or-email>")
        return 1

    target = sys.argv[1].strip().lower()
    firebase_db.init_firebase(force=True)

    if not firebase_db.is_ready():
        print("Can't connect to Firebase:", firebase_db.get_error())
        return 1

    match = None
    for profile in firebase_db.list_profiles():
        if (
            (profile.get("username_lower") or "").lower() == target
            or (profile.get("email") or "").lower() == target
        ):
            match = profile
            break

    if match is None:
        print(f"No account found for “{target}”.")
        return 1

    if match.get("role") == "admin":
        print(f"{match.get('username')} ({match.get('email')}) is already an admin.")
        return 0

    firebase_db.set_role(match["uid"], "admin")
    print(f"{match.get('username')} ({match.get('email')}) is now an admin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
