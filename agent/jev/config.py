"""No environment access until an explicit check/live operation."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from .schemas import JevError

MODEL = "jev-1.13.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MAX_INPUT_TOKENS = 65_536
NANODOLLARS_PER_TOKEN = 42
BUDGET_NANODOLLARS = 1_000_000_000
PRICE_VERSION = "typesafe-2026-10-23-usd-0.042-per-million"
CACHE = Path(__file__).resolve().parent / ".cache"


@dataclass(frozen=True)
class Config:
    api_key: str = field(default="", repr=False)
    timeout_seconds: float = 4.0

    def __post_init__(self):
        if not 0 < self.timeout_seconds <= 4:
            raise JevError("INVALID_TIMEOUT")
        if self.api_key and (not self.api_key.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in self.api_key)):
            raise JevError("INVALID_API_KEY")

    @classmethod
    def from_environment(cls):
        return cls(api_key=os.getenv("TYPESAFE_API_KEY", "").strip())

    def require_live(self):
        if not self.api_key:
            raise JevError("MODEL_NOT_CONFIGURED")
