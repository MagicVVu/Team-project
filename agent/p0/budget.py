"""Persistent conservative reservations survive crashes and concurrent processes."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from .engines import EngineError


class Budget:
    def __init__(self, path: Path, pricing_path: Path, limit: Decimal = Decimal("20")):
        self.path, self.pricing_path, self.limit = path, pricing_path, limit
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, reserved REAL, actual REAL, status TEXT, created_at TEXT)")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def pricing(self, model: str) -> dict:
        pricing = json.loads(self.pricing_path.read_text(encoding="utf-8"))
        # Verification dates are audit metadata, not a runtime expiry gate.
        if model != pricing["model"]:
            raise EngineError("PRICING_NOT_VERIFIED")
        return pricing

    def reserve(self, model: str, input_bound: int, output_bound: int) -> tuple[str, Decimal, dict]:
        pricing = self.pricing(model)
        amount = (Decimal(str(pricing["input_cny_per_million"])) * input_bound +
                  Decimal(str(pricing["output_cny_per_million"])) * output_bound) / Decimal(1000000)
        call_id = uuid4().hex
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            used = Decimal(str(db.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM calls").fetchone()[0]))
            if used + amount > self.limit:
                raise EngineError("BUDGET_EXCEEDED")
            db.execute("INSERT INTO calls VALUES (?,?,NULL,'reserved',?)", (call_id, float(amount), datetime.now(timezone.utc).isoformat()))
        return call_id, amount, pricing

    def settle(self, call_id: str, usage: dict, pricing: dict):
        # Peak, cache-miss rates deliberately overestimate the actual invoice.
        prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if not isinstance(prompt, int) or not isinstance(completion, int) or min(prompt, completion) < 0:
            return  # Unknown billed usage keeps the entire reservation charged.
        actual = (Decimal(prompt) * Decimal(str(pricing["input_cny_per_million"])) +
                  Decimal(completion) * Decimal(str(pricing["output_cny_per_million"]))) / Decimal(1000000)
        with self.connection() as db:
            db.execute("UPDATE calls SET actual=?,status='measured' WHERE id=?", (float(actual), call_id))

    def summary(self) -> dict:
        with self.connection() as db:
            used, calls, pending = db.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved)),0), COUNT(*), SUM(actual IS NULL) FROM calls").fetchone()
        return {"limit_cny": float(self.limit), "conservative_cost_cny": used, "calls": calls, "unknown_usage_calls": pending or 0}
