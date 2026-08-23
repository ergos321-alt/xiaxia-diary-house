from __future__ import annotations

from datetime import date

import diary as diary_module


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


def test_margin_replies_keep_true_chronological_order(logged_in_client, repo):
    entry = repo.create_entry(author="user", title="一页", content="正文", entry_date=date.today())
    repo.create_reply(entry_id=entry["id"], author="xiaxia", content="第一句")
    repo.create_reply(entry_id=entry["id"], author="user", content="第二句")
    repo.create_reply(entry_id=entry["id"], author="xiaxia", content="第三句")
    page = logged_in_client.get(f"/diary/{entry['id']}")
    html = page.get_data(as_text=True)
    assert html.index("第一句") < html.index("第二句") < html.index("第三句")
    assert "页边慢慢长出的字" in html


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


def test_web_archive_by_month_and_exact_date(logged_in_client, repo):
    repo.create_entry(author="user", title="八月二十二", content="a", entry_date=date(2026, 8, 22))
    repo.create_entry(author="xiaxia", title="八月二十三", content="b", entry_date=date(2026, 8, 23))
    repo.create_entry(author="user", title="七月", content="c", entry_date=date(2026, 7, 31))

    month = logged_in_client.get("/diary/archive?month=2026-08")
    assert month.status_code == 200
    assert "八月二十二" in month.get_data(as_text=True)
    assert "八月二十三" in month.get_data(as_text=True)
    assert "七月" not in month.get_data(as_text=True)

    exact = logged_in_client.get("/diary/archive?date=2026-08-22")
    assert exact.status_code == 200
    assert "八月二十二" in exact.get_data(as_text=True)
    assert "八月二十三" not in exact.get_data(as_text=True)


def test_home_author_browsing_keeps_each_persons_pages_separate(logged_in_client, repo):
    repo.create_entry(
        author="user", title="只在我的一边", content="a", entry_date=date(2026, 8, 24)
    )
    repo.create_entry(
        author="xiaxia", title="只在夏夏一边", content="b", entry_date=date(2026, 8, 23)
    )

    all_pages = logged_in_client.get("/diary").get_data(as_text=True)
    assert "只在我的一边" in all_pages
    assert "只在夏夏一边" in all_pages
    assert "2026 年 8 月 24 日" in all_pages

    mine = logged_in_client.get("/diary?author=user")
    assert mine.status_code == 200
    assert "只在我的一边" in mine.get_data(as_text=True)
    assert "只在夏夏一边" not in mine.get_data(as_text=True)

    xiaxia = logged_in_client.get("/diary?author=xiaxia")
    assert xiaxia.status_code == 200
    assert "只在夏夏一边" in xiaxia.get_data(as_text=True)
    assert "只在我的一边" not in xiaxia.get_data(as_text=True)
    assert logged_in_client.get("/diary?author=other").status_code == 400


def test_calendar_shows_each_authors_trace_and_both_traces(logged_in_client, repo):
    repo.create_entry(
        author="user", title="我五号写过", content="a", entry_date=date(2026, 8, 5)
    )
    repo.create_entry(
        author="xiaxia", title="夏夏六号写过", content="b", entry_date=date(2026, 8, 6)
    )
    repo.create_entry(
        author="user", title="我们七号之一", content="c", entry_date=date(2026, 8, 7)
    )
    repo.create_entry(
        author="xiaxia", title="我们七号之二", content="d", entry_date=date(2026, 8, 7)
    )

    html = logged_in_client.get("/diary/archive?month=2026-08").get_data(as_text=True)

    def calendar_cell(day: str) -> str:
        start = html.index(f'data-date="{day}"')
        return html[start:html.index("</a>", start)]

    fifth = calendar_cell("2026-08-05")
    sixth = calendar_cell("2026-08-06")
    seventh = calendar_cell("2026-08-07")
    assert 'data-author="user"' in fifth
    assert 'data-author="xiaxia"' not in fifth
    assert 'data-author="xiaxia"' in sixth
    assert 'data-author="user"' not in sixth
    assert 'data-author="user"' in seventh
    assert 'data-author="xiaxia"' in seventh


def test_home_only_offers_one_year_ago_when_a_real_entry_exists(
    logged_in_client, repo, monkeypatch
):
    monkeypatch.setattr(diary_module, "_today", lambda: date(2026, 8, 24))
    empty_home = logged_in_client.get("/diary").get_data(as_text=True)
    assert "一年前的今天" not in empty_home

    repo.create_entry(
        author="xiaxia",
        title="一年前留下的一页",
        content="真实存在",
        entry_date=date(2025, 8, 24),
    )
    home = logged_in_client.get("/diary").get_data(as_text=True)
    assert "一年前的今天" in home
    page = logged_in_client.get("/diary/on-this-day").get_data(as_text=True)
    assert "一年前留下的一页" in page


def test_detail_links_the_other_persons_entries_from_same_day(logged_in_client, repo):
    user_entry = repo.create_entry(
        author="user", title="我的这一天", content="a", entry_date=date(2026, 8, 24)
    )
    xiaxia_entry = repo.create_entry(
        author="xiaxia", title="夏夏的这一天", content="b", entry_date=date(2026, 8, 24)
    )
    repo.create_entry(
        author="xiaxia", title="夏夏的另一天", content="c", entry_date=date(2026, 8, 23)
    )

    html = logged_in_client.get(f"/diary/{user_entry['id']}").get_data(as_text=True)
    assert "这一天，我们都留下过记录。" in html
    assert "夏夏的这一天" in html
    assert f'/diary/{xiaxia_entry["id"]}' in html
    assert "夏夏的另一天" not in html


def test_on_this_day_empty_is_safe(logged_in_client):
    response = logged_in_client.get("/diary/on-this-day")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "去年的今天" in html
    assert "这一天还没有留下日记" in html


def test_random_page_redirects_only_to_real_active_entry(logged_in_client, repo):
    active = repo.create_entry(author="xiaxia", title="真的一页", content="a", entry_date=date.today())
    deleted = repo.create_entry(author="user", title="已移走", content="b", entry_date=date.today())
    repo.trash_user_entry(deleted["id"])
    response = logged_in_client.get("/diary/random")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/diary/{active['id']}")


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


def test_user_mark_is_fixed_idempotent_and_removable(logged_in_client, repo, csrf_form):
    entry = repo.create_entry(author="xiaxia", title="留一片叶子", content="正文", entry_date=date.today())
    url = f"/diary/{entry['id']}/marks"
    first = logged_in_client.post(url, data={**csrf_form, "author": "xiaxia"})
    second = logged_in_client.post(url, data={**csrf_form, "author": "xiaxia"})
    assert first.status_code == second.status_code == 302
    assert len(repo.marks[entry["id"]]) == 1
    assert repo.marks[entry["id"]][0]["author"] == "user"
    assert "🌿 我" in logged_in_client.get("/diary").get_data(as_text=True)
    page = logged_in_client.get(f"/diary/{entry['id']}")
    assert "🌿 我" in page.get_data(as_text=True)

    removed = logged_in_client.post(
        f"/diary/{entry['id']}/marks/remove", data=csrf_form
    )
    assert removed.status_code == 302
    assert repo.marks[entry["id"]] == []


def test_action_mark_is_fixed_xiaxia_idempotent_and_removable(client, repo, api_headers):
    entry = repo.create_entry(author="user", title="目标", content="正文", entry_date=date.today())
    endpoint = f"/api/diary/entries/{entry['id']}/marks"
    first = client.post(endpoint, headers=api_headers, json={"mark_type": "leaf"})
    again = client.post(endpoint, headers=api_headers, json={"mark_type": "leaf"})
    assert first.status_code == 201
    assert again.status_code == 200
    assert first.json["mark"]["author"] == "xiaxia"
    assert len(repo.marks[entry["id"]]) == 1

    spoof = client.post(
        endpoint,
        headers=api_headers,
        json={"mark_type": "leaf", "author": "user"},
    )
    assert spoof.status_code == 400
    assert len(repo.marks[entry["id"]]) == 1

    removed = client.delete(
        f"/api/diary/entries/{entry['id']}/marks/leaf", headers=api_headers
    )
    assert removed.status_code == 200
    assert removed.json == {"mark_type": "leaf", "removed": True}
    assert repo.marks[entry["id"]] == []


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


def test_soft_delete_hides_only_target_and_restore_returns_it(logged_in_client, repo, csrf_form, api_headers):
    target = repo.create_entry(author="user", title="暂时收起", content="a", entry_date=date.today())
    other = repo.create_entry(author="xiaxia", title="仍在这里", content="b", entry_date=date.today())

    confirm = logged_in_client.get(f"/diary/{target['id']}/delete")
    assert confirm.status_code == 200
    moved = logged_in_client.post(f"/diary/{target['id']}/delete", data=csrf_form)
    assert moved.status_code == 302
    assert repo.entries[target["id"]]["deleted_at"] is not None
    assert repo.entries[other["id"]]["deleted_at"] is None

    home = logged_in_client.get("/diary").get_data(as_text=True)
    assert "暂时收起" not in home
    assert "仍在这里" in home
    assert logged_in_client.get(f"/diary/{target['id']}").status_code == 404
    assert logged_in_client.get("/diary/trash").status_code == 200

    api_detail = logged_in_client.get(
        f"/api/diary/entries/{target['id']}", headers=api_headers
    )
    assert api_detail.status_code == 404
    recent = logged_in_client.get("/api/diary/recent", headers=api_headers)
    assert {item["title"] for item in recent.json["entries"]} == {"仍在这里"}

    restored = logged_in_client.post(
        f"/diary/trash/{target['id']}/restore", data=csrf_form
    )
    assert restored.status_code == 302
    assert repo.entries[target["id"]]["deleted_at"] is None
    assert logged_in_client.get(f"/diary/{target['id']}").status_code == 200


def test_permanent_delete_requires_trash_and_cascades_fake_data(logged_in_client, repo, csrf_form):
    target = repo.create_entry(author="user", title="删除目标", content="a", entry_date=date.today())
    other = repo.create_entry(author="user", title="保留目标", content="b", entry_date=date.today())
    assert logged_in_client.post(
        f"/diary/trash/{target['id']}/delete", data=csrf_form
    ).status_code == 404
    repo.create_reply(entry_id=target["id"], author="xiaxia", content="页边")
    repo.add_mark(entry_id=target["id"], author="user", mark_type="leaf")
    repo.trash_user_entry(target["id"])
    assert logged_in_client.get(f"/diary/trash/{target['id']}/delete").status_code == 200
    response = logged_in_client.post(
        f"/diary/trash/{target['id']}/delete", data=csrf_form
    )
    assert response.status_code == 302
    assert target["id"] not in repo.entries
    assert other["id"] in repo.entries


def test_xiaxia_entry_cannot_be_trashed_on_web(logged_in_client, repo, csrf_form):
    entry = repo.create_entry(author="xiaxia", title="她的一页", content="正文", entry_date=date.today())
    assert logged_in_client.get(f"/diary/{entry['id']}/delete").status_code == 403
    assert logged_in_client.post(f"/diary/{entry['id']}/delete", data=csrf_form).status_code == 404
    assert entry["id"] in repo.entries


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
    mark_request = spec["components"]["schemas"]["CreateXiaxiaMarkRequest"]
    assert "author" not in entry_request["properties"]
    assert "author" not in reply_request["properties"]
    assert "author" not in mark_request["properties"]
    assert entry_request["additionalProperties"] is False
    assert reply_request["additionalProperties"] is False
    assert mark_request["additionalProperties"] is False

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
                operation = path_item[method]
                operation_ids.append(operation["operationId"])
                assert len(operation.get("description", "")) <= 300
                for parameter in operation.get("parameters", []):
                    if "$ref" not in parameter:
                        assert len(parameter.get("description", "")) <= 700
    assert len(operation_ids) == len(set(operation_ids)) == 8
    assert {
        "getRecentDiaryEntries",
        "getDiaryEntry",
        "getDiaryEntriesByDate",
        "createDiaryEntry",
        "replyToDiaryEntry",
        "getSharedDiaryContext",
    }.issubset(operation_ids)
    assert {"addDiaryMark", "removeDiaryMark"}.issubset(operation_ids)
    assert spec["paths"]["/api/diary/entries/{entry_id}/marks"]["post"][
        "x-openai-isConsequential"
    ] is True
    assert "delete" not in spec["paths"]["/api/diary/entries/{entry_id}"]

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
        normalized = rule.rule.replace("<entry_id>", "{entry_id}").replace(
            "<mark_type>", "{mark_type}"
        )
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            flask_routes.add((method, normalized))
    assert spec_routes == flask_routes


def test_schema_has_persistence_and_author_guards():
    from pathlib import Path

    sql = (Path(__file__).parents[1] / "schema.sql").read_text().lower()
    assert "create table if not exists public.diary_entries" in sql
    assert "create table if not exists public.diary_replies" in sql
    assert "create table if not exists public.diary_marks" in sql
    assert "author in ('user', 'xiaxia')" in sql
    assert "unique (entry_id, author, mark_type)" in sql
    assert "deleted_at timestamptz" in sql
    assert "on delete cascade" in sql
    assert "enable row level security" in sql


def test_v11_migration_contains_only_required_additions():
    from pathlib import Path

    sql = (
        Path(__file__).parents[1] / "migrations" / "001_v1_1_marks_and_trash.sql"
    ).read_text().lower()
    assert "add column if not exists deleted_at" in sql
    assert "add column if not exists deleted_by" in sql
    assert "create table if not exists public.diary_marks" in sql
    assert "unique (entry_id, author, mark_type)" in sql
