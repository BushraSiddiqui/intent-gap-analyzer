"""Lightweight TTL caching for external calls."""
import time
from functools import wraps
from typing import Callable


def _make_key(args: tuple, kwargs: dict):
    def freeze(x):
        if isinstance(x, list):
            return tuple(freeze(i) for i in x)
        if isinstance(x, dict):
            return tuple(sorted((k, freeze(v)) for k, v in x.items()))
        if isinstance(x, set):
            return tuple(sorted(freeze(i) for i in x))
        return x
    return (tuple(freeze(a) for a in args), tuple(sorted((k, freeze(v)) for k, v in kwargs.items())))


def ttl_cache(ttl_seconds: int = 3600) -> Callable:
    """Decorator: cache return value for ttl_seconds. Keyed by args + kwargs."""
    def decorator(fn):
        store: dict = {}

        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = _make_key(args, kwargs)
            now = time.time()
            entry = store.get(key)
            if entry is not None:
                ts, val = entry
                if now - ts < ttl_seconds:
                    return val
            val = fn(*args, **kwargs)
            store[key] = (now, val)
            return val

        wrapper.cache_clear = lambda: store.clear()  # type: ignore[attr-defined]
        wrapper.cache_size = lambda: len(store)  # type: ignore[attr-defined]
        return wrapper

    return decorator
