import asyncio
import json
import os
from pathlib import Path
from typing import Callable

import httpx

from .budget import Budget
from .engines import EngineError, SYSTEM_PROMPT, parse_json_output
from .schemas import Parsed

ROOT = Path(__file__).resolve().parents[1]


class DeepSeekEngine:
    def __init__(self, budget: Budget | None = None, *, system_prompt: str = SYSTEM_PROMPT,
                 output_parser: Callable = parse_json_output, timeout_seconds=10,
                 max_tokens=768, max_input_bytes=16000):
        self.budget = budget or Budget(ROOT / ".cache/p0/budget.sqlite", ROOT / "eval/pricing.json")
        self.system_prompt, self.output_parser = system_prompt, output_parser
        self.timeout_seconds, self.max_tokens, self.max_input_bytes = timeout_seconds, max_tokens, max_input_bytes
        self.model = os.getenv("LLM_MODEL", "deepseek-flash")
        self.last_usage: dict = {}
        self.last_model: str | None = None

    async def extract(self, text: str) -> Parsed:
        self.last_usage, self.last_model = {}, None
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise EngineError("MODEL_NOT_CONFIGURED")
        payload = {"model": self.model, "messages": [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": text}],
                   "response_format": {"type": "json_object"}, "max_tokens": self.max_tokens,
                   "thinking": {"type": "disabled"}, "stream": False}
        body_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if body_size > self.max_input_bytes:
            raise EngineError("MODEL_INPUT_TOO_LARGE")
        call_id, _, pricing = self.budget.reserve(self.model, body_size + 1024, self.max_tokens)
        try:
            # Wall-clock cap includes DNS, connect, send, and read; no hidden SDK retries.
            async with asyncio.timeout(self.timeout_seconds):
                async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
                    response = await client.post("https://api.deepseek.com/chat/completions", json=payload,
                                                 headers={"Authorization": f"Bearer {key}"})
                    if response.status_code != 200:
                        raise EngineError(f"MODEL_HTTP_{response.status_code}")
                    data = response.json()
            self.last_usage = data.get("usage", {})
            self.last_model = data.get("model")
            self.budget.settle(call_id, self.last_usage, pricing)
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise EngineError("EMPTY_MODEL_OUTPUT")
            return self.output_parser(content)
        except (TimeoutError, httpx.TimeoutException):
            raise EngineError("MODEL_TIMEOUT") from None
        except httpx.HTTPError:
            raise EngineError("MODEL_UNAVAILABLE") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise EngineError("INVALID_MODEL_OUTPUT") from None
