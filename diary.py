from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from auth import api_token_required, csrf_protect, web_login_required

web = Blueprint("diary", __name__)
api = Blueprint("diary_api", __name__, url_prefix="/api/diary")

AUTHORS = {"user", "xiaxia"}
MAX_TITLE_LENGTH = 200
MAX_CONTENT_LENGTH = 100_000


class InputError(ValueError):
    pass


def _repo() -> Any:
    return current_app.extensions["diary_repository"]


def _today() -> date:
    return datetime.now(ZoneInfo(current_app.config["APP_TIMEZONE"])).date()


def _parse_date(value: Any, *, field: str, default: date | None = None) -> date:
    if value in (None, "") and default is not None:
        return default
    if not isinstance(value, str):
        raise InputError(f"{field} must use YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"{field} must use YYYY-MM-DD format.") from exc


def _parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, AttributeError) as exc:
        raise InputError("entry_id must be a valid UUID.") from exc


def _validate_author(value: Any) -> str:
    if value not in AUTHORS:
        raise InputError("author must be either 'user' or 'xiaxia'.")
    return str(value)


def _clean_entry(data: dict[str, Any]) -> tuple[str | None, str, date]:
    raw_title = data.get("title")
    if raw_title is not None and not isinstance(raw_title, str):
        raise InputError("title must be a string or null.")
    title = raw_title.strip() if isinstance(raw_title, str) else None
    title = title or None
    if title and len(title) > MAX_TITLE_LENGTH:
        raise InputError(f"title must not exceed {MAX_TITLE_LENGTH} characters.")
    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        raise InputError("content is required.")
    content = content.strip()
    if len(content) > MAX_CONTENT_LENGTH:
        raise InputError(f"content must not exceed {MAX_CONTENT_LENGTH} characters.")
    entry_date = _parse_date(data.get("entry_date"), field="entry_date", default=_today())
    return title, content, entry_date


def _clean_reply(data: dict[str, Any]) -> str:
    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        raise InputError("content is required.")
    content = content.strip()
    if len(content) > MAX_CONTENT_LENGTH:
        raise InputError(f"content must not exceed {MAX_CONTENT_LENGTH} characters.")
    return content


def _json_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _json_body(*, allowed_fields: set[str]) -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise InputError("Request body must be a JSON object.")
    unexpected = sorted(set(data) - allowed_fields)
    if unexpected:
        raise InputError(f"Unexpected request field(s): {', '.join(unexpected)}.")
    return data


@web.get("/diary")
@web_login_required
def diary_home() -> str:
    try:
        page = max(int(request.args.get("page", "1")), 1)
    except ValueError:
        page = 1
    page_size = 30
    rows = _repo().list_entries(limit=page_size + 1, offset=(page - 1) * page_size)
    has_next = len(rows) > page_size
    entries = rows[:page_size]
    return render_template(
        "diary.html", entries=entries, page=page, has_next=has_next
    )


@web.get("/diary/new")
@web_login_required
def new_entry() -> str:
    return render_template("entry_form.html", entry=None, today=_today().isoformat())


@web.post("/diary")
@web_login_required
@csrf_protect
def create_user_entry() -> Any:
    try:
        title, content, entry_date = _clean_entry(
            {
                "title": request.form.get("title"),
                "content": request.form.get("content"),
                "entry_date": request.form.get("entry_date"),
            }
        )
    except InputError as exc:
        flash(str(exc), "error")
        return render_template(
            "entry_form.html",
            entry=request.form,
            today=request.form.get("entry_date", _today().isoformat()),
        ), 400
    entry = _repo().create_entry(author="user", title=title, content=content, entry_date=entry_date)
    flash("日记已经好好收进家里了。", "success")
    return redirect(url_for("diary.entry_detail", entry_id=entry["id"]))


@web.get("/diary/<entry_id>")
@web_login_required
def entry_detail(entry_id: str) -> Any:
    try:
        entry_uuid = _parse_uuid(entry_id)
    except InputError:
        return render_template("404.html"), 404
    entry = _repo().get_entry(entry_uuid)
    if entry is None:
        return render_template("404.html"), 404
    return render_template("entry.html", entry=entry)


@web.get("/diary/<entry_id>/edit")
@web_login_required
def edit_entry(entry_id: str) -> Any:
    try:
        entry = _repo().get_entry(_parse_uuid(entry_id))
    except InputError:
        entry = None
    if entry is None:
        return render_template("404.html"), 404
    if entry["author"] != "user":
        return render_template("403.html"), 403
    return render_template("entry_form.html", entry=entry, today=entry["entry_date"].isoformat())


@web.post("/diary/<entry_id>/edit")
@web_login_required
@csrf_protect
def update_entry(entry_id: str) -> Any:
    try:
        entry_uuid = _parse_uuid(entry_id)
        title, content, entry_date = _clean_entry(
            {
                "title": request.form.get("title"),
                "content": request.form.get("content"),
                "entry_date": request.form.get("entry_date"),
            }
        )
    except InputError as exc:
        flash(str(exc), "error")
        return redirect(url_for("diary.edit_entry", entry_id=entry_id))
    updated = _repo().update_user_entry(entry_uuid, title=title, content=content, entry_date=entry_date)
    if updated is None:
        return render_template("404.html"), 404
    flash("修改已经保存。", "success")
    return redirect(url_for("diary.entry_detail", entry_id=entry_id))


@web.post("/diary/<entry_id>/replies")
@web_login_required
@csrf_protect
def create_user_reply(entry_id: str) -> Any:
    try:
        entry_uuid = _parse_uuid(entry_id)
        content = _clean_reply({"content": request.form.get("content")})
    except InputError as exc:
        flash(str(exc), "error")
        return redirect(url_for("diary.entry_detail", entry_id=entry_id))
    reply = _repo().create_reply(entry_id=entry_uuid, author="user", content=content)
    if reply is None:
        return render_template("404.html"), 404
    flash("回复已经送到这篇日记下面。", "success")
    return redirect(url_for("diary.entry_detail", entry_id=entry_id) + "#replies")


@api.get("/recent")
@api_token_required
def api_recent() -> Any:
    try:
        limit = min(max(int(request.args.get("limit", "10")), 1), 50)
    except ValueError:
        return jsonify({"error": "invalid_request", "message": "limit must be an integer."}), 400
    author = request.args.get("author")
    if author is not None:
        try:
            author = _validate_author(author)
        except InputError as exc:
            return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    entries = _repo().list_entries(limit=limit, author=author)
    return jsonify({"entries": _json_value(entries), "count": len(entries)})


@api.get("/entries/<entry_id>")
@api_token_required
def api_entry(entry_id: str) -> Any:
    try:
        entry = _repo().get_entry(_parse_uuid(entry_id))
    except InputError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    if entry is None:
        return jsonify({"error": "not_found", "message": "Diary entry not found."}), 404
    return jsonify({"entry": _json_value(entry)})


@api.get("/by-date")
@api_token_required
def api_by_date() -> Any:
    try:
        single_date = request.args.get("date")
        start_raw = request.args.get("start_date")
        end_raw = request.args.get("end_date")
        if single_date and (start_raw or end_raw):
            raise InputError("Use date or start_date/end_date, not both.")
        if single_date:
            start_date = end_date = _parse_date(single_date, field="date")
        else:
            if not start_raw or not end_raw:
                raise InputError("Provide date, or both start_date and end_date.")
            start_date = _parse_date(start_raw, field="start_date")
            end_date = _parse_date(end_raw, field="end_date")
        if start_date > end_date:
            raise InputError("start_date must not be after end_date.")
        if (end_date - start_date).days > 366:
            raise InputError("Date range must not exceed 366 days.")
        author = request.args.get("author")
        if author is not None:
            author = _validate_author(author)
        limit = min(max(int(request.args.get("limit", "100")), 1), 200)
    except (InputError, ValueError) as exc:
        message = str(exc) if str(exc) else "limit must be an integer."
        return jsonify({"error": "invalid_request", "message": message}), 400
    entries = _repo().list_entries(
        limit=limit, author=author, start_date=start_date, end_date=end_date
    )
    return jsonify(
        {
            "entries": _json_value(entries),
            "count": len(entries),
            "range": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        }
    )


@api.post("/entries")
@api_token_required
def api_create_entry() -> Any:
    try:
        title, content, entry_date = _clean_entry(
            _json_body(allowed_fields={"title", "content", "entry_date"})
        )
    except InputError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    entry = _repo().create_entry(
        author="xiaxia", title=title, content=content, entry_date=entry_date
    )
    return jsonify({"entry": _json_value(entry)}), 201


@api.post("/entries/<entry_id>/replies")
@api_token_required
def api_create_reply(entry_id: str) -> Any:
    try:
        entry_uuid = _parse_uuid(entry_id)
        content = _clean_reply(_json_body(allowed_fields={"content"}))
    except InputError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    reply = _repo().create_reply(entry_id=entry_uuid, author="xiaxia", content=content)
    if reply is None:
        return jsonify({"error": "not_found", "message": "Diary entry not found."}), 404
    return jsonify({"reply": _json_value(reply)}), 201


@api.get("/context")
@api_token_required
def api_context() -> Any:
    try:
        per_author = min(max(int(request.args.get("per_author", "5")), 1), 10)
        reply_limit = min(max(int(request.args.get("reply_limit", "10")), 1), 20)
    except ValueError:
        return jsonify({"error": "invalid_request", "message": "Limits must be integers."}), 400
    user_entries = _repo().list_entries(limit=per_author, author="user")
    xiaxia_entries = _repo().list_entries(limit=per_author, author="xiaxia")
    replies = _repo().list_recent_replies(limit=reply_limit)
    return jsonify(
        {
            "generated_at": datetime.now(ZoneInfo(current_app.config["APP_TIMEZONE"])).isoformat(),
            "timezone": current_app.config["APP_TIMEZONE"],
            "recent_user_entries": _json_value(user_entries),
            "recent_xiaxia_entries": _json_value(xiaxia_entries),
            "recent_replies": _json_value(replies),
        }
    )
