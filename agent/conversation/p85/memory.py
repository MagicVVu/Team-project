"""Bounded lexical retrieval. Text is remembered; facts must be read again.

Original implementation using BM25-style term saturation and Chinese bigrams;
no vector database, background LLM, filesystem store or remote memory service.
"""
import hashlib
import json
import math
import re
from collections import Counter

from p0.domain import DomainError
from ..dialogue import checked
from ..memory import explain_state
from .schemas import P85MemoryUse, P85MemoryDelta, P85Episode, P85Subject


def terms(text):
    result = []
    for chunk in re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+", text.lower()):
        result.extend([chunk] if chunk.isascii() or len(chunk) < 2 else
                      [chunk[i:i+2] for i in range(len(chunk)-1)])
    return Counter(result)


def prepare(owner, body, scope):
    ctx = checked(owner, body, scope)
    episodes = body.archive.episodes if body.archive else []
    # Do not spend the model's memory budget repeating the recent window.
    recent = {t.request_id for t in ctx.history}
    pool = [e for e in episodes if e.request_id not in recent]
    query = terms(body.text)
    docs = [terms(e.text + " " + " ".join(s.name for s in e.subjects)) for e in pool]
    avg = sum(sum(d.values()) for d in docs) / max(1, len(docs)) or 1
    df = Counter(term for d in docs for term in d)
    recall = bool(re.search(r"刚才|之前|接着|继续|上次|还记得|最早|聊过|说过|回到|最开始|一开始|开头", body.text))
    earliest = bool(re.search(r"最早|最开始|一开始|开头", body.text))
    ranked = []
    for e, doc in zip(pool, docs):
        score = 0.0
        for term in query.keys() & doc.keys():
            idf = math.log(1+(len(docs)-df[term]+.5)/(df[term]+.5))
            score += idf*doc[term]*2.2/(doc[term]+1.2*(.25+.75*sum(doc.values())/avg))
        score += sum(6 for s in e.subjects if s.name in body.text)
        # Generic recall can see recent episodes; unrelated topics are not forced in.
        if score > 0 or recall:
            ranked.append((score, e.created_at, e.memory_id, e))
    ranked.sort(key=lambda x: (x[0], -x[1].timestamp() if earliest else x[1].timestamp(), x[2]), reverse=True)
    chosen = []
    budget = 14000
    for *_, episode in ranked[:8]:
        size = len(episode.model_dump_json().encode())
        if size <= budget:
            chosen.append(episode)
            budget -= size
    # Timeline is explicit; relevance score does not imply chronological order.
    chosen.sort(key=lambda e: (e.created_at, e.memory_id))
    summary = {
        "active_task": {"task_id": str(ctx.active.task.task_id), "revision": ctx.active.task.revision,
                        "status": ctx.active.task.status,
                        "missing_fields": list(ctx.active.task.result.missing_fields) if ctx.active.task.result else []}
                       if ctx.active else None,
        "task_states": [{"task_id": str(t.task_id), "revision": t.revision,
                         "explanation": explain_state(t)} for t in ctx.tasks],
        "recent_object_available": ctx.reference is not None,
        "history_is_not_current_inventory": True,
        "retrieval_strategy": "lexical_then_earliest" if earliest else "lexical_then_recent",
    }
    base = len(ctx.model_dump_json().encode()) + len(json.dumps(summary, ensure_ascii=False).encode())
    while chosen and base + sum(len(e.model_dump_json().encode()) for e in chosen) > 34000:
        # Drop least relevant first, preserving the surviving temporal order.
        weakest = min(chosen, key=lambda e: next((s, t, i) for s, t, i, v in ranked if v.memory_id == e.memory_id))
        chosen.remove(weakest)
    if base > 34000:
        # Never silently delete candidate lists or active task evidence.
        while ctx.history and base > 34000:
            ctx.history.pop(0)
            ctx.truncated = True
            base = len(ctx.model_dump_json().encode()) + len(json.dumps(summary, ensure_ascii=False).encode())
        if base > 34000:
            raise DomainError("MEMORY_CONTEXT_TOO_LARGE", "当前任务资料超出预算，请进入原任务核对。", 422)
    omitted = len(pool)-len(chosen)
    use = P85MemoryUse(selected_ids=[e.memory_id for e in chosen], omitted_episodes=omitted,
                       truncated=ctx.truncated or omitted > 0 or bool(body.archive and body.archive.has_more),
                       archive_available=body.archive is not None, summary=summary)
    return ctx, chosen, use


def delta(body, frame):
    # Only literal names are indexed. Historical replies remain historical prose,
    # never promoted to a stock fact or execution receipt.
    names = []
    plan = body.plan
    if plan.selector.name and plan.selector.name in body.text:
        names.append(plan.selector.name)
    if "name" in plan.fields:
        item = plan.fields["name"]
        if item.source == "current_text" and item.quote in body.text and item.value in item.quote:
            names.append(item.value)
    key = json.dumps([body.context.scope.model_dump(), str(body.context.conversation_id), body.request_id], sort_keys=True)
    episode = P85Episode(memory_id="mem_"+hashlib.sha256(key.encode()).hexdigest()[:32], request_id=body.request_id,
                         text=body.text, reply=frame.reply[:8000], created_at=body.context.trusted_now,
                         subjects=[P85Subject(name=n, quote=n) for n in dict.fromkeys(names)])
    return P85MemoryDelta(scope=body.context.scope, conversation_id=body.context.conversation_id,
                          expected_revision=body.context.revision, episode=episode,
                          source_text_sha256=hashlib.sha256(body.text.encode()).hexdigest())
