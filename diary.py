from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from auth import api_token_required, csrf_protect, web_login_required

web = Blueprint("diary", __name__)
api = Blueprint("diary_api", __name__, url_prefix="/api/diary")

AUTHORS = {"user", "xiaxia"}
MARK_TYPES = {"leaf"}
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


def _clean_mark(value: Any) -> str:
    if value not in MARK_TYPES:
        raise InputError("mark_type must be 'leaf'.")
    return str(value)


def _month_range(value: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(f"{value}-01")
    except (TypeError, ValueError) as exc:
        raise InputError("month must use YYYY-MM format.") from exc
    last_day = calendar.monthrange(start.year, start.month)[1]
    return start, date(start.year, start.month, last_day)


def _same_day_last_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def _calendar_context(month_value: str) -> dict[str, Any]:
    start_date, end_date = _month_range(month_value)
    activity = {
        row["entry_date"]: row
        for row in _repo().list_calendar_days(
            start_date=start_date, end_date=end_date
        )
    }
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(
        start_date.year, start_date.month
    ):
        weeks.append(
            [
                {
                    "date": day,
                    "in_month": day.month == start_date.month,
                    "has_user": bool(activity.get(day, {}).get("has_user")),
                    "has_xiaxia": bool(activity.get(day, {}).get("has_xiaxia")),
                    "entry_count": int(activity.get(day, {}).get("entry_count", 0)),
                }
                for day in week
            ]
        )
    return {
        "calendar_month": start_date,
        "calendar_month_value": start_date.strftime("%Y-%m"),
        "calendar_weeks": weeks,
        "previous_month": (start_date - timedelta(days=1)).strftime("%Y-%m"),
        "next_month": (end_date + timedelta(days=1)).strftime("%Y-%m"),
    }


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
    selected_author = request.args.get("author") or None
    try:
        page = max(int(request.args.get("page", "1")), 1)
    except ValueError:
        page = 1
    try:
        if selected_author is not None:
            selected_author = _validate_author(selected_author)
    except InputError as exc:
        return render_template("error.html", message=str(exc)), 400
    page_size = 30
    rows = _repo().list_entries(
        limit=page_size + 1,
        offset=(page - 1) * page_size,
        author=selected_author,
    )
    has_next = len(rows) > page_size
    entries = rows[:page_size]
    last_year_day = _same_day_last_year(_today())
    has_on_this_day = bool(
        _repo().list_entries(
            limit=1, start_date=last_year_day, end_date=last_year_day
        )
    )
    return render_template(
        "diary.html",
        entries=entries,
        page=page,
        has_next=has_next,
        selected_author=selected_author,
        has_on_this_day=has_on_this_day,
    )


@web.get("/diary/archive")
@web_login_required
def diary_archive() -> Any:
    month = request.args.get("month")
    selected_date = request.args.get("date")
    if month and selected_date:
        return render_template("error.html", message="月份和日期请只选择一种。"), 400
    entries: list[dict[str, Any]] | None = None
    heading = "翻旧日记"
    months = _repo().list_months()
    try:
        if month:
            start_date, end_date = _month_range(month)
            entries = _repo().list_entries(
                limit=500, start_date=start_date, end_date=end_date
            )
            heading = f"{start_date.year} 年 {start_date.month} 月"
        elif selected_date:
            day = _parse_date(selected_date, field="date")
            entries = _repo().list_entries(limit=200, start_date=day, end_date=day)
            heading = day.strftime("%Y 年 %m 月 %d 日")
        if month:
            calendar_month_value = month
        elif selected_date:
            calendar_month_value = day.strftime("%Y-%m")
        elif months:
            calendar_month_value = months[0]["month"]
        else:
            calendar_month_value = _today().strftime("%Y-%m")
        calendar_context = _calendar_context(calendar_month_value)
    except InputError as exc:
        return render_template("error.html", message=str(exc)), 400
    last_year_day = _same_day_last_year(_today())
    has_on_this_day = bool(
        _repo().list_entries(
            limit=1, start_date=last_year_day, end_date=last_year_day
        )
    )
    return render_template(
        "archive.html",
        months=months,
        entries=entries,
        heading=heading,
        selected_month=month,
        selected_date=selected_date,
        mode="archive",
        has_on_this_day=has_on_this_day,
        **calendar_context,
    )


@web.get("/diary/on-this-day")
@web_login_required
def on_this_day() -> str:
    target = _same_day_last_year(_today())
    entries = _repo().list_entries(limit=200, start_date=target, end_date=target)
    calendar_context = _calendar_context(target.strftime("%Y-%m"))
    return render_template(
        "archive.html",
        months=_repo().list_months(),
        entries=entries,
        heading=f"去年的今天 · {target.strftime('%Y 年 %m 月 %d 日')}",
        selected_month=None,
        selected_date=target.isoformat(),
        mode="on-this-day",
        has_on_this_day=bool(entries),
        **calendar_context,
    )


@web.get("/diary/random")
@web_login_required
def random_entry() -> Any:
    entry = _repo().random_entry()
    if entry is None:
        flash("还没有可以翻到的旧日记。", "error")
        return redirect(url_for("diary.diary_archive"))
    return redirect(url_for("diary.entry_detail", entry_id=entry["id"]))


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
    same_day_entries = [
        item
        for item in _repo().list_entries(
            limit=200, start_date=entry["entry_date"], end_date=entry["entry_date"]
        )
        if item["id"] != entry["id"] and item["author"] != entry["author"]
    ]
    return render_template(
        "entry.html", entry=entry, same_day_entries=same_day_entries
    )


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
    flash("这句话已经留在日记页边。", "success")
    return redirect(url_for("diary.entry_detail", entry_id=entry_id) + "#replies")


@web.post("/diary/<entry_id>/marks")
@web_login_required
@csrf_protect
def add_user_mark(entry_id: str) -> Any:
    try:
        entry_uuid = _parse_uuid(entry_id)
    except InputError:
        return render_template("404.html"), 404
    mark, created = _repo().add_mark(
        entry_id=entry_uuid, author="user", mark_type="leaf"
    )
    if mark is None:
        return render_template("404.html"), 404
    flash("留下了一片小叶子。" if created else "这片叶子已经在这里了。", "success")
    return redirect(url_for("diary.entry_detail", entry_id=entry_id) + "#marks")


@web.post("/diary/<entry_id>/marks/remove")
@web_login_required
@csrf_protect
def remove_user_mark(entry_id: str) -> Any:
    try:
        entry_uuid = _parse_uuid(entry_id)
    except InputError:
        return render_template("404.html"), 404
    if _repo().get_entry(entry_uuid) is None:
        return render_template("404.html"), 404
    removed = _repo().remove_mark(
        entry_id=entry_uuid, author="user", mark_type="leaf"
    )
    flash("收回了这片小叶子。" if removed else "这里没有需要收回的叶子。", "success")
    return redirect(url_for("diary.entry_detail", entry_id=entry_id) + "#marks")


@web.get("/diary/<entry_id>/delete")
@web_login_required
def confirm_trash_entry(entry_id: str) -> Any:
    try:
        entry = _repo().get_entry(_parse_uuid(entry_id))
    except InputError:
        entry = None
    if entry is None:
        return render_template("404.html"), 404
    if entry["author"] != "user":
        return render_template("403.html"), 403
    return render_template("delete_confirm.html", entry=entry, permanent=False)


@web.post("/diary/<entry_id>/delete")
@web_login_required
@csrf_protect
def trash_entry(entry_id: str) -> Any:
    try:
        entry_uuid = _parse_uuid(entry_id)
    except InputError:
        return render_template("404.html"), 404
    if not _repo().trash_user_entry(entry_uuid):
        return render_template("404.html"), 404
    flash("日记已移入废纸篓，需要时还可以恢复。", "success")
    return redirect(url_for("diary.diary_home"))


@web.get("/diary/trash")
@web_login_required
def diary_trash() -> str:
    return render_template("trash.html", entries=_repo().list_deleted_entries(limit=100))


@web.post("/diary/trash/<entry_id>/restore")
@web_login_required
@csrf_protect
def restore_entry(entry_id: str) -> Any:
    try:
        entry_uuid = _parse_uuid(entry_id)
    except InputError:
        return render_template("404.html"), 404
    if not _repo().restore_user_entry(entry_uuid):
        return render_template("404.html"), 404
    flash("这篇日记已经回到时间线。", "success")
    return redirect(url_for("diary.entry_detail", entry_id=entry_id))


@web.get("/diary/trash/<entry_id>/delete")
@web_login_required
def confirm_permanent_delete(entry_id: str) -> Any:
    try:
        entry = _repo().get_entry(_parse_uuid(entry_id), include_deleted=True)
    except InputError:
        entry = None
    if entry is None or entry["author"] != "user" or entry["deleted_at"] is None:
        return render_template("404.html"), 404
    return render_template("delete_confirm.html", entry=entry, permanent=True)


@web.post("/diary/trash/<entry_id>/delete")
@web_login_required
@csrf_protect
def permanently_delete_entry(entry_id: str) -> Any:
    try:
        entry_uuid = _parse_uuid(entry_id)
    except InputError:
        return render_template("404.html"), 404
    if not _repo().permanently_delete_user_entry(entry_uuid):
        return render_template("404.html"), 404
    flash("这篇日记已被彻底删除，无法恢复。", "success")
    return redirect(url_for("diary.diary_trash"))


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


@api.post("/entries/<entry_id>/marks")
@api_token_required
def api_add_mark(entry_id: str) -> Any:
    try:
        entry_uuid = _parse_uuid(entry_id)
        data = _json_body(allowed_fields={"mark_type"})
        mark_type = _clean_mark(data.get("mark_type"))
    except InputError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    mark, created = _repo().add_mark(
        entry_id=entry_uuid, author="xiaxia", mark_type=mark_type
    )
    if mark is None:
        return jsonify({"error": "not_found", "message": "Diary entry not found."}), 404
    return jsonify({"mark": _json_value(mark), "created": created}), 201 if created else 200


@api.delete("/entries/<entry_id>/marks/<mark_type>")
@api_token_required
def api_remove_mark(entry_id: str, mark_type: str) -> Any:
    try:
        entry_uuid = _parse_uuid(entry_id)
        mark_type = _clean_mark(mark_type)
    except InputError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    if _repo().get_entry(entry_uuid) is None:
        return jsonify({"error": "not_found", "message": "Diary entry not found."}), 404
    removed = _repo().remove_mark(
        entry_id=entry_uuid, author="xiaxia", mark_type=mark_type
    )
    return jsonify({"removed": removed, "mark_type": mark_type})


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
