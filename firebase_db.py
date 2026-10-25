"""
firebase_db.py
--------------
Lahat ng Firebase (Authentication + Cloud Firestore) na kailangan ng app.

Kailangan ng service account key (default: serviceAccountKey.json) at ng
Web API key ng Firebase project (FIREBASE_API_KEY sa .env).
"""

import os
import time
from datetime import timedelta
from pathlib import Path

import firebase_admin
import requests
from dotenv import load_dotenv
from firebase_admin import auth, credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

load_dotenv()

CREDENTIALS_FILE = os.getenv("FIREBASE_CREDENTIALS", "serviceAccountKey.json")
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "")

SIGN_IN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
SESSION_DAYS = 5
VALID_ROLES = {"admin", "user"}

_ready = False
_error = ""
_last_attempt = 0.0


class FirebaseSetupError(RuntimeError):
    """Kulang ang settings o wala ang service account key."""


class InvalidLogin(Exception):
    """Mali ang username/email o password."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def init_firebase(force=False):
    """I-initialize ang Firebase Admin SDK at i-test ang Firestore.

    Bumabalik agad kung ready na, at may 15-second cooldown bago umulit
    kapag nabigo (para hindi mabagal ang bawat request).
    """
    global _ready, _error, _last_attempt

    now = time.monotonic()
    if not force:
        if _ready:
            return True
        if now - _last_attempt < 15:
            return False
    _last_attempt = now

    try:
        if not Path(CREDENTIALS_FILE).exists():
            raise FirebaseSetupError(
                f"Service account key not found ({CREDENTIALS_FILE}). "
                "Download it from Firebase Console -> Project settings -> Service accounts."
            )
        if not FIREBASE_API_KEY:
            raise FirebaseSetupError(
                "FIREBASE_API_KEY is missing from .env. Get it from "
                "Firebase Console -> Project settings -> General -> Web API Key."
            )

        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(credentials.Certificate(CREDENTIALS_FILE))

        # Subukang basahin ang Firestore para malaman kung naka-enable ito.
        get_db().collection("users").limit(1).get()

        _ready = True
        _error = ""
        print("[Firebase] Connection to Authentication and Firestore is OK.")
    except Exception as error:  # noqa: BLE001 - gusto nating ipakita lahat ng error sa page
        _ready = False
        _error = str(error)
        print("[Firebase] Not set up yet:", error)
    return _ready


def is_ready():
    return _ready


def get_error():
    return _error


def get_db():
    return firestore.client()


# --- Firestore: user profiles -------------------------------------------------


def find_profile_by_username(username):
    """Hanapin ang profile gamit ang username (case-insensitive). None kung wala."""
    snapshots = (
        get_db()
        .collection("users")
        .where(filter=FieldFilter("username_lower", "==", username.strip().lower()))
        .limit(1)
        .get()
    )
    for snapshot in snapshots:
        profile = snapshot.to_dict() or {}
        profile["uid"] = snapshot.id
        return profile
    return None


def get_profile(uid):
    snapshot = get_db().collection("users").document(uid).get()
    if not snapshot.exists:
        return None
    profile = snapshot.to_dict() or {}
    profile["uid"] = snapshot.id
    profile.setdefault("role", "user")
    return profile


def list_profiles():
    """Lahat ng user profiles, pinakabago muna."""
    profiles = []
    for snapshot in get_db().collection("users").stream():
        profile = snapshot.to_dict() or {}
        profile["uid"] = snapshot.id
        profile.setdefault("role", "user")
        profiles.append(profile)

    def sort_key(profile):
        created = profile.get("created_at")
        return created.timestamp() if hasattr(created, "timestamp") else 0

    profiles.sort(key=sort_key, reverse=True)
    return profiles


def count_admins():
    return sum(1 for profile in list_profiles() if profile.get("role") == "admin")


def set_role(uid, role):
    """Palitan ang role ng user ('admin' o 'user')."""
    if role not in VALID_ROLES:
        raise ValueError(f"Hindi valid na role: {role}")
    get_db().collection("users").document(uid).update({"role": role})


def delete_profile(uid):
    get_db().collection("users").document(uid).delete()


def update_profile(uid, fields):
    """I-update ang mga field ng profile sa Firestore."""
    if fields:
        get_db().collection("users").document(uid).update(fields)


def update_auth_user(uid, **fields):
    """I-update ang Firebase Authentication record (hal. password, display_name)."""
    return auth.update_user(uid, **fields)


def create_profile(uid, username, full_name, email, role="user"):
    if role not in VALID_ROLES:
        raise ValueError(f"Hindi valid na role: {role}")
    get_db().collection("users").document(uid).set(
        {
            "username": username,
            "username_lower": username.lower(),
            "full_name": full_name,
            "email": email,
            "email_lower": email.lower(),
            "role": role,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )


# --- Firebase Authentication --------------------------------------------------


def create_auth_user(email, password, full_name):
    """Gumawa ng account sa Firebase Authentication. Returns ang user record."""
    return auth.create_user(email=email, password=password, display_name=full_name)


def delete_auth_user(uid):
    """Rollback kapag nabigo ang pag-save ng profile sa Firestore."""
    auth.delete_user(uid)


def sign_in_with_password(email, password):
    """Mag-login sa Firebase Auth gamit ang REST API. Returns idToken at localId."""
    try:
        response = requests.post(
            SIGN_IN_URL,
            params={"key": FIREBASE_API_KEY},
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=15,
        )
    except requests.RequestException:
        raise InvalidLogin("Can't reach Firebase. Check your internet connection.") from None

    if response.ok:
        return response.json()

    code = ""
    try:
        code = response.json().get("error", {}).get("message", "")
    except ValueError:
        pass
    raise InvalidLogin(_friendly_sign_in_error(code))


def _friendly_sign_in_error(code):
    if code in {"EMAIL_NOT_FOUND", "INVALID_PASSWORD", "INVALID_LOGIN_CREDENTIALS"}:
        return "Incorrect username/email or password. Try again."
    if code == "USER_DISABLED":
        return "This account has been disabled. Contact an admin."
    if code == "TOO_MANY_ATTEMPTS_TRY_LATER":
        return "Too many attempts. Please wait a few minutes."
    if code:
        return f"Can't log in ({code})."
    return "Can't log in. Please try again."


def create_session_cookie(id_token):
    """Gawing secure session cookie ang idToken (server-side session)."""
    return auth.create_session_cookie(id_token, expires_in=timedelta(days=SESSION_DAYS))


def verify_session_cookie(session_cookie):
    """I-verify ang session cookie. Nag-e-error kapag invalid o revoked."""
    return auth.verify_session_cookie(session_cookie, check_revoked=True)


def revoke_sessions(uid):
    """Puwersahing mag-logout sa lahat ng device (revoke refresh tokens)."""
    auth.revoke_refresh_tokens(uid)
