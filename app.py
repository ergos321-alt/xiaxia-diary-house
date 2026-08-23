from __future__ import annotations

import os
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from auth import csrf_protect, csrf_token, password_matches, web_login_required
from database import Database
from diary import api, web


def _required(name: str, *, minimum: int = 1) -> str:
    value = os.environ.get(name, "")
    if len(value) < minimum:
        raise RuntimeError(f"{name} is required and must contain at least {minimum} characters")
    return value


def _safe_next(value: str | None) -> str:
    if not value:
        return url_for("diary.diary_home")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/"):
        return url_for("diary.diary_home")
    return value


def create_app(*, repository: Any | None = None, test_config: dict[str, Any] | None = None) -> Flask:
    load_dotenv()
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=_required("FLASK_SECRET_KEY", minimum=32),
        WEB_PASSWORD=_required("WEB_PASSWORD", minimum=12),
        DIARY_API_TOKEN=_required("DIARY_API_TOKEN", minimum=32),
        APP_TIMEZONE=os.environ.get("APP_TIMEZONE", "Asia/Shanghai"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    repo = repository or Database(_required("DATABASE_URL"))
    app.extensions["diary_repository"] = repo
    app.jinja_env.globals["csrf_token"] = csrf_token

    app.register_blueprint(web)
    app.register_blueprint(api)

    @app.after_request
    def add_security_headers(response: Any) -> Any:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        if request.path != "/healthz":
            response.headers["Cache-Control"] = "no-store, private"
        return response

    @app.get("/")
    def index() -> Any:
        return redirect(url_for("diary.diary_home"))

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Any:
        if request.method == "POST":
            supplied_csrf = request.form.get("csrf_token", "")
            expected_csrf = str(session.get("csrf_token", ""))
            import hmac
            if not supplied_csrf or not expected_csrf or not hmac.compare_digest(supplied_csrf, expected_csrf):
                return "Invalid or expired form token.", 400
            if password_matches(request.form.get("password", "")):
                session.clear()
                session["web_authenticated"] = True
                session.permanent = True
                csrf_token()
                return redirect(_safe_next(request.form.get("next")))
            flash("口令不对，再试一次。", "error")
        return render_template("login.html", next=_safe_next(request.args.get("next")))

    @app.post("/logout")
    @web_login_required
    @csrf_protect
    def logout() -> Any:
        session.clear()
        return redirect(url_for("login"))

    @app.get("/healthz")
    def healthz() -> Any:
        try:
            healthy = bool(repo.healthcheck())
        except Exception:
            healthy = False
        return jsonify({"status": "ok" if healthy else "unavailable"}), 200 if healthy else 503

    @app.errorhandler(413)
    def too_large(_: Any) -> Any:
        if request.path.startswith("/api/"):
            return jsonify({"error": "payload_too_large", "message": "Request body is too large."}), 413
        return render_template("error.html", message="提交的内容太大了。"), 413

    @app.errorhandler(500)
    def server_error(_: Any) -> Any:
        if request.path.startswith("/api/"):
            return jsonify({"error": "server_error", "message": "The request could not be completed."}), 500
        return render_template("error.html", message="家里暂时出了点小问题，请稍后再试。"), 500

    return app
