"""MCP adapters for the existing Diary HTTP API."""

from __future__ import annotations

import contextlib
import os
from datetime import date
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from a2wsgi import WSGIMiddleware
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.applications import Starlette
from starlette.routing import Mount

from app import create_app


diary_app = create_app()
mcp = MCPServer("Xiaxia Diary")


def _request(method: str, path: str, *, params: dict | None = None, body: dict | None = None) -> dict:
    """Call one existing API route with the existing Diary bearer credential."""
    port = os.environ.get("PORT", "10000")
    token = os.environ["DIARY_API_TOKEN"]
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30.0) as client:
        response = client.request(
            method,
            path,
            params={key: value for key, value in (params or {}).items() if value is not None},
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
    return response.json()


@mcp.tool()
def getRecentDiaryEntries(
    author: Literal["user", "xiaxia"] | None = None,
    page: Annotated[int, Field(ge=1)] = 1,
    page_size: Annotated[int, Field(ge=1, le=20)] = 10,
) -> dict:
    """List recent diary entry summaries with pagination metadata."""
    return _request("GET", "/api/diary/recent", params={"author": author, "page": page, "page_size": page_size})


@mcp.tool()
def getDiaryEntry(entry_id: UUID) -> dict:
    """Read one complete diary entry, including its replies and marks."""
    return _request("GET", f"/api/diary/entries/{entry_id}")


@mcp.tool()
def getDiaryEntriesByDate(
    date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    author: Literal["user", "xiaxia"] | None = None,
    page: Annotated[int, Field(ge=1)] = 1,
    page_size: Annotated[int, Field(ge=1, le=20)] = 10,
) -> dict:
    """List diary entry summaries for a date or inclusive date range."""
    return _request(
        "GET",
        "/api/diary/by-date",
        params={
            "date": date.isoformat() if date else None,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "author": author,
            "page": page,
            "page_size": page_size,
        },
    )


@mcp.tool()
def createDiaryEntry(
    content: Annotated[str, Field(min_length=1, max_length=100000)],
    title: Annotated[str | None, Field(max_length=200)] = None,
    entry_date: date | None = None,
) -> dict:
    """Create a diary entry from supplied text; the API records author as Xiaxia."""
    body: dict = {"content": content}
    if title is not None:
        body["title"] = title
    if entry_date is not None:
        body["entry_date"] = entry_date.isoformat()
    return _request("POST", "/api/diary/entries", body=body)


@mcp.tool()
def replyToDiaryEntry(
    entry_id: UUID, content: Annotated[str, Field(min_length=1, max_length=100000)]
) -> dict:
    """Add a supplied reply to an existing diary entry; the API records author as Xiaxia."""
    return _request("POST", f"/api/diary/entries/{entry_id}/replies", body={"content": content})


@mcp.tool()
def addDiaryMark(entry_id: UUID, mark_type: Literal["leaf"]) -> dict:
    """Add Xiaxia's mark to a diary entry; repeating the same mark is safe."""
    return _request("POST", f"/api/diary/entries/{entry_id}/marks", body={"mark_type": mark_type})


@mcp.tool()
def removeDiaryMark(entry_id: UUID, mark_type: Literal["leaf"]) -> dict:
    """Remove Xiaxia's mark from a diary entry."""
    return _request("DELETE", f"/api/diary/entries/{entry_id}/marks/{quote(mark_type, safe='')}")


@mcp.tool()
def deleteDiaryEntry(entry_id: UUID) -> dict:
    """Soft-delete an active diary entry only when its stored author is Xiaxia."""
    return _request("DELETE", f"/api/diary/entries/{entry_id}")


@mcp.tool()
def getSharedDiaryContext(
    per_author: Annotated[int, Field(ge=1, le=10)] = 5,
    reply_limit: Annotated[int, Field(ge=1, le=20)] = 10,
) -> dict:
    """Get bounded recent entries and replies for both diary authors."""
    return _request(
        "GET",
        "/api/diary/context",
        params={"per_author": per_author, "reply_limit": reply_limit},
    )


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette):
    async with mcp.session_manager.run():
        yield


host = os.environ.get("DIARY_PUBLIC_HOST", "xiaxia-diary-house.onrender.com")
transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[host, f"{host}:*", "localhost:*", "127.0.0.1:*"],
)
mcp_http_app = mcp.streamable_http_app(transport_security=transport_security)
diary_http_app = WSGIMiddleware(diary_app)


async def dispatch_http(scope, receive, send):
    """Dispatch /mcp to MCP and every existing web/API path to Flask."""
    if scope["path"] == "/mcp":
        await mcp_http_app(scope, receive, send)
    else:
        await diary_http_app(scope, receive, send)


app = Starlette(
    routes=[
        Mount("/", app=dispatch_http),
    ],
    lifespan=lifespan,
)
