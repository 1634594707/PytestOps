from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


class FixtureStore:
    """Convention-based fixture loader.

    Default directory: tests/fixtures
    Supported extensions: .yaml/.yml/.json
    """

    def __init__(self, base_dir: str | Path = "tests/fixtures") -> None:
        self._base_dir = Path(base_dir)

    def load(self, name: str) -> Any:
        candidates = [
            self._base_dir / f"{name}.yaml",
            self._base_dir / f"{name}.yml",
            self._base_dir / f"{name}.json",
        ]
        for p in candidates:
            if not p.exists():
                continue
            raw = p.read_text(encoding="utf-8")
            if p.suffix.lower() in {".yaml", ".yml"}:
                return yaml.safe_load(raw)
            return json.loads(raw)
        raise FileNotFoundError(f"fixture not found: {name} under {self._base_dir}")
