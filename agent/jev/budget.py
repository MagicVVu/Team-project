"""Atomic, persistent USD reservations; independent of the DeepSeek ledger."""
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from .config import (CACHE, MODEL, PRICE_VERSION, MAX_INPUT_TOKENS,
                     NANODOLLARS_PER_TOKEN, BUDGET_NANODOLLARS)
from .schemas import JevError

NANO = Decimal(1_000_000_000)
RESERVATION = MAX_INPUT_TOKENS * NANODOLLARS_PER_TOKEN


class Budget:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else CACHE / "budget.sqlite"

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=0.2)
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                db.execute("CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, reserved INTEGER NOT NULL, actual INTEGER, input_tokens INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
                expected = {"model": MODEL, "price": PRICE_VERSION, "limit": str(BUDGET_NANODOLLARS)}
                for key, value in expected.items():
                    db.execute("INSERT OR IGNORE INTO metadata VALUES (?,?)", (key, value))
                if dict(db.execute("SELECT key,value FROM metadata")) != expected:
                    raise JevError("BUDGET_METADATA_MISMATCH")
            yield db
        except sqlite3.Error:
            raise JevError("BUDGET_UNAVAILABLE") from None
        finally:
            db.close()

    def reserve(self):
        with self.connection() as db, db:
            db.execute("BEGIN IMMEDIATE")
            used = db.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM calls").fetchone()[0]
            if used + RESERVATION > BUDGET_NANODOLLARS:
                raise JevError("BUDGET_EXCEEDED")
            call_id = uuid4().hex
            db.execute("INSERT INTO calls(id,reserved) VALUES (?,?)", (call_id, RESERVATION))
        return call_id, Decimal(RESERVATION) / NANO

    def settle(self, call_id, input_tokens):
        if type(input_tokens) is not int or not 0 <= input_tokens <= MAX_INPUT_TOKENS:
            raise JevError("INVALID_USAGE")
        amount = input_tokens * NANODOLLARS_PER_TOKEN
        with self.connection() as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT actual FROM calls WHERE id=?", (call_id,)).fetchone()
            if row is None:
                raise JevError("RESERVATION_NOT_FOUND")
            if row[0] is not None and row[0] != amount:
                raise JevError("RESERVATION_ALREADY_SETTLED")
            db.execute("UPDATE calls SET actual=?,input_tokens=? WHERE id=?", (amount, input_tokens, call_id))
        return Decimal(amount) / NANO

    def summary(self):
        result = {"currency": "USD", "limit_usd": "1", "price_version": PRICE_VERSION,
                  "charged_or_reserved_usd": "0", "calls": 0, "unknown_usage_calls": 0}
        if not self.path.exists():
            return result
        try:
            with sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2) as db:
                row = db.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved)),0),COUNT(*),COALESCE(SUM(actual IS NULL),0) FROM calls").fetchone()
                if dict(db.execute("SELECT key,value FROM metadata")) != {"model": MODEL, "price": PRICE_VERSION, "limit": str(BUDGET_NANODOLLARS)}:
                    raise JevError("BUDGET_METADATA_MISMATCH")
        except sqlite3.Error:
            raise JevError("BUDGET_UNAVAILABLE") from None
        result.update(charged_or_reserved_usd=str(Decimal(row[0]) / NANO), calls=row[1], unknown_usage_calls=row[2])
        return result
