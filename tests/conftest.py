from __future__ import annotations

import os
from copy import deepcopy
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key-with-more-than-32-characters")
os.environ.setdefault("WEB_PASSWORD", "private-test-password")
os.environ.setdefault("DIARY_API_TOKEN", "test-api-token-with-more-than-32-characters")

from app import create_app  # noqa: E402


class FakeRepository:
    def __init__(self) -> None:
        self.entries: dict[UUID, dict] = {}
        self.replies: dict[UUID, list[dict]] = {}
        self.marks: dict[UUID, list[dict]] = {}

    def healthcheck(self) -> bool:
        return True

    def create_entry(self, *, author, title, content, entry_date):
        now = datetime.now(timezone.utc)
        entry_id = uuid4()
        entry = {
            "id": entry_id,
            "author": author,
            "title": title,
            "content": content,
            "entry_date": entry_date,
            "created_at": now,
            "updated_at": now,
            "last_activity_at": now,
            "reply_count": 0,
            "replies": [],
            "marks": [],
            "deleted_at": None,
            "deleted_by": None,
        }
        self.entries[entry_id] = entry
        self.replies[entry_id] = []
        self.marks[entry_id] = []
        return deepcopy(entry)

    def update_user_entry(self, entry_id, *, title, content, entry_date):
        entry = self.entries.get(entry_id)
        if not entry or entry["author"] != "user" or entry["deleted_at"] is not None:
            return None
        entry.update(title=title, content=content, entry_date=entry_date, updated_at=datetime.now(timezone.utc))
        return deepcopy(entry)

    def create_reply(self, *, entry_id, author, content):
        if entry_id not in self.entries or self.entries[entry_id]["deleted_at"] is not None:
            return None
        now = datetime.now(timezone.utc)
        reply = {
            "id": uuid4(),
            "entry_id": entry_id,
            "author": author,
            "content": content,
            "created_at": now,
            "updated_at": now,
        }
        self.replies[entry_id].append(reply)
        self.entries[entry_id]["reply_count"] = len(self.replies[entry_id])
        self.entries[entry_id]["last_activity_at"] = now
        return deepcopy(reply)

    def get_entry(self, entry_id, *, include_deleted=False):
        entry = self.entries.get(entry_id)
        if not entry or (entry["deleted_at"] is not None and not include_deleted):
            return None
        result = deepcopy(entry)
        result["replies"] = deepcopy(self.replies[entry_id])
        result["marks"] = deepcopy(self.marks[entry_id])
        return result

    def list_entries(self, *, limit=50, offset=0, author=None, start_date=None, end_date=None):
        entries = [item for item in self.entries.values() if item["deleted_at"] is None]
        if author:
            entries = [item for item in entries if item["author"] == author]
        if start_date:
            entries = [item for item in entries if item["entry_date"] >= start_date]
        if end_date:
            entries = [item for item in entries if item["entry_date"] <= end_date]
        entries.sort(key=lambda item: (item["entry_date"], item["created_at"]), reverse=True)
        return deepcopy(entries[offset:offset + limit])

    def list_deleted_entries(self, *, limit=100):
        entries = [
            item for item in self.entries.values()
            if item["author"] == "user" and item["deleted_at"] is not None
        ]
        entries.sort(key=lambda item: item["deleted_at"], reverse=True)
        return deepcopy(entries[:limit])

    def list_months(self):
        counts: dict[str, int] = {}
        for entry in self.entries.values():
            if entry["deleted_at"] is None:
                key = entry["entry_date"].strftime("%Y-%m")
                counts[key] = counts.get(key, 0) + 1
        return [{"month": key, "entry_count": counts[key]} for key in sorted(counts, reverse=True)]

    def list_calendar_days(self, *, start_date, end_date):
        days: dict[date, dict] = {}
        for entry in self.entries.values():
            if entry["deleted_at"] is not None:
                continue
            if not start_date <= entry["entry_date"] <= end_date:
                continue
            row = days.setdefault(
                entry["entry_date"],
                {
                    "entry_date": entry["entry_date"],
                    "has_user": False,
                    "has_xiaxia": False,
                    "entry_count": 0,
                },
            )
            row["has_user"] = row["has_user"] or entry["author"] == "user"
            row["has_xiaxia"] = row["has_xiaxia"] or entry["author"] == "xiaxia"
            row["entry_count"] += 1
        return deepcopy([days[key] for key in sorted(days)])

    def random_entry(self):
        entries = self.list_entries(limit=len(self.entries) or 1)
        return entries[0] if entries else None

    def add_mark(self, *, entry_id, author, mark_type):
        entry = self.entries.get(entry_id)
        if not entry or entry["deleted_at"] is not None:
            return None, False
        existing = next(
            (
                mark for mark in self.marks[entry_id]
                if mark["author"] == author and mark["mark_type"] == mark_type
            ),
            None,
        )
        if existing:
            return deepcopy(existing), False
        now = datetime.now(timezone.utc)
        mark = {
            "id": uuid4(),
            "entry_id": entry_id,
            "author": author,
            "mark_type": mark_type,
            "created_at": now,
        }
        self.marks[entry_id].append(mark)
        entry["marks"] = deepcopy(self.marks[entry_id])
        entry["last_activity_at"] = now
        return deepcopy(mark), True

    def remove_mark(self, *, entry_id, author, mark_type):
        entry = self.entries.get(entry_id)
        if not entry or entry["deleted_at"] is not None:
            return False
        before = len(self.marks[entry_id])
        self.marks[entry_id] = [
            mark for mark in self.marks[entry_id]
            if not (mark["author"] == author and mark["mark_type"] == mark_type)
        ]
        entry["marks"] = deepcopy(self.marks[entry_id])
        return len(self.marks[entry_id]) < before

    def trash_user_entry(self, entry_id):
        entry = self.entries.get(entry_id)
        if not entry or entry["author"] != "user" or entry["deleted_at"] is not None:
            return False
        now = datetime.now(timezone.utc)
        entry.update(deleted_at=now, deleted_by="user", updated_at=now)
        return True

    def restore_user_entry(self, entry_id):
        entry = self.entries.get(entry_id)
        if not entry or entry["author"] != "user" or entry["deleted_at"] is None:
            return False
        now = datetime.now(timezone.utc)
        entry.update(deleted_at=None, deleted_by=None, updated_at=now)
        return True

    def permanently_delete_user_entry(self, entry_id):
        entry = self.entries.get(entry_id)
        if not entry or entry["author"] != "user" or entry["deleted_at"] is None:
            return False
        del self.entries[entry_id]
        del self.replies[entry_id]
        del self.marks[entry_id]
        return True

    def list_recent_replies(self, *, limit=10):
        rows = []
        for entry_id, replies in self.replies.items():
            entry = self.entries[entry_id]
            if entry["deleted_at"] is not None:
                continue
            for reply in replies:
                rows.append(
                    {
                        **reply,
                        "entry_author": entry["author"],
                        "entry_title": entry["title"],
                        "entry_date": entry["entry_date"],
                    }
                )
        rows.sort(key=lambda item: item["created_at"], reverse=True)
        return deepcopy(rows[:limit])


@pytest.fixture
def repo():
    return FakeRepository()


@pytest.fixture
def app(repo):
    return create_app(
        repository=repo,
        test_config={"TESTING": True, "SESSION_COOKIE_SECURE": False},
    )


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def api_headers():
    return {"Authorization": f"Bearer {os.environ['DIARY_API_TOKEN']}"}


@pytest.fixture
def logged_in_client(client):
    with client.session_transaction() as session:
        session["web_authenticated"] = True
        session["csrf_token"] = "test-csrf"
    return client


@pytest.fixture
def csrf_form():
    return {"csrf_token": "test-csrf"}
