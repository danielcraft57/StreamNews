"""Backend DB : Postgres (asyncpg) en prod, SQLite (aiosqlite) en local."""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional, Sequence, Union
from urllib.parse import unquote, urlparse

_PARAM_RE = re.compile(r"\$(\d+)")
_CAST_RE = re.compile(r"::(?:jsonb|json|text|integer|int|bigint|boolean|bool)\b", re.I)


def is_sqlite_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith("sqlite:") or u.startswith("sqlite+")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_sqlite_path(database_url: str) -> Path:
    """sqlite:///./data/x.db ou sqlite:////abs/path.db -> Path absolu."""
    raw = (database_url or "").strip()
    # sqlite+aiosqlite:///...
    if raw.startswith("sqlite+"):
        raw = "sqlite:" + raw.split(":", 1)[1]
    if not raw.startswith("sqlite:"):
        raise ValueError(f"URL SQLite invalide: {database_url}")

    # sqlite:///relative  |  sqlite:////absolute
    rest = raw[len("sqlite:") :]
    if rest.startswith("////"):
        path = Path(unquote(rest[3:]))
    elif rest.startswith("///"):
        path = Path(unquote(rest[3:]))
        if not path.is_absolute():
            path = repo_root() / path
    else:
        parsed = urlparse(raw)
        path = Path(unquote(parsed.path or ""))
        if not path.is_absolute():
            path = repo_root() / path

    return path.resolve()


def adapt_sql_for_sqlite(sql: str, args: Sequence[Any]) -> tuple[str, tuple]:
    """Convertit $1,$2 + casts Postgres vers ? pour aiosqlite."""
    cleaned = _CAST_RE.sub("", sql)
    order: list[int] = []

    def _repl(match: re.Match) -> str:
        order.append(int(match.group(1)))
        return "?"

    converted = _PARAM_RE.sub(_repl, cleaned)
    if not order:
        return converted, tuple(args)
    bound = tuple(args[n - 1] for n in order)
    return converted, bound


class _PostgresConn:
    """Proxy mince autour d'une connexion asyncpg."""

    def __init__(self, conn):
        self._conn = conn

    async def execute(self, sql: str, *args):
        return await self._conn.execute(sql, *args)

    async def fetch(self, sql: str, *args):
        return await self._conn.fetch(sql, *args)

    async def fetchrow(self, sql: str, *args):
        return await self._conn.fetchrow(sql, *args)

    async def fetchval(self, sql: str, *args):
        return await self._conn.fetchval(sql, *args)

    def transaction(self):
        return self._conn.transaction()


class _SqliteTransaction:
    def __init__(self, conn: "_SqliteConn"):
        self._conn = conn

    async def __aenter__(self):
        self._conn._tx_depth += 1
        if self._conn._tx_depth == 1:
            await self._conn._raw.execute("BEGIN")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._conn._tx_depth = max(0, self._conn._tx_depth - 1)
        if self._conn._tx_depth == 0:
            if exc_type is None:
                await self._conn._raw.commit()
            else:
                await self._conn._raw.rollback()
        return False


class _SqliteConn:
    def __init__(self, conn):
        self._raw = conn
        self._tx_depth = 0

    def transaction(self):
        return _SqliteTransaction(self)

    async def execute(self, sql: str, *args):
        q, bound = adapt_sql_for_sqlite(sql, args)
        cursor = await self._raw.execute(q, bound)
        if self._tx_depth == 0:
            await self._raw.commit()
        # Compat asyncpg status "DELETE N"
        if cursor.rowcount is not None and cursor.rowcount >= 0:
            verb = (q.lstrip().split(None, 1) or ["OK"])[0].upper()
            return f"{verb} {cursor.rowcount}"
        return "OK"

    async def fetch(self, sql: str, *args):
        q, bound = adapt_sql_for_sqlite(sql, args)
        cursor = await self._raw.execute(q, bound)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def fetchrow(self, sql: str, *args):
        rows = await self.fetch(sql, *args)
        return rows[0] if rows else None

    async def fetchval(self, sql: str, *args):
        row = await self.fetchrow(sql, *args)
        if row is None:
            return None
        return next(iter(row.values()))


class PostgresPool:
    backend = "postgres"

    def __init__(self, pool):
        self._pool = pool

    @asynccontextmanager
    async def acquire(self):
        async with self._pool.acquire() as conn:
            yield _PostgresConn(conn)

    async def close(self):
        await self._pool.close()


class SqlitePool:
    backend = "sqlite"

    def __init__(self, path: Path):
        self.path = path
        self._conn = None

    async def open(self):
        import aiosqlite

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.commit()
        return self

    @asynccontextmanager
    async def acquire(self):
        if self._conn is None:
            await self.open()
        yield _SqliteConn(self._conn)

    async def close(self):
        if self._conn is not None:
            try:
                await self._conn.commit()
            except Exception:
                pass
            await self._conn.close()
            self._conn = None


async def create_pool(database_url: Optional[str] = None) -> Union[PostgresPool, SqlitePool]:
    # Pas de mot de passe en dur : defaut = SQLite local (voir .env.local.example).
    url = database_url or os.getenv("DATABASE_URL", "sqlite:///./data/streamnews.db")
    if is_sqlite_url(url):
        path = resolve_sqlite_path(url)
        pool = SqlitePool(path)
        await pool.open()
        return pool

    import asyncpg

    raw = await asyncpg.create_pool(url)
    return PostgresPool(raw)
