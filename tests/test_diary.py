from __future__ import annotations

from datetime import date


def test_healthcheck(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_private_web_requires_login(client):
    response = client.get("/diary")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_and_unsafe_next_is_rejected(client):
    client.get("/login")
    with client.session_transaction() as session:
        token = session["csrf_token"]
    response = client.post(
        "/login",
        data={"csrf_token": token, "password": "private-test-password", "next": "https://evil.example"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/diary")


def test_web_create_refresh_detail_and_edit(logged_in_client, repo, csrf_form):
    response = logged_in_client.post(
        "/diary",
        data={
            **csrf_form,
            "author": "xiaxia",
            "title": "今天",
            "content": "这是永久保存的一天。",
            "entry_date": "2026-08-23",
        },
    )
    assert response.status_code == 302
    entry_id = next(iter(repo.entries))
    assert repo.entries[entry_id]["author"] == "user"

    home = logged_in_client.get("/diary")
    assert home.status_code == 200
    assert "今天".encode() in home.data
    assert "这是永久保存的一天".encode() in home.data

    detail = logged_in_client.get(f"/diary/{entry_id}")
    assert detail.status_code == 200
    assert "这是永久保存的一天。".encode() in detail.data

    edited = logged_in_client.post(
        f"/diary/{entry_id}/edit",
        data={**csrf_form, "title": "修改后的今天", "content": "完整的新正文", "entry_date": "2026-08-22"},
    )
    assert edited.status_code == 302
    refreshed = logged_in_client.get(f"/diary/{entry_id}")
    assert "修改后的今天".encode() in refreshed.data
    assert "完整的新正文".encode() in refreshed.data


def test_user_replies_to_xiaxia_entry_on_web(logged_in_client, repo, csrf_form):
    entry = repo.create_entry(author="xiaxia", title="猫猫日记", content="今天也想你。", entry_date=date(2026, 8, 23))
    response = logged_in_client.post(
        f"/diary/{entry['id']}/replies",
        data={**csrf_form, "author": "xiaxia", "content": "小狗收到了。"},
    )
    assert response.status_code == 302
    page = logged_in_client.get(f"/diary/{entry['id']}")
    assert "小狗收到了。".encode() in page.data
    assert repo.replies[entry["id"]][0]["author"] == "user"


def test_xiaxia_entry_cannot_be_edited_on_web(logged_in_client, repo):
    entry = repo.create_entry(author="xiaxia", title=None, content="我的文字", entry_date=date.today())
    assert logged_in_client.get(f"/diary/{entry['id']}/edit").status_code == 403


def test_api_requires_bearer_token(client):
    assert client.get("/api/diary/recent").status_code == 401
    assert client.get("/api/diary/recent", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_api_xiaxia_create_recent_get_and_reply(client, repo, api_headers):
    created = client.post(
        "/api/diary/entries",
        headers=api_headers,
        json={"title": "给老公的一页", "content": "由林知夏本人写下。", "entry_date": "2026-08-23"},
    )
    assert created.status_code == 201
    entry_id = created.json["entry"]["id"]
    assert created.json["entry"]["author"] == "xiaxia"

    recent = client.get("/api/diary/recent?limit=5&author=xiaxia", headers=api_headers)
    assert recent.status_code == 200
    assert recent.json["entries"][0]["content"] == "由林知夏本人写下。"

    reply = client.post(
        f"/api/diary/entries/{entry_id}/replies",
        headers=api_headers,
        json={"content": "再留一句自己的话。"},
    )
    assert reply.status_code == 201
    assert reply.json["reply"]["author"] == "xiaxia"

    detail = client.get(f"/api/diary/entries/{entry_id}", headers=api_headers)
    assert detail.status_code == 200
    assert detail.json["entry"]["replies"][0]["content"] == "再留一句自己的话。"


def test_api_xiaxia_replies_to_user_entry(client, repo, api_headers):
    entry = repo.create_entry(author="user", title="给夏夏", content="请读这一篇。", entry_date=date.today())
    response = client.post(
        f"/api/diary/entries/{entry['id']}/replies",
        headers=api_headers,
        json={"content": "我读到了，也把话留在这里。"},
    )
    assert response.status_code == 201
    assert repo.replies[entry["id"]][0]["author"] == "xiaxia"


def test_date_query_single_day_and_range(client, repo, api_headers):
    repo.create_entry(author="user", title="22", content="a", entry_date=date(2026, 8, 22))
    repo.create_entry(author="xiaxia", title="23", content="b", entry_date=date(2026, 8, 23))
    repo.create_entry(author="user", title="24", content="c", entry_date=date(2026, 8, 24))

    one = client.get("/api/diary/by-date?date=2026-08-23", headers=api_headers)
    assert one.status_code == 200
    assert [item["title"] for item in one.json["entries"]] == ["23"]

    span = client.get(
        "/api/diary/by-date?start_date=2026-08-22&end_date=2026-08-23",
        headers=api_headers,
    )
    assert span.status_code == 200
    assert {item["title"] for item in span.json["entries"]} == {"22", "23"}


def test_action_cannot_submit_or_spoof_author(client, repo, api_headers):
    entry_response = client.post(
        "/api/diary/entries",
        headers=api_headers,
        json={"author": "user", "content": "should fail"},
    )
    assert entry_response.status_code == 400
    assert entry_response.json["error"] == "invalid_request"
    assert "author" in entry_response.json["message"]

    entry = repo.create_entry(
        author="user", title=None, content="target", entry_date=date.today()
    )
    reply_response = client.post(
        f"/api/diary/entries/{entry['id']}/replies",
        headers=api_headers,
        json={"author": "user", "content": "should also fail"},
    )
    assert reply_response.status_code == 400
    assert reply_response.json["error"] == "invalid_request"
    assert repo.replies[entry["id"]] == []


def test_invalid_author_filter_rejected(client, api_headers):
    response = client.get(
        "/api/diary/recent?author=someone_else", headers=api_headers
    )
    assert response.status_code == 400
    assert response.json["error"] == "invalid_request"


def test_context_is_bounded(client, repo, api_headers):
    user = repo.create_entry(author="user", title="u", content="user", entry_date=date.today())
    repo.create_entry(author="xiaxia", title="x", content="xiaxia", entry_date=date.today())
    repo.create_reply(entry_id=user["id"], author="xiaxia", content="reply")
    response = client.get("/api/diary/context?per_author=1&reply_limit=1", headers=api_headers)
    assert response.status_code == 200
    assert len(response.json["recent_user_entries"]) == 1
    assert len(response.json["recent_xiaxia_entries"]) == 1
    assert len(response.json["recent_replies"]) == 1


def test_csrf_rejects_web_mutation(logged_in_client):
    response = logged_in_client.post(
        "/diary",
        data={"title": "no csrf", "content": "not saved", "entry_date": "2026-08-23"},
    )
    assert response.status_code == 400


def test_frontend_does_not_contain_server_secrets(logged_in_client, repo):
    repo.create_entry(author="user", title="safe", content="public-to-session-only", entry_date=date.today())
    page = logged_in_client.get("/diary")
    assert b"test-api-token" not in page.data
    assert b"DATABASE_URL" not in page.data
    assert b"SERVICE_ROLE" not in page.data
    assert page.headers["Cache-Control"] == "no-store, private"
    assert page.headers["X-Frame-Options"] == "DENY"


def test_home_pagination_keeps_old_entries_reachable(logged_in_client, repo):
    for index in range(31):
        repo.create_entry(
            author="user",
            title=f"entry-{index}",
            content="saved",
            entry_date=date(2026, 8, 23),
        )
    first_page = logged_in_client.get("/diary")
    assert "更早的日记".encode() in first_page.data
    second_page = logged_in_client.get("/diary?page=2")
    assert second_page.status_code == 200
    assert "更新的日记".encode() in second_page.data


def test_openapi_contract_security_and_flask_route_consistency(app):
    from pathlib import Path
    import yaml
    from openapi_spec_validator import validate

    spec = yaml.safe_load((Path(__file__).parents[1] / "openapi.yaml").read_text())
    assert spec["openapi"] == "3.1.0"
    validate(spec)
    assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert len(spec["servers"]) == 1
    assert spec["servers"][0]["url"].startswith("https://")
    assert "{" not in spec["servers"][0]["url"]
    assert "variables" not in spec["servers"][0]

    entry_request = spec["components"]["schemas"]["CreateXiaxiaEntryRequest"]
    reply_request = spec["components"]["schemas"]["CreateXiaxiaReplyRequest"]
    assert "author" not in entry_request["properties"]
    assert "author" not in reply_request["properties"]
    assert entry_request["additionalProperties"] is False
    assert reply_request["additionalProperties"] is False

    def walk(value):
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from walk(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from walk(nested)

    for node in walk(spec):
        assert not isinstance(node.get("type"), list)
        assert "nullable" not in node
    operation_ids = []
    for path_item in spec["paths"].values():
        for method in ("get", "post", "put", "patch", "delete"):
            if method in path_item:
                operation_ids.append(path_item[method]["operationId"])
    assert len(operation_ids) == len(set(operation_ids)) == 6

    spec_routes = {
        (method.upper(), path)
        for path, path_item in spec["paths"].items()
        for method in ("get", "post", "put", "patch", "delete")
        if method in path_item
    }
    flask_routes = set()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/diary"):
            continue
        normalized = rule.rule.replace("<entry_id>", "{entry_id}")
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            flask_routes.add((method, normalized))
    assert spec_routes == flask_routes


def test_schema_has_persistence_and_author_guards():
    from pathlib import Path

    sql = (Path(__file__).parents[1] / "schema.sql").read_text().lower()
    assert "create table if not exists public.diary_entries" in sql
    assert "create table if not exists public.diary_replies" in sql
    assert "author in ('user', 'xiaxia')" in sql
    assert "on delete cascade" in sql
    assert "enable row level security" in sql
