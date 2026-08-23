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
        }
        self.entries[entry_id] = entry
        self.replies[entry_id] = []
        return deepcopy(entry)

    def update_user_entry(self, entry_id, *, title, content, entry_date):
        entry = self.entries.get(entry_id)
        if not entry or entry["author"] != "user":
            return None
        entry.update(title=title, content=content, entry_date=entry_date, updated_at=datetime.now(timezone.utc))
        return deepcopy(entry)

    def create_reply(self, *, entry_id, author, content):
        if entry_id not in self.entries:
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

    def get_entry(self, entry_id):
        entry = self.entries.get(entry_id)
        if not entry:
            return None
        result = deepcopy(entry)
        result["replies"] = deepcopy(self.replies[entry_id])
        return result

    def list_entries(self, *, limit=50, offset=0, author=None, start_date=None, end_date=None):
        entries = list(self.entries.values())
        if author:
            entries = [item for item in entries if item["author"] == author]
        if start_date:
            entries = [item for item in entries if item["entry_date"] >= start_date]
        if end_date:
            entries = [item for item in entries if item["entry_date"] <= end_date]
        entries.sort(key=lambda item: (item["entry_date"], item["created_at"]), reverse=True)
        return deepcopy(entries[offset:offset + limit])

    def list_recent_replies(self, *, limit=10):
        rows = []
        for entry_id, replies in self.replies.items():
            entry = self.entries[entry_id]
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
