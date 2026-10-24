"""Exactly one POST per call, fixed endpoint/version, no redirects or retries."""
import asyncio

import httpx
from pydantic import ValidationError

from .config import ENDPOINT, MODEL
from .questions import validate_response
from .schemas import WireResponse, JevError


class Client:
    def __init__(self, config, *, transport=None):
        self.config = config
        self.transport = transport

    async def ask(self, payload):
        self.config.require_live()
        if set(payload) != {"model", "state", "questions"} or payload["model"] != MODEL:
            raise JevError("INVALID_MODEL_REQUEST")
        try:
            async with asyncio.timeout(self.config.timeout_seconds):
                async with httpx.AsyncClient(transport=self.transport, timeout=self.config.timeout_seconds,
                                            trust_env=False, follow_redirects=False) as client:
                    response = await client.post(ENDPOINT, json=payload,
                        headers={"Authorization": "Bearer " + self.config.api_key, "Content-Type": "application/json"})
                    if response.status_code != 200:
                        raise JevError("MODEL_RATE_LIMITED" if response.status_code == 429 else f"MODEL_HTTP_{response.status_code}")
                    # Avoid unbounded malformed provider responses.
                    if len(response.content) > 1_000_000:
                        raise JevError("MODEL_RESPONSE_TOO_LARGE")
                    parsed = WireResponse.model_validate_json(response.content)
                    return validate_response(parsed, payload)
        except (TimeoutError, httpx.TimeoutException):
            raise JevError("MODEL_TIMEOUT") from None
        except httpx.HTTPError:
            raise JevError("MODEL_UNAVAILABLE") from None
        except (ValidationError, ValueError, TypeError):
            raise JevError("INVALID_MODEL_RESPONSE") from None
