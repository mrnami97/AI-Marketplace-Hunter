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
                location TEXT,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(watch_id, source, listing_id),
                FOREIGN KEY(watch_id)
                    REFERENCES watches(id)
                    ON DELETE CASCADE
            )
            """
        )

        watch_columns = {
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(watches)"
            ).fetchall()
        }

        if "initialized" not in watch_columns:
            con.execute(
                "ALTER TABLE watches "
                "ADD COLUMN initialized "
                "INTEGER NOT NULL DEFAULT 0"
            )

        if "last_checked_at" not in watch_columns:
            con.execute(
                "ALTER TABLE watches "
                "ADD COLUMN last_checked_at TEXT"
            )

        con.execute("""
            CREATE TABLE IF NOT EXISTS market_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_key TEXT NOT NULL,
                source TEXT NOT NULL,
                location TEXT,
                listing_id TEXT NOT NULL,
                title TEXT NOT NULL,
                price REAL NOT NULL,
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_key, source, listing_id, price)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS crawler_health (
                source TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                results_found INTEGER NOT NULL DEFAULT 0,
                detail TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS ai_analysis_cache (
                cache_key TEXT PRIMARY KEY, query TEXT NOT NULL, source TEXT NOT NULL,
                listing_id TEXT NOT NULL, model TEXT NOT NULL, analysis_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        listing_columns = {
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(seen_listings)"
            ).fetchall()
        }

        if "location" not in listing_columns:
            con.execute(
                "ALTER TABLE seen_listings "
                "ADD COLUMN location TEXT"
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
            INSERT INTO watches (
                chat_id,
                query,
                max_price,
                location
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                chat_id,
                query,
                max_price,
                location,
            ),
        )

        return int(cursor.lastrowid)


def get_watches(chat_id: int):
    with connect() as con:
        return con.execute(
            """
            SELECT
                id,
                chat_id,
                query,
                max_price,
                location,
                active,
                initialized,
                created_at,
                last_checked_at
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
                id,
                chat_id,
                query,
                max_price,
                location,
                active,
                initialized,
                created_at,
                last_checked_at
            FROM watches
            WHERE active = 1
            ORDER BY id ASC
            """
        ).fetchall()


def get_watch(
    chat_id: int,
    watch_id: int,
):
    with connect() as con:
        return con.execute(
            """
            SELECT
                id,
                chat_id,
                query,
                max_price,
                location,
                active,
                initialized,
                created_at,
                last_checked_at
            FROM watches
            WHERE chat_id = ? AND id = ?
            """,
            (
                chat_id,
                watch_id,
            ),
        ).fetchone()


def get_latest_watch(chat_id: int):
    with connect() as con:
        return con.execute(
            """
            SELECT
                id,
                chat_id,
                query,
                max_price,
                location,
                active,
                initialized,
                created_at,
                last_checked_at
            FROM watches
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (chat_id,),
        ).fetchone()


def remove_watch(
    chat_id: int,
    watch_id: int,
) -> bool:
    with connect() as con:
        cursor = con.execute(
            """
            DELETE FROM watches
            WHERE chat_id = ? AND id = ?
            """,
            (
                chat_id,
                watch_id,
            ),
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
            WHERE watch_id = ?
              AND source = ?
              AND listing_id = ?
            """,
            (
                watch_id,
                source,
                listing_id,
            ),
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
    location: Optional[str] = None,
) -> None:
    with connect() as con:
        con.execute(
            """
            INSERT INTO seen_listings (
                watch_id,
                source,
                listing_id,
                title,
                price,
                url,
                posted_text,
                location
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                watch_id,
                source,
                listing_id
            )
            DO UPDATE SET
                title = excluded.title,
                price = excluded.price,
                url = excluded.url,
                posted_text = excluded.posted_text,
                location = excluded.location,
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
                location,
            ),
        )


def mark_watch_initialized(
    watch_id: int,
) -> None:
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


def update_watch_checked_time(
    watch_id: int,
) -> None:
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
    limit: int = 40,
):
    with connect() as con:
        return con.execute(
            """
            SELECT
                source,
                listing_id,
                title,
                price,
                url,
                posted_text,
                location,
                first_seen_at,
                last_seen_at
            FROM seen_listings
            WHERE watch_id = ?
            ORDER BY last_seen_at DESC, id DESC
            LIMIT ?
            """,
            (
                watch_id,
                limit,
            ),
        ).fetchall()


def count_seen_listings(
    watch_id: int,
) -> int:
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


def save_market_prices(product_key, listings):
    with connect() as con:
        for listing in listings:
            if listing.price is None: continue
            con.execute("""INSERT OR IGNORE INTO market_prices(product_key,source,location,listing_id,title,price) VALUES(?,?,?,?,?,?)""",(product_key,listing.source,listing.location,listing.listing_id,listing.title,listing.price))

def get_market_prices(product_key, limit=200):
    with connect() as con:
        return con.execute("SELECT price FROM market_prices WHERE product_key=? ORDER BY captured_at DESC LIMIT ?",(product_key,limit)).fetchall()

def get_market_stats(product_key):
    with connect() as con:
        return con.execute("SELECT COUNT(*) samples, MIN(price) minimum_price, MAX(price) maximum_price, AVG(price) average_price FROM market_prices WHERE product_key=?",(product_key,)).fetchone()

def update_crawler_health(source,status,results_found,detail=''):
    with connect() as con:
        con.execute("""INSERT INTO crawler_health(source,status,results_found,detail) VALUES(?,?,?,?) ON CONFLICT(source) DO UPDATE SET status=excluded.status,results_found=excluded.results_found,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP""",(source,status,results_found,detail))

def get_crawler_health():
    with connect() as con:
        return con.execute("SELECT source,status,results_found,detail,updated_at FROM crawler_health ORDER BY source").fetchall()


def get_ai_cache(cache_key: str):
    with connect() as con:
        return con.execute("SELECT * FROM ai_analysis_cache WHERE cache_key=?",(cache_key,)).fetchone()

def save_ai_cache(cache_key,query,source,listing_id,model,analysis_json):
    with connect() as con:
        con.execute("""INSERT INTO ai_analysis_cache(cache_key,query,source,listing_id,model,analysis_json) VALUES(?,?,?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET model=excluded.model,analysis_json=excluded.analysis_json,updated_at=CURRENT_TIMESTAMP""",(cache_key,query,source,listing_id,model,analysis_json))

def count_ai_cache():
    with connect() as con:
        return int(con.execute("SELECT COUNT(*) total FROM ai_analysis_cache").fetchone()["total"])
