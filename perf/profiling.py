# perf/profiling.py
#
# Phase 0 of REQUEST_PATH_OPTIMIZATION_PROMPTS.md: an opt-in timing shim for the request
# path. Disabled by default -- set PROFILE_REQUESTS=1 in the environment to turn it on.
#
# When disabled, `timed()` hands back the original function completely unwrapped, so
# there is no per-call overhead (not even an `if`) added to the hot path -- this module
# is scaffolding for measurement, not a feature.
#
# Counters are thread-local so a benchmark script can drive flows sequentially (Flask's
# dev/test client runs each request on the calling thread) and call reset()/snapshot()
# around each one without cross-flow contamination.

import os
import time
import functools
import threading

ENABLED = os.environ.get('PROFILE_REQUESTS', '') not in ('', '0', 'false', 'False')

_local = threading.local()

# Per-request log, appended to by app.py's after_request hook when ENABLED. Each entry is
# {'method', 'path', 'elapsed', 'counters'} -- a benchmark script can drive several requests
# for one flow, then read/clear this to aggregate call counts across the whole flow (the
# thread-local counters above are reset every request for clean per-request numbers).
REQUEST_LOG = []


def _counters() -> dict:
    if not hasattr(_local, 'counters'):
        _local.counters = {}
    return _local.counters


def reset() -> None:
    """Clear this thread's counters. Call at the start of a request or a benchmark flow."""
    _local.counters = {}


def snapshot() -> dict:
    """Return a shallow copy of this thread's counters: {label: {'count', 'total'}}."""
    return {label: dict(stats) for label, stats in _counters().items()}


def timed(label):
    """Decorator recording call count + wall time for `label` under PROFILE_REQUESTS=1.

    No-op (returns fn unchanged) when profiling is disabled -- callers pay zero cost.
    """
    def decorator(fn):
        if not ENABLED:
            return fn

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                entry = _counters().setdefault(label, {'count': 0, 'total': 0.0})
                entry['count'] += 1
                entry['total'] += elapsed
                print('[PROFILE] {} #{} took {:.2f}ms (running total {:.2f}ms)'.format(
                    label, entry['count'], elapsed * 1000, entry['total'] * 1000))
        return wrapper
    return decorator


class span:
    """Context manager twin of `timed()`, for timing a block rather than a whole function
    (e.g. total request time around a Flask before/after_request pair). No-op when
    profiling is disabled.
    """
    __slots__ = ('label', '_start')

    def __init__(self, label):
        self.label = label

    def __enter__(self):
        if ENABLED:
            self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        if not ENABLED:
            return False
        elapsed = time.perf_counter() - self._start
        entry = _counters().setdefault(self.label, {'count': 0, 'total': 0.0})
        entry['count'] += 1
        entry['total'] += elapsed
        print('[PROFILE] {} #{} took {:.2f}ms (running total {:.2f}ms)'.format(
            self.label, entry['count'], elapsed * 1000, entry['total'] * 1000))
        return False
