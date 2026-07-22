import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from amazon_mcp.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracked_products (
    asin TEXT PRIMARY KEY,
    label TEXT,
    url TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asin TEXT NOT NULL,
    price REAL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    in_stock INTEGER NOT NULL DEFAULT 1,
    scraped_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_asin ON price_history(asin, scraped_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def add_tracked(conn, asin: str, url: str, label: str | None = None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tracked_products (asin, label, url, created_at) VALUES (?,?,?,?)",
        (asin, label, url, _now()),
    )
    conn.commit()


def remove_tracked(conn, asin: str) -> bool:
    cur = conn.execute("DELETE FROM tracked_products WHERE asin = ?", (asin,))
    conn.commit()
    return cur.rowcount > 0


def is_tracked(conn, asin: str) -> bool:
    return conn.execute("SELECT 1 FROM tracked_products WHERE asin = ?", (asin,)).fetchone() is not None


def record_price(conn, asin: str, price: float | None, currency: str = "EUR", in_stock: bool = True) -> None:
    conn.execute(
        "INSERT INTO price_history (asin, price, currency, in_stock, scraped_at) VALUES (?,?,?,?,?)",
        (asin, price, currency, int(in_stock), _now()),
    )
    conn.commit()


def list_tracked(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM tracked_products ORDER BY created_at").fetchall()
    out = []
    for r in rows:
        hist = conn.execute(
            "SELECT price, scraped_at FROM price_history WHERE asin = ? ORDER BY scraped_at DESC, id DESC LIMIT 2",
            (r["asin"],),
        ).fetchall()
        out.append({
            "asin": r["asin"],
            "label": r["label"],
            "url": r["url"],
            "created_at": r["created_at"],
            "last_price": hist[0]["price"] if hist else None,
            "previous_price": hist[1]["price"] if len(hist) > 1 else None,
            "last_scraped_at": hist[0]["scraped_at"] if hist else None,
        })
    return out


def price_history(conn, asin: str, days: int = 30) -> list[dict]:
    rows = conn.execute(
        "SELECT price, currency, in_stock, scraped_at FROM price_history "
        "WHERE asin = ? AND scraped_at >= datetime('now', ?) ORDER BY scraped_at, id",
        (asin, f"-{int(days)} days"),
    ).fetchall()
    return [
        {"price": r["price"], "currency": r["currency"], "in_stock": bool(r["in_stock"]), "scraped_at": r["scraped_at"]}
        for r in rows
    ]
