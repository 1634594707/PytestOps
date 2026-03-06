from __future__ import annotations

import random
import string
import time
import uuid


def unique_id(prefix: str = "id") -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def random_str(length: int = 8, *, alphabet: str | None = None) -> str:
    n = max(1, int(length))
    chars = alphabet or (string.ascii_lowercase + string.digits)
    return "".join(random.choice(chars) for _ in range(n))


def random_email(prefix: str = "user", domain: str = "example.test") -> str:
    return f"{prefix}_{random_str(8)}@{domain}"


def random_phone() -> str:
    head = random.choice(["13", "15", "17", "18", "19"])
    return head + "".join(random.choice(string.digits) for _ in range(9))
