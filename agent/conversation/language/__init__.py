"""Language preferences affect expression and literal parsing, never authority."""
from contextvars import ContextVar
from contextlib import contextmanager

PROTOCOL = "assistant-language-1"
SUPPORTED = ("zh-CN", "en")
current = ContextVar("assistant_locale", default="zh-CN")


@contextmanager
def using(locale):
    if locale not in SUPPORTED: raise ValueError("Unsupported assistant locale")
    token=current.set(locale)
    try: yield
    finally: current.reset(token)


def choose(chinese, english):
    return english if current.get()=="en" else chinese
