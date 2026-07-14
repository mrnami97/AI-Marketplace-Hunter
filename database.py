import sqlite3
from pathlib import Path
from typing import Optional


DB_PATH = Path(__file__).resolve().parent / "marketplace.db"


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                max_price REAL,
                location TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                initialized INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_checked_at TEXT
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watch_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                title TEXT,
                price REAL,
                url TEXT NOT NULL,
                posted_text TEXT,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(watch_id, source, listing_id),
                FOREIGN KEY(watch_id) REFERENCES watches(id) ON DELETE CASCADE
            )
            """
        )

        columns = {
            row["name"]
            for row in con.execute("PRAGMA table_info(watches)").fetchall()
        }

        if "initialized" not in columns:
            con.execute(
                "ALTER TABLE watches "
                "ADD COLUMN initialized INTEGER NOT NULL DEFAULT 0"
            )

        if "last_checked_at" not in columns:
            con.execute(
                "ALTER TABLE watches "
                "ADD COLUMN last_checked_at TEXT"
            )


def add_watch(
    chat_id: int,
    query: str,
    max_price: Optional[float],
    location: Optional[str],
) -> int:
    with connect() as con:
        cursor = con.execute(
            """
            INSERT INTO watches (chat_id, query, max_price, location)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, query, max_price, location),
        )
        return int(cursor.lastrowid)


def get_watches(chat_id: int):
    with connect() as con:
        return con.execute(
            """
            SELECT
                id, chat_id, query, max_price, location,
                active, initialized, created_at, last_checked_at
            FROM watches
            WHERE chat_id = ?
            ORDER BY id DESC
            """,
            (chat_id,),
        ).fetchall()


def get_active_watches():
    with connect() as con:
        return con.execute(
            """
            SELECT
                id, chat_id, query, max_price, location,
                initialized, last_checked_at
            FROM watches
            WHERE active = 1
            ORDER BY id ASC
            """
        ).fetchall()


def get_watch(chat_id: int, watch_id: int):
    with connect() as con:
        return con.execute(
            """
            SELECT
                id, chat_id, query, max_price, location,
                active, initialized, created_at, last_checked_at
            FROM watches
            WHERE chat_id = ? AND id = ?
            """,
            (chat_id, watch_id),
        ).fetchone()


def get_latest_watch(chat_id: int):
    with connect() as con:
        return con.execute(
            """
            SELECT
                id, chat_id, query, max_price, location,
                active, initialized, created_at, last_checked_at
            FROM watches
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id,),
        ).fetchone()


def remove_watch(chat_id: int, watch_id: int) -> bool:
    with connect() as con:
        cursor = con.execute(
            """
            DELETE FROM watches
            WHERE chat_id = ? AND id = ?
            """,
            (chat_id, watch_id),
        )
        return cursor.rowcount > 0


def listing_was_seen(
    watch_id: int,
    source: str,
    listing_id: str,
) -> bool:
    with connect() as con:
        row = con.execute(
            """
            SELECT id
            FROM seen_listings
            WHERE watch_id = ? AND source = ? AND listing_id = ?
            """,
            (watch_id, source, listing_id),
        ).fetchone()
        return row is not None


def save_seen_listing(
    watch_id: int,
    source: str,
    listing_id: str,
    title: str,
    price: Optional[float],
    url: str,
    posted_text: Optional[str],
) -> None:
    with connect() as con:
        con.execute(
            """
            INSERT INTO seen_listings (
                watch_id, source, listing_id, title,
                price, url, posted_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(watch_id, source, listing_id)
            DO UPDATE SET
                title = excluded.title,
                price = excluded.price,
                url = excluded.url,
                posted_text = excluded.posted_text,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            (
                watch_id,
                source,
                listing_id,
                title,
                price,
                url,
                posted_text,
            ),
        )


def mark_watch_initialized(watch_id: int) -> None:
    with connect() as con:
        con.execute(
            """
            UPDATE watches
            SET initialized = 1,
                last_checked_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (watch_id,),
        )


def update_watch_checked_time(watch_id: int) -> None:
    with connect() as con:
        con.execute(
            """
            UPDATE watches
            SET last_checked_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (watch_id,),
        )


def get_seen_listings(
    watch_id: int,
    limit: int = 15,
):
    with connect() as con:
        return con.execute(
            """
            SELECT
                source, listing_id, title, price, url,
                posted_text, first_seen_at, last_seen_at
            FROM seen_listings
            WHERE watch_id = ?
            ORDER BY last_seen_at DESC, id DESC
            LIMIT ?
            """,
            (watch_id, limit),
        ).fetchall()


def count_seen_listings(watch_id: int) -> int:
    with connect() as con:
        row = con.execute(
            """
            SELECT COUNT(*) AS total
            FROM seen_listings
            WHERE watch_id = ?
            """,
            (watch_id,),
        ).fetchone()
        return int(row["total"])
