"""Bounded, atomic admission control for the supported single-worker backend.

Count *attempts*, including successful ones, independently of account existence.
State is deliberately process-local: replicas/workers need a shared limiter.
Never take an IP from HTTP headers; the optional edge enforces real-client IPs.
"""

from collections import deque
from contextlib import contextmanager
from hashlib import sha256
from math import ceil
from threading import Lock
from time import monotonic

from fastapi import HTTPException


class LoginGuard:
    def __init__(self, *, ip_limit=30, account_limit=8, global_limit=120,
                 ip_window=60, account_window=300, max_inflight=4,
                 max_keys=4096, clock=monotonic):
        self.ip_limit, self.account_limit = ip_limit, account_limit
        self.global_limit = global_limit
        self.ip_window, self.account_window = ip_window, account_window
        self.max_inflight, self.max_keys = max_inflight, max_keys
        self.clock = clock
        self._lock = Lock()
        self._buckets = {}
        self._inflight = 0

    @staticmethod
    def _reject(seconds):
        raise HTTPException(429, "Too many login attempts; try again later",
                            headers={"Retry-After": str(max(1, ceil(seconds))),
                                     "Cache-Control": "no-store"})

    def _reserve(self, peer, phone):
        now = self.clock()
        # Hash identifiers so limiter state does not retain phone numbers.
        keys = [("global", self.global_limit, self.ip_window),
                ("ip:" + sha256(peer.encode()).hexdigest(), self.ip_limit, self.ip_window),
                ("account:" + sha256(phone.encode()).hexdigest(), self.account_limit, self.account_window)]
        with self._lock:
            for key, (events, window) in list(self._buckets.items()):
                while events and events[0] <= now - window:
                    events.popleft()
                if not events:
                    del self._buckets[key]
            waits = [self._buckets[key][0][0] + window - now
                     for key, limit, window in keys
                     if key in self._buckets and len(self._buckets[key][0]) >= limit]
            if waits:
                self._reject(max(waits))
            if self._inflight >= self.max_inflight:
                self._reject(1)
            missing = sum(key not in self._buckets for key, _, _ in keys)
            if len(self._buckets) + missing > self.max_keys:
                # Do not evict live keys: rotating accounts/IPs must not reset limits.
                self._reject(1)
            for key, _, window in keys:
                events, _ = self._buckets.setdefault(key, (deque(), window))
                events.append(now)
            self._inflight += 1

    @contextmanager
    def attempt(self, peer, phone):
        self._reserve(peer, phone)
        try:
            yield
        finally:
            with self._lock:
                self._inflight -= 1
