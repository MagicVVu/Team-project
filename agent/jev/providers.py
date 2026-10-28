"""No provider performs I/O on construction. No automatic provider fallback."""
import asyncio
import hashlib
import json
import re
import time
from pathlib import Path

from .budget import Budget
from .client import Client
from .config import MODEL, CACHE
from .questions import QUESTION_VERSION, validate_response
from .schemas import WireResponse, JevError, Node


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(payload):
    # Object-key canonicalization must not erase option order, which can change model answers.
    orders = {key: list(question["criteria"]) for key, question in payload["questions"].items()
              if question["type"] == "choice"}
    return hashlib.sha256(canonical({"question_version": QUESTION_VERSION, "payload": payload,
                                    "choice_orders": orders}).encode()).hexdigest()


class LiveProvider:
    source = "live"

    def __init__(self, config, *, budget=None, transport=None, recordings=None):
        self.config = config
        self.budget = budget or Budget()
        self.client = Client(config, transport=transport)
        self.recordings = Path(recordings) if recordings is not None else CACHE / "recordings"

    async def ask(self, payload, trace):
        started = time.perf_counter()
        try:
            self.config.require_live()
            if set(payload) != {"model", "state", "questions"} or payload["model"] != MODEL:
                raise JevError("INVALID_MODEL_REQUEST")
            trace.reservation_id, trace.charged_usd = self.budget.reserve()
            trace.attempted = True
            response = await self.client.ask(payload)
            trace.charged_usd = self.budget.settle(trace.reservation_id, response.usage.input_tokens)
            trace.usage_measured = True
            trace.input_tokens = response.usage.input_tokens
            trace.output_tokens = response.usage.output_tokens
            trace.model, trace.status = response.model, "ok"
            try:
                self.recordings.mkdir(parents=True, exist_ok=True)
                # Immutable first recording; no key or original state is saved.
                path = self.recordings / (trace.fingerprint + ".json")
                with path.open("x", encoding="utf-8") as handle:
                    handle.write(canonical({"source": "live", "question_version": QUESTION_VERSION,
                        "fingerprint": trace.fingerprint, "response": response.model_dump(mode="json")}))
            except FileExistsError:
                pass
            except OSError:
                trace.recording_error = "RECORDING_UNAVAILABLE"
            return response
        except JevError as error:
            trace.status, trace.error_code = "error", error.code
            raise
        except asyncio.CancelledError:
            trace.status, trace.error_code = "error", "TOTAL_TIMEOUT"
            raise
        finally:
            trace.elapsed_ms = (time.perf_counter() - started) * 1000


class ReplayProvider:
    source = "replay"

    def __init__(self, recordings=None):
        self.recordings = Path(recordings) if recordings is not None else CACHE / "recordings"

    async def ask(self, payload, trace):
        started = time.perf_counter()
        try:
            path = self.recordings / (trace.fingerprint + ".json")
            if not path.is_file():
                raise JevError("REPLAY_MISS")
            try:
                if path.stat().st_size > 1_000_000:
                    raise ValueError("oversized")
                record = json.loads(path.read_text(encoding="utf-8"))
                if (record["fingerprint"] != trace.fingerprint or record["source"] != "live"
                        or record["question_version"] != QUESTION_VERSION):
                    raise ValueError("record mismatch")
                result = validate_response(WireResponse.model_validate(record["response"]), payload)
            except (ValueError, TypeError, KeyError, OSError):
                raise JevError("INVALID_REPLAY") from None
            trace.status, trace.model = "ok", result.model
            trace.input_tokens, trace.output_tokens = result.usage.input_tokens, result.usage.output_tokens
            return result
        except JevError as error:
            trace.status, trace.error_code = "error", error.code
            raise
        finally:
            trace.elapsed_ms = (time.perf_counter() - started) * 1000


def literal_prediction(text):
    """Small, intentionally incomplete offline baseline, NOT a Jev emulator."""
    speech = "REQUEST"
    if re.search(r"不要|别把|假如|如果|没喝完|没用完|没有喝完|没有用完|不是", text):
        return "QUERY_INVENTORY", "NONE", "NEGATED", False
    if re.search(r"和.+(?:都|各)|再把|然后|顺便|三袋面包", text):
        return "UNKNOWN", "UNKNOWN", "REQUEST", True
    if re.search(r"准备买|打算买|明天买|计划买", text):
        return "SUGGEST_PURCHASE", "NONE", "PLAN", False
    for pattern, intent in [
        (r"关注|库存摘要|库存概览", "QUERY_OVERVIEW"),
        (r"冰箱.*(?:有什么|有哪些)", "QUERY_LOCATION_ITEMS"),
        (r"什么时候.*(?:用完|喝完)|还能用几天|多久用完", "QUERY_FORECAST"),
        (r"消耗统计|最近.*用了多少|上周.*消耗", "QUERY_CONSUMPTION"),
        (r"要不要买|需要补货|该买|还要买", "SUGGEST_PURCHASE"),
        (r"过期|安全吗|保存条件|临期", "QUERY_RISK"),
        (r"在哪|放哪里|什么地方", "QUERY_LOCATION"),
        (r"还有|剩多少|库存多少|用完了吗|喝完了吗|是不是.*完", "QUERY_INVENTORY"),
    ]:
        if re.search(pattern, text): return intent, "NONE", "QUESTION", False
    for pattern, intent, event in [
        (r"清单|待购", "PLAN_ADD", "NONE"),
        (r"扔掉|丢弃|倒掉|报废", "DISCARD", "DISCARDED"),
        (r"移到|移动|挪到", "MOVE", "MOVED"),
        (r"开封|打开了", "OPEN", "OPENED"),
        (r"用完了|喝完了|吃完了", "CONSUME", "FINISHED"),
        (r"喝掉|用掉|消耗|吃掉|减去", "CONSUME", "CONSUMED"),
        (r"买了|购入|入库|新增|添加", "ADD", "ADDED"),
    ]:
        if re.search(pattern, text): return intent, event, "FACT" if "了" in text else speech, False
    return "UNSUPPORTED", "NONE", "UNKNOWN", False


class MockProvider:
    source = "mock"

    def __init__(self, *, overrides=None):
        self.overrides = overrides or {}

    async def ask(self, payload, trace):
        started = time.perf_counter()
        state = payload["state"]
        intent, event, speech, multiple = literal_prediction(state["text"])
        values = {Node.INTENT.value: intent, Node.EVENT.value: event, "speech_act": speech,
                  "multiple_actions": 1.0 if multiple else 0.0}
        reasons = state.get("hard_reasons", [])
        from .policy import WRITE, WAIT_REASONS
        clarification = "CLARIFY" if reasons else "PASS"
        action = "WAIT" if WAIT_REASONS.intersection(reasons) else "CLARIFY" if reasons else "CONFIRM" if intent in WRITE else "READ"
        values.update({Node.CLARIFICATION.value: clarification, Node.ACTION.value: action})
        values.update(self.overrides)
        answers = {}
        for key, question in payload["questions"].items():
            value = values[key]
            if question["type"] == "noul":
                answers[key] = {"type": "noul", "noul": float(value)}
            else:
                answers[key] = {"type": "choice", "choice": value, "confidence": 1.0,
                                "probabilities": {option: float(option == value) for option in question["criteria"]}}
        response = validate_response(WireResponse.model_validate({"model": MODEL, "answers": answers,
                                                                 "usage": {"input_tokens": 0, "output_tokens": 0}}), payload)
        trace.status = "ok"
        trace.elapsed_ms = (time.perf_counter() - started) * 1000
        return response
