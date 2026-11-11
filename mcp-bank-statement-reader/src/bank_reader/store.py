"""Local SQLite storage. Nothing leaves your laptop from here.

Data lives in ~/.bank-reader/ by default. Set BANK_READER_HOME to change it.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id          TEXT PRIMARY KEY,
    date        TEXT NOT NULL,
    description TEXT NOT NULL,
    amount      REAL NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('debit', 'credit')),
    balance     REAL,
    merchant    TEXT NOT NULL,
    category    TEXT NOT NULL,
    manual_category INTEGER NOT NULL DEFAULT 0,
    source      TEXT NOT NULL,
    account     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_txn_merchant ON transactions(merchant);

CREATE TABLE IF NOT EXISTS statements (
    source      TEXT PRIMARY KEY,
    account     TEXT NOT NULL DEFAULT '',
    loaded_at   TEXT NOT NULL,
    added       INTEGER NOT NULL,
    first_date  TEXT,
    last_date   TEXT
);
"""


def home() -> Path:
    path = Path(os.environ.get("BANK_READER_HOME", "~/.bank-reader")).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return home() / "transactions.db"


def rules_path() -> Path:
    return home() / "rules.json"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_transactions(rows: list[dict], source: str, account: str) -> tuple[int, int]:
    """Insert rows, skipping ones already stored. Returns (added, skipped)."""
    added = 0
    with connect() as conn:
        for row in rows:
            cur = conn.execute(
                """INSERT OR IGNORE INTO transactions
                   (id, date, description, amount, type, balance, merchant, category, source, account)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["id"], row["date"], row["description"], row["amount"], row["type"],
                 row["balance"], row["merchant"], row["category"], source, account),
            )
            added += cur.rowcount
        dates = [r["date"] for r in rows]
        conn.execute(
            """INSERT INTO statements (source, account, loaded_at, added, first_date, last_date)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(source) DO UPDATE SET
                 loaded_at = excluded.loaded_at, added = statements.added + excluded.added,
                 first_date = excluded.first_date, last_date = excluded.last_date""",
            (source, account, datetime.now().isoformat(timespec="seconds"), added,
             min(dates) if dates else None, max(dates) if dates else None),
        )
    return added, len(rows) - added


def query_transactions(
    month: str = "",
    category: str = "",
    search: str = "",
    txn_type: str = "",
    account: str = "",
    limit: int | None = None,
) -> list[dict]:
    sql = "SELECT * FROM transactions WHERE 1=1"
    params: list = []
    if month:
        sql += " AND substr(date, 1, 7) = ?"
        params.append(month)
    if category:
        sql += " AND lower(category) = lower(?)"
        params.append(category)
    if search:
        sql += " AND (description LIKE ? OR merchant LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if txn_type:
        sql += " AND type = ?"
        params.append(txn_type)
    if account:
        sql += " AND account = ?"
        params.append(account)
    sql += " ORDER BY date DESC, rowid DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def update_category(txn_id: str, category: str, manual: bool) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE transactions SET category = ?, manual_category = ? WHERE id = ?",
            (category, int(manual), txn_id),
        )


def list_statements() -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM statements ORDER BY loaded_at DESC")]


def delete_statement(source: str) -> int:
    with connect() as conn:
        removed = conn.execute("DELETE FROM transactions WHERE source = ?", (source,)).rowcount
        conn.execute("DELETE FROM statements WHERE source = ?", (source,))
    return removed


def clear_all() -> int:
    with connect() as conn:
        removed = conn.execute("DELETE FROM transactions").rowcount
        conn.execute("DELETE FROM statements")
    return removed


def load_rules() -> dict[str, str]:
    path = rules_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return {str(k).upper(): str(v) for k, v in data.items()}


def save_rules(rules: dict[str, str]) -> None:
    rules_path().write_text(json.dumps(rules, indent=2, sort_keys=True))
