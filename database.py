import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "marketplace.db"

def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

def add_watch(chat_id: int, query: str, max_price: Optional[float], location: Optional[str]) -> int:
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
            SELECT id, query, max_price, location, active, created_at
            FROM watches
            WHERE chat_id = ?
            ORDER BY id DESC
            """,
            (chat_id,),
        ).fetchall()

def remove_watch(chat_id: int, watch_id: int) -> bool:
    with connect() as con:
        cursor = con.execute(
            "DELETE FROM watches WHERE chat_id = ? AND id = ?",
            (chat_id, watch_id),
        )
        return cursor.rowcount > 0
