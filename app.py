"""
app.py
------
Login system gamit ang Flask + Firebase (Authentication at Cloud Firestore).

Patakbuhin:
    python app.py   ->   http://127.0.0.1:5000

Bago ito gumana, tingnan ang README.md para sa Firebase setup
(serviceAccountKey.json at FIREBASE_API_KEY sa .env).
"""

import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from firebase_admin import auth
from google.api_core.exceptions import GoogleAPICallError

import firebase_db

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "palitan-ito-ng-random-secret-key")
app.permanent_session_lifetime = timedelta(days=firebase_db.SESSION_DAYS)

# Kalagayan ng Firebase connection (para sa friendly na error sa page).
firebase_db.init_firebase(force=True)
firebase_ready = firebase_db.is_ready()
firebase_error = firebase_db.get_error()


@app.before_request
def retry_firebase_connection():
    """Kung hindi pa naka-setup noong start, subukan ulit paminsan-minsan."""
    global firebase_ready, firebase_error
    if not firebase_ready:
        firebase_db.init_firebase()
        firebase_ready = firebase_db.is_ready()
        firebase_error = firebase_db.get_error()


@app.context_processor
def inject_globals():
    return {
        "firebase_ready": firebase_ready,
        "firebase_error": firebase_error,
        "current_year": datetime.now().year,
        "is_admin": getattr(g, "is_admin", False),
        "current_uid": getattr(g, "uid", None),
    }


def login_required(view):
    """I-redirect sa login page kung walang valid na Firebase session."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        cookie = session.get("session_cookie")
        claims = None
        if cookie:
            try:
                claims = firebase_db.verify_session_cookie(cookie)
            except Exception:  # expired, revoked, o hindi ma-verify
                claims = None

        if not claims:
            session.clear()
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        g.uid = claims["uid"]
        g.claims = claims
        g.profile = firebase_db.get_profile(g.uid) or {}
        g.profile.setdefault("role", "user")
        g.is_admin = g.profile.get("role") == "admin"
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    """Admin lang ang puwedeng pumasok. I-redirect ang normal users sa dashboard."""

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.is_admin:
            flash("Only admins can access that page.", "warning")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped


@app.route("/")
@login_required
def dashboard():
    """Home page ng mga naka-login na user (user o admin)."""
    profile = g.profile

    last_login = None
    if g.claims.get("auth_time"):
        last_login = datetime.fromtimestamp(g.claims["auth_time"])

    created = profile.get("created_at")
    days_active = None
    if created:
        now = datetime.now(timezone.utc) if getattr(created, "tzinfo", None) else datetime.now()
        days_active = max(1, (now - created).days + 1)

    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    user = {
        "uid": g.uid,
        "username": profile.get("username") or session.get("username", "—"),
        "full_name": profile.get("full_name") or session.get("full_name", "—"),
        "email": profile.get("email") or g.claims.get("email", "—"),
        "role": profile.get("role", "user"),
        "created_at": created,
        "last_login": last_login,
    }
    return render_template(
        "dashboard.html",
        user=user,
        greeting=greeting,
        days_active=days_active,
        session_days=firebase_db.SESSION_DAYS,
    )


@app.route("/settings")
@login_required
def settings():
    """Account settings page: profile at password."""
    return render_template("settings.html", profile=g.profile)


@app.route("/settings/profile", methods=["POST"])
@login_required
def update_profile():
    """I-update ang full name at username."""
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()

    errors = []
    if len(full_name) < 2:
        errors.append("Enter your full name.")
    if len(username) < 3:
        errors.append("Username must be at least 3 characters.")
    if not username.replace("_", "").replace(".", "").isalnum():
        errors.append(
            "Username may only contain letters, numbers, underscores (_), and dots (.)."
        )

    if not errors:
        existing = firebase_db.find_profile_by_username(username)
        if existing and existing["uid"] != g.uid:
            errors.append("That username is already taken.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return redirect(url_for("settings"))

    try:
        firebase_db.update_profile(
            g.uid,
            {
                "username": username,
                "username_lower": username.lower(),
                "full_name": full_name,
            },
        )
        firebase_db.update_auth_user(g.uid, display_name=full_name)
    except GoogleAPICallError as error:
        flash(f"Firebase error: {error}", "danger")
        return redirect(url_for("settings"))

    session["username"] = username
    session["full_name"] = full_name
    flash("Your profile has been updated.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/password", methods=["POST"])
@login_required
def update_password():
    """Palitan ang password — kailangang i-verify muna ang current password."""
    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    errors = []
    if not current:
        errors.append("Enter your current password.")
    if len(new) < 8:
        errors.append("New password must be at least 8 characters.")
    if new != confirm:
        errors.append("New password and confirmation don't match.")
    if new and new == current:
        errors.append("New password must be different from your current password.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return redirect(url_for("settings"))

    email = g.profile.get("email") or g.claims.get("email")
    if not email:
        flash("Couldn't find the email for your account.", "danger")
        return redirect(url_for("settings"))

    try:
        firebase_db.sign_in_with_password(email, current)
    except firebase_db.InvalidLogin:
        flash("Your current password is incorrect.", "danger")
        return redirect(url_for("settings"))

    try:
        firebase_db.update_auth_user(g.uid, password=new)
    except GoogleAPICallError as error:
        flash(f"Firebase error: {error}", "danger")
        return redirect(url_for("settings"))

    # Kapag pinalitan ang password, ini-invalidate ng Firebase ang lumang
    # session. Gumawa agad ng bagong session para hindi ma-logout ang user.
    try:
        tokens = firebase_db.sign_in_with_password(email, new)
        session["session_cookie"] = firebase_db.create_session_cookie(tokens["idToken"])
        session["username"] = g.profile.get("username", session.get("username", ""))
        session["full_name"] = g.profile.get("full_name", session.get("full_name", ""))
        session.permanent = True
    except (firebase_db.InvalidLogin, GoogleAPICallError):
        session.clear()
        flash(
            "Your password has been changed. Please log in again with your new password.",
            "success",
        )
        return redirect(url_for("login"))

    flash("Your password has been changed. Use it on your next login.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/logout-all", methods=["POST"])
@login_required
def logout_all():
    """I-logout sa lahat ng device (revoke lahat ng refresh tokens)."""
    try:
        firebase_db.revoke_sessions(g.uid)
    except Exception:  # ok lang kahit hindi ma-revoke
        pass
    session.clear()
    flash("You've been logged out on all devices. Log in again to continue.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("session_cookie"):
        return redirect(url_for("dashboard"))

    identifier = ""

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        if not firebase_ready:
            flash("Firebase isn't set up yet. See README.md.", "warning")
            return render_template("login.html", identifier=identifier), 503

        if not identifier or not password:
            flash("Enter your username/email and password.", "danger")
            return render_template("login.html", identifier=identifier), 400

        try:
            if "@" in identifier:
                email = identifier.lower()
            else:
                profile = firebase_db.find_profile_by_username(identifier)
                if profile is None:
                    flash("Incorrect username/email or password. Try again.", "danger")
                    return render_template("login.html", identifier=identifier), 401
                email = profile["email"]

            tokens = firebase_db.sign_in_with_password(email, password)
            session_cookie = firebase_db.create_session_cookie(tokens["idToken"])
            profile = firebase_db.get_profile(tokens["localId"])
        except firebase_db.InvalidLogin as error:
            flash(error.message, "danger")
            return render_template("login.html", identifier=identifier), 401
        except GoogleAPICallError as error:
            flash(f"Firebase error: {error}", "danger")
            return render_template("login.html", identifier=identifier), 500

        session.clear()
        session.permanent = True
        session["session_cookie"] = session_cookie
        session["username"] = (profile or {}).get("username", identifier)
        session["full_name"] = (profile or {}).get("full_name", "")

        flash(f"Welcome, {session['full_name'] or session['username']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html", identifier=identifier)


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("session_cookie"):
        return redirect(url_for("dashboard"))

    form = {"username": "", "full_name": "", "email": ""}

    if request.method == "POST":
        form["username"] = request.form.get("username", "").strip()
        form["full_name"] = request.form.get("full_name", "").strip()
        form["email"] = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not firebase_ready:
            flash("Firebase isn't set up yet. See README.md.", "warning")
            return render_template("register.html", form=form), 503

        errors = []
        if len(form["username"]) < 3:
            errors.append("Username must be at least 3 characters.")
        if not form["username"].replace("_", "").replace(".", "").isalnum():
            errors.append(
                "Username may only contain letters, numbers, underscores (_), and dots (.)."
            )
        if len(form["full_name"]) < 2:
            errors.append("Enter your full name.")
        if "@" not in form["email"] or "." not in form["email"].split("@")[-1]:
            errors.append("That email doesn't look valid.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Password and confirmation don't match.")

        if not errors:
            try:
                if firebase_db.find_profile_by_username(form["username"]):
                    errors.append("That username is already taken.")
                else:
                    # Ang unang account (walang admin pa) ay magiging admin.
                    role = "admin" if firebase_db.count_admins() == 0 else "user"
                    auth_user = firebase_db.create_auth_user(
                        form["email"], password, form["full_name"]
                    )
                    try:
                        firebase_db.create_profile(
                            auth_user.uid,
                            form["username"],
                            form["full_name"],
                            form["email"],
                            role=role,
                        )
                    except Exception:
                        # Huwag mag-iwan ng account na walang profile.
                        firebase_db.delete_auth_user(auth_user.uid)
                        raise

                    message = "Registration successful! You can log in now."
                    if role == "admin":
                        message += " You're the first account, so you're an admin."
                    flash(message, "success")
                    return redirect(url_for("login"))
            except auth.EmailAlreadyExistsError:
                errors.append("An account with that email already exists.")
            except GoogleAPICallError as error:
                errors.append(f"Firebase error: {error}")
            except Exception as error:  # hal. nawalan ng internet habang nag-se-save
                errors.append(f"Something went wrong: {error}")

        for message in errors:
            flash(message, "danger")

    return render_template("register.html", form=form)


@app.route("/admin")
@admin_required
def admin_users():
    """Admin dashboard: statistik at listahan ng lahat ng account."""
    profiles = firebase_db.list_profiles()
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    users = []
    new_users = 0
    for profile in profiles:
        created = profile.get("created_at")
        is_new = False
        try:
            is_new = bool(created) and created >= week_ago
        except TypeError:
            is_new = False
        if is_new:
            new_users += 1

        display_name = profile.get("full_name") or profile.get("username") or "?"
        users.append(
            {
                "uid": profile["uid"],
                "username": profile.get("username", "—"),
                "full_name": profile.get("full_name", "—"),
                "email": profile.get("email", "—"),
                "role": profile.get("role", "user"),
                "created_at": created,
                "initial": display_name[:1].upper(),
            }
        )

    stats = {
        "total": len(users),
        "admins": sum(1 for user in users if user["role"] == "admin"),
        "new": new_users,
    }
    return render_template("admin.html", users=users, stats=stats)


@app.route("/admin/users/<uid>/role", methods=["POST"])
@admin_required
def admin_set_role(uid):
    """I-promote o i-demote ang isang user."""
    action = request.form.get("action", "")
    if action not in {"promote", "demote"}:
        flash("Invalid action.", "danger")
        return redirect(url_for("admin_users"))

    if uid == g.uid:
        flash("You can't change your own role.", "warning")
        return redirect(url_for("admin_users"))

    profile = firebase_db.get_profile(uid)
    if profile is None:
        flash("That user doesn't exist.", "danger")
        return redirect(url_for("admin_users"))

    role = "admin" if action == "promote" else "user"
    if (
        role == "user"
        and profile.get("role") == "admin"
        and firebase_db.count_admins() <= 1
    ):
        flash("The last admin can't be demoted.", "warning")
        return redirect(url_for("admin_users"))

    try:
        firebase_db.set_role(uid, role)
    except GoogleAPICallError as error:
        flash(f"Firebase error: {error}", "danger")
        return redirect(url_for("admin_users"))

    flash(
        f"{profile.get('username', uid)} is now {'an admin' if role == 'admin' else 'a user'}.",
        "success",
    )
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<uid>/delete", methods=["POST"])
@admin_required
def admin_delete_user(uid):
    """Burahin ang account (Firebase Auth + Firestore profile)."""
    if uid == g.uid:
        flash("You can't delete your own account here.", "warning")
        return redirect(url_for("admin_users"))

    profile = firebase_db.get_profile(uid)
    if profile is None:
        flash("That user doesn't exist.", "danger")
        return redirect(url_for("admin_users"))

    if profile.get("role") == "admin" and firebase_db.count_admins() <= 1:
        flash("The last admin can't be deleted.", "warning")
        return redirect(url_for("admin_users"))

    try:
        try:
            firebase_db.delete_auth_user(uid)
        except auth.UserNotFoundError:
            pass  # wala na sa Authentication, linisin na lang ang profile
        firebase_db.delete_profile(uid)
    except GoogleAPICallError as error:
        flash(f"Firebase error: {error}", "danger")
        return redirect(url_for("admin_users"))

    flash(f"{profile.get('username', uid)}'s account has been deleted.", "success")
    return redirect(url_for("admin_users"))


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    try:
        firebase_db.revoke_sessions(g.uid)
    except Exception:  # ok lang kahit hindi ma-revoke
        pass
    session.clear()
    flash("You've been logged out. Take care!", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
