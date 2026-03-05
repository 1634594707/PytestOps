from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
    base_url: str
    timeout_s: float = 60.0


def load_config(path: str | Path) -> AppConfig:
    p = Path(path)
    data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    api = data.get("api", {})
    return AppConfig(
        base_url=str(api.get("base_url", "")),
        timeout_s=float(api.get("timeout_s", 60.0)),
    )
