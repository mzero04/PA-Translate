"""Translate Form — aplikasi web penerjemah teks instruksi kerja (Inggris -> Indonesia)."""
import hmac
import os
import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, g, jsonify, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db


def _load_secret_key(instance_path: Path, serverless: bool) -> str:
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    if serverless:
        raise RuntimeError("SECRET_KEY wajib diatur (Environment Variables) saat memakai DATABASE_URL/Vercel.")
    key_file = instance_path / "secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
        try:
            key_file.chmod(0o600)
        except OSError:
            pass
    return key_file.read_text().strip()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    instance = Path(app.instance_path)
    on_vercel = bool(os.environ.get("VERCEL"))
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if test_config and "DATABASE_URL" in test_config:
        database_url = test_config["DATABASE_URL"]
    serverless = on_vercel or bool(database_url)
    if on_vercel and not database_url:
        raise RuntimeError("DATABASE_URL belum diatur. Vercel tidak punya penyimpanan permanen untuk SQLite; "
                           "sambungkan database Postgres (mis. Neon) dan isi DATABASE_URL.")
    if not serverless:
        instance.mkdir(parents=True, exist_ok=True)

    app.config.update(
        SECRET_KEY=_load_secret_key(instance, serverless),
        DATABASE=str(instance / "app.sqlite3"),
        DATABASE_URL=database_url,
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1" or on_vercel,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        JSON_AS_ASCII=False,
        MAX_LOGIN_FAILURES=5,
        LOGIN_WINDOW_SECONDS=600,
    )
    if test_config:
        app.config.update(test_config)

    if on_vercel or os.environ.get("TRUST_PROXY") == "1":
        # Di belakang proxy: pakai IP asli klien (untuk batas login) dan skema https.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)

    from . import api, auth, views

    app.register_blueprint(auth.bp)
    app.register_blueprint(views.bp)
    app.register_blueprint(api.bp)

    @app.before_request
    def _csrf_and_user():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        g.user = None
        uid = session.get("user_id")
        if uid is not None:
            row = db.get_db().execute(
                "SELECT * FROM users WHERE id = ? AND is_active = 1", (uid,)
            ).fetchone()
            if row is None:
                session.pop("user_id", None)
            else:
                g.user = row
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
            if not hmac.compare_digest(sent, session["csrf"]):
                if request.path.startswith("/api/"):
                    return jsonify(error="Sesi tidak valid, muat ulang halaman."), 400
                abort(400)

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        if request.path.startswith("/api/") or g.get("user"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(404)
    def _404(e):
        if request.path.startswith("/api/"):
            return jsonify(error="Tidak ditemukan."), 404
        return views.render_error(404, "Halaman tidak ditemukan.")

    @app.errorhandler(400)
    def _400(e):
        return views.render_error(400, "Permintaan tidak valid.")

    @app.errorhandler(413)
    def _413(e):
        if request.path.startswith("/api/"):
            return jsonify(error="Data terlalu besar (maks 5 MB)."), 413
        return views.render_error(413, "Data terlalu besar.")

    @app.cli.command("init-db")
    def _init_db_cmd():
        """Buat tabel, kamus awal, dan akun admin pertama bila belum ada."""
        db.ensure_ready(announce=True)

    @app.cli.command("create-user")
    def _create_user_cmd():
        """Buat pengguna baru lewat command line."""
        import click
        from werkzeug.security import generate_password_hash

        username = click.prompt("Username")
        full_name = click.prompt("Nama lengkap", default=username)
        role = click.prompt("Role", type=click.Choice(["admin", "user"]), default="user")
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        db.ensure_ready()
        db.get_db().execute(
            "INSERT INTO users (username, full_name, password_hash, role) VALUES (?,?,?,?)",
            (username, full_name, generate_password_hash(password), role),
        )
        db.get_db().commit()
        click.echo("Pengguna dibuat.")

    with app.app_context():
        db.ensure_ready(announce=not app.testing)

    return app
