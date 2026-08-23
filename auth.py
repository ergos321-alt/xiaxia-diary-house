from __future__ import annotations

import hmac
import secrets
from functools import wraps
from typing import Any, Callable, TypeVar, cast

from flask import current_app, jsonify, redirect, request, session, url_for

F = TypeVar("F", bound=Callable[..., Any])


def web_login_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if not session.get("web_authenticated"):
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return cast(F, wrapped)


def api_token_required(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        header = request.headers.get("Authorization", "")
        scheme, _, supplied = header.partition(" ")
        expected = current_app.config["DIARY_API_TOKEN"]
        if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied, expected):
            return jsonify({"error": "unauthorized", "message": "A valid Bearer token is required."}), 401
        return view(*args, **kwargs)

    return cast(F, wrapped)


def password_matches(supplied: str) -> bool:
    return hmac.compare_digest(supplied, current_app.config["WEB_PASSWORD"])


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return str(token)


def csrf_protect(view: F) -> F:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        supplied = request.form.get("csrf_token", "")
        expected = str(session.get("csrf_token", ""))
        if not supplied or not expected or not hmac.compare_digest(supplied, expected):
            return "Invalid or expired form token.", 400
        return view(*args, **kwargs)

    return cast(F, wrapped)

