from __future__ import annotations

import datetime
import random


def now_iso() -> str:
    return datetime.datetime.now().isoformat()


def rand_int(a: str = "0", b: str = "100") -> int:
    try:
        lo = int(a)
    except Exception:
        lo = 0
    try:
        hi = int(b)
    except Exception:
        hi = 100
    if lo > hi:
        lo, hi = hi, lo
    return random.randint(lo, hi)


FUNCTIONS = {
    "now_iso": now_iso,
    "rand_int": rand_int,
}
