import re
import secrets
import time
from functools import wraps
from urllib.parse import urlparse

from flask import (Blueprint, flash, g, jsonify, redirect, render_template, request,
                   session, url_for, current_app)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, utcnow

bp = Blueprint("auth", __name__)

# Hash palsu supaya waktu respons sama untuk username yang tidak ada.
_DUMMY_HASH = generate_password_hash("tidak-dipakai")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD = 8


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Silakan login terlebih dahulu."), 401
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*a, **kw)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Silakan login terlebih dahulu."), 401
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        if g.user["role"] != "admin":
            if request.path.startswith("/api/"):
                return jsonify(error="Hanya admin yang boleh melakukan ini."), 403
            from .views import render_error
            return render_error(403, "Hanya admin yang boleh membuka halaman ini.")
        return view(*a, **kw)
    return wrapped


def validate_password(pw: str):
    if not isinstance(pw, str) or len(pw) < MIN_PASSWORD:
        return f"Password minimal {MIN_PASSWORD} karakter."
    if len(pw) > 128:
        return "Password terlalu panjang."
    return None


def _safe_next(target):
    if not target:
        return url_for("views.translate")
    p = urlparse(target)
    if p.scheme or p.netloc or not target.startswith("/") or target.startswith("//"):
        return url_for("views.translate")
    return target


def _recent_failures(key):
    db = get_db()
    cutoff = time.time() - current_app.config["LOGIN_WINDOW_SECONDS"]
    db.execute("DELETE FROM login_attempts WHERE ts < ?", (cutoff,))
    return db.scalar("SELECT COUNT(*) FROM login_attempts WHERE key = ?", (key,))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("views.translate"))
    nxt = request.values.get("next", "")
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        key = f"{request.remote_addr}|{username.lower()}"
        db = get_db()
        if _recent_failures(key) >= current_app.config["MAX_LOGIN_FAILURES"]:
            db.commit()
            flash("Terlalu banyak percobaan gagal. Coba lagi beberapa menit lagi.", "error")
            return render_template("login.html", username=username, next=nxt), 429
        user = db.execute("SELECT * FROM users WHERE lower(username) = lower(?)", (username,)).fetchone()
        ok = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, password)
        if user and ok and user["is_active"]:
            db.execute("DELETE FROM login_attempts WHERE key = ?", (key,))
            db.execute("UPDATE users SET last_login = ? WHERE id = ?", (utcnow(), user["id"]))
            db.commit()
            session.clear()  # cegah session fixation
            session["user_id"] = user["id"]
            session["csrf"] = secrets.token_urlsafe(32)
            session.permanent = True
            return redirect(_safe_next(nxt))
        db.execute("INSERT INTO login_attempts (key, ts) VALUES (?, ?)", (key, time.time()))
        db.commit()
        flash("Username atau password salah." if not (user and ok) else "Akun dinonaktifkan.", "error")
        return render_template("login.html", username=username, next=nxt), 401
    return render_template("login.html", username="", next=nxt)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
