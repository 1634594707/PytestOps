from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def print_report(summary: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    print("[ntf-sample-plugin] summary:", summary)
    if failures:
        print("[ntf-sample-plugin] failures:", len(failures))

    out_path = os.getenv("NTF_SAMPLE_REPORT")
    if not out_path:
        return
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "failures": failures}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
