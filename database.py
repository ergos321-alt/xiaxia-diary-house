from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


ENTRY_SELECT = """
    SELECT e.id, e.author, e.title, e.content, e.entry_date,
           e.created_at, e.updated_at, e.deleted_at, e.deleted_by,
           (SELECT COUNT(*)::int
              FROM diary_replies r
             WHERE r.entry_id = e.id) AS reply_count,
           COALESCE(
               (SELECT jsonb_agg(
                           jsonb_build_object(
                               'id', m.id,
                               'entry_id', m.entry_id,
                               'author', m.author,
                               'mark_type', m.mark_type,
                               'created_at', m.created_at
                           ) ORDER BY m.created_at ASC
                       )
                  FROM diary_marks m
                 WHERE m.entry_id = e.id),
               '[]'::jsonb
           ) AS marks,
           GREATEST(
               e.updated_at,
               COALESCE(
                   (SELECT MAX(r.updated_at) FROM diary_replies r WHERE r.entry_id = e.id),
                   e.updated_at
               ),
               COALESCE(
                   (SELECT MAX(m.created_at) FROM diary_marks m WHERE m.entry_id = e.id),
                   e.updated_at
               )
           ) AS last_activity_at
      FROM diary_entries e
"""

ENTRY_SUMMARY_SELECT = """
    SELECT e.id, e.author, e.title, e.entry_date,
           e.created_at, e.updated_at,
           (SELECT COUNT(*)::int
              FROM diary_replies r
             WHERE r.entry_id = e.id) AS reply_count,
           GREATEST(
               e.updated_at,
               COALESCE(
                   (SELECT MAX(r.updated_at) FROM diary_replies r WHERE r.entry_id = e.id),
                   e.updated_at
               ),
               COALESCE(
                   (SELECT MAX(m.created_at) FROM diary_marks m WHERE m.entry_id = e.id),
                   e.updated_at
               )
           ) AS last_activity_at
      FROM diary_entries e
"""


class Database:
    """Small PostgreSQL repository. It stores facts and never generates diary text."""

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

    @staticmethod
    def _entry_filters(
        *,
        author: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> tuple[list[str], list[Any]]:
        conditions = ["e.deleted_at IS NULL"]
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
        return conditions, params

    def list_entries(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        author: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        conditions, params = self._entry_filters(
            author=author, start_date=start_date, end_date=end_date
        )
        params.extend((limit, offset))
        query = f"""
            {ENTRY_SELECT}
            WHERE {' AND '.join(conditions)}
            ORDER BY e.entry_date DESC, e.created_at DESC, e.id DESC
            LIMIT %s OFFSET %s
        """
        with self.pool.connection() as conn:
            return list(conn.execute(query, params).fetchall())

    def list_entry_summaries(
        self,
        *,
        limit: int,
        offset: int = 0,
        author: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return lightweight list rows without diary content, replies, or marks."""
        conditions, params = self._entry_filters(
            author=author, start_date=start_date, end_date=end_date
        )
        params.extend((limit, offset))
        query = f"""
            {ENTRY_SUMMARY_SELECT}
            WHERE {' AND '.join(conditions)}
            ORDER BY e.entry_date DESC, e.created_at DESC, e.id DESC
            LIMIT %s OFFSET %s
        """
        with self.pool.connection() as conn:
            return list(conn.execute(query, params).fetchall())

    def count_entries(
        self,
        *,
        author: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """Count active entries after applying the same filters as list queries."""
        conditions, params = self._entry_filters(
            author=author, start_date=start_date, end_date=end_date
        )
        query = f"""
            SELECT COUNT(*)::int AS total
            FROM diary_entries e
            WHERE {' AND '.join(conditions)}
        """
        with self.pool.connection() as conn:
            row = conn.execute(query, params).fetchone()
            return int(row["total"])

    def list_deleted_entries(self, *, limit: int = 100) -> list[dict[str, Any]]:
        query = f"""
            {ENTRY_SELECT}
            WHERE e.deleted_at IS NOT NULL AND e.author = 'user'
            ORDER BY e.deleted_at DESC
            LIMIT %s
        """
        with self.pool.connection() as conn:
            return list(conn.execute(query, (limit,)).fetchall())

    def list_months(self) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            return list(
                conn.execute(
                    """
                    SELECT to_char(entry_date, 'YYYY-MM') AS month,
                           COUNT(*)::int AS entry_count
                    FROM diary_entries
                    WHERE deleted_at IS NULL
                    GROUP BY to_char(entry_date, 'YYYY-MM')
                    ORDER BY month DESC
                    """
                ).fetchall()
            )

    def list_calendar_days(
        self, *, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            return list(
                conn.execute(
                    """
                    SELECT entry_date,
                           bool_or(author = 'user') AS has_user,
                           bool_or(author = 'xiaxia') AS has_xiaxia,
                           COUNT(*)::int AS entry_count
                    FROM diary_entries
                    WHERE deleted_at IS NULL
                      AND entry_date >= %s
                      AND entry_date <= %s
                    GROUP BY entry_date
                    ORDER BY entry_date ASC
                    """,
                    (start_date, end_date),
                ).fetchall()
            )

    def random_entry(self) -> dict[str, Any] | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM diary_entries
                WHERE deleted_at IS NULL
                ORDER BY random()
                LIMIT 1
                """
            ).fetchone()
        return self.get_entry(row["id"]) if row else None

    def get_entry(
        self, entry_id: UUID, *, include_deleted: bool = False
    ) -> dict[str, Any] | None:
        deleted_clause = "" if include_deleted else "AND e.deleted_at IS NULL"
        with self.pool.connection() as conn:
            entry = conn.execute(
                f"""
                {ENTRY_SELECT}
                WHERE e.id = %s {deleted_clause}
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

    def get_entry_author(self, entry_id: UUID) -> str | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT author
                FROM diary_entries
                WHERE id = %s AND deleted_at IS NULL
                """,
                (entry_id,),
            ).fetchone()
            return str(row["author"]) if row else None

    def create_entry(
        self, *, author: str, title: str | None, content: str, entry_date: date
    ) -> dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO diary_entries (author, title, content, entry_date)
                VALUES (%s, %s, %s, %s)
                RETURNING id, author, title, content, entry_date, created_at,
                          updated_at, deleted_at, deleted_by
                """,
                (author, title, content, entry_date),
            ).fetchone()
            conn.commit()
            assert row is not None
            row["reply_count"] = 0
            row["replies"] = []
            row["marks"] = []
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
                WHERE id = %s AND author = 'user' AND deleted_at IS NULL
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
                "SELECT 1 FROM diary_entries WHERE id = %s AND deleted_at IS NULL",
                (entry_id,),
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
                    WHERE e.deleted_at IS NULL
                    ORDER BY r.created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            )

    def add_mark(
        self, *, entry_id: UUID, author: str, mark_type: str
    ) -> tuple[dict[str, Any] | None, bool]:
        with self.pool.connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM diary_entries WHERE id = %s AND deleted_at IS NULL",
                (entry_id,),
            ).fetchone()
            if exists is None:
                return None, False
            row = conn.execute(
                """
                INSERT INTO diary_marks (entry_id, author, mark_type)
                VALUES (%s, %s, %s)
                ON CONFLICT (entry_id, author, mark_type) DO NOTHING
                RETURNING id, entry_id, author, mark_type, created_at
                """,
                (entry_id, author, mark_type),
            ).fetchone()
            created = row is not None
            if row is None:
                row = conn.execute(
                    """
                    SELECT id, entry_id, author, mark_type, created_at
                    FROM diary_marks
                    WHERE entry_id = %s AND author = %s AND mark_type = %s
                    """,
                    (entry_id, author, mark_type),
                ).fetchone()
            conn.commit()
            return row, created

    def remove_mark(self, *, entry_id: UUID, author: str, mark_type: str) -> bool:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                DELETE FROM diary_marks m
                USING diary_entries e
                WHERE m.entry_id = e.id
                  AND m.entry_id = %s
                  AND m.author = %s
                  AND m.mark_type = %s
                  AND e.deleted_at IS NULL
                RETURNING m.id
                """,
                (entry_id, author, mark_type),
            ).fetchone()
            conn.commit()
            return row is not None

    def trash_user_entry(self, entry_id: UUID) -> bool:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE diary_entries
                SET deleted_at = now(), deleted_by = 'user', updated_at = now()
                WHERE id = %s AND author = 'user' AND deleted_at IS NULL
                RETURNING id
                """,
                (entry_id,),
            ).fetchone()
            conn.commit()
            return row is not None

    def trash_xiaxia_entry(self, entry_id: UUID) -> bool:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE diary_entries
                SET deleted_at = now(), deleted_by = 'xiaxia', updated_at = now()
                WHERE id = %s AND author = 'xiaxia' AND deleted_at IS NULL
                RETURNING id
                """,
                (entry_id,),
            ).fetchone()
            conn.commit()
            return row is not None

    def restore_user_entry(self, entry_id: UUID) -> bool:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE diary_entries
                SET deleted_at = NULL, deleted_by = NULL, updated_at = now()
                WHERE id = %s AND author = 'user' AND deleted_at IS NOT NULL
                RETURNING id
                """,
                (entry_id,),
            ).fetchone()
            conn.commit()
            return row is not None

    def permanently_delete_user_entry(self, entry_id: UUID) -> bool:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                DELETE FROM diary_entries
                WHERE id = %s AND author = 'user' AND deleted_at IS NOT NULL
                RETURNING id
                """,
                (entry_id,),
            ).fetchone()
            conn.commit()
            return row is not None
