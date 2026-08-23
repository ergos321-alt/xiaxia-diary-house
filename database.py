from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class Database:
    """Small PostgreSQL repository. It never generates diary content."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        self.pool = ConnectionPool(
            conninfo=database_url,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
            open=True,
        )

    def close(self) -> None:
        self.pool.close()

    def healthcheck(self) -> bool:
        with self.pool.connection() as conn:
            return conn.execute("SELECT 1").fetchone() is not None

    def list_entries(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        author: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if author:
            conditions.append("e.author = %s")
            params.append(author)
        if start_date:
            conditions.append("e.entry_date >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("e.entry_date <= %s")
            params.append(end_date)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend((limit, offset))
        query = f"""
            SELECT e.id, e.author, e.title, e.content, e.entry_date,
                   e.created_at, e.updated_at,
                   COUNT(r.id)::int AS reply_count,
                   GREATEST(e.updated_at, COALESCE(MAX(r.updated_at), e.updated_at)) AS last_activity_at
            FROM diary_entries e
            LEFT JOIN diary_replies r ON r.entry_id = e.id
            {where_sql}
            GROUP BY e.id
            ORDER BY e.entry_date DESC, e.created_at DESC
            LIMIT %s OFFSET %s
        """
        with self.pool.connection() as conn:
            return list(conn.execute(query, params).fetchall())

    def get_entry(self, entry_id: UUID) -> dict[str, Any] | None:
        with self.pool.connection() as conn:
            entry = conn.execute(
                """
                SELECT e.id, e.author, e.title, e.content, e.entry_date,
                       e.created_at, e.updated_at,
                       COUNT(r.id)::int AS reply_count,
                       GREATEST(e.updated_at, COALESCE(MAX(r.updated_at), e.updated_at)) AS last_activity_at
                FROM diary_entries e
                LEFT JOIN diary_replies r ON r.entry_id = e.id
                WHERE e.id = %s
                GROUP BY e.id
                """,
                (entry_id,),
            ).fetchone()
            if entry is None:
                return None
            entry["replies"] = list(
                conn.execute(
                    """
                    SELECT id, entry_id, author, content, created_at, updated_at
                    FROM diary_replies
                    WHERE entry_id = %s
                    ORDER BY created_at ASC, id ASC
                    """,
                    (entry_id,),
                ).fetchall()
            )
            return entry

    def create_entry(
        self, *, author: str, title: str | None, content: str, entry_date: date
    ) -> dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO diary_entries (author, title, content, entry_date)
                VALUES (%s, %s, %s, %s)
                RETURNING id, author, title, content, entry_date, created_at, updated_at
                """,
                (author, title, content, entry_date),
            ).fetchone()
            conn.commit()
            assert row is not None
            row["reply_count"] = 0
            row["replies"] = []
            row["last_activity_at"] = row["updated_at"]
            return row

    def update_user_entry(
        self, entry_id: UUID, *, title: str | None, content: str, entry_date: date
    ) -> dict[str, Any] | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE diary_entries
                SET title = %s, content = %s, entry_date = %s, updated_at = now()
                WHERE id = %s AND author = 'user'
                RETURNING id, author, title, content, entry_date, created_at, updated_at
                """,
                (title, content, entry_date, entry_id),
            ).fetchone()
            conn.commit()
            return row

    def create_reply(
        self, *, entry_id: UUID, author: str, content: str
    ) -> dict[str, Any] | None:
        with self.pool.connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM diary_entries WHERE id = %s", (entry_id,)
            ).fetchone()
            if exists is None:
                return None
            row = conn.execute(
                """
                INSERT INTO diary_replies (entry_id, author, content)
                VALUES (%s, %s, %s)
                RETURNING id, entry_id, author, content, created_at, updated_at
                """,
                (entry_id, author, content),
            ).fetchone()
            conn.commit()
            return row

    def list_recent_replies(self, *, limit: int = 10) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            return list(
                conn.execute(
                    """
                    SELECT r.id, r.entry_id, r.author, r.content, r.created_at, r.updated_at,
                           e.author AS entry_author, e.title AS entry_title, e.entry_date
                    FROM diary_replies r
                    JOIN diary_entries e ON e.id = r.entry_id
                    ORDER BY r.created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            )
