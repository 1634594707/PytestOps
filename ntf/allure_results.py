from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AllureAttachment:
    name: str
    source: str
    type: str


class AllureResultsWriter:
    def __init__(self, results_dir: str | Path) -> None:
        self._dir = Path(results_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def write_case_result(
        self,
        *,
        suite_name: str,
        case_name: str,
        file_path: str,
        status: str,
        start_ms: int,
        stop_ms: int,
        status_details: dict[str, Any] | None = None,
        attachments: list[tuple[str, str, str]] | None = None,
        steps: list[dict[str, Any]] | None = None,
    ) -> str:
        test_uuid = str(uuid.uuid4())

        allure_attachments: list[AllureAttachment] = []
        for item in attachments or []:
            att_name, att_type, content = item
            source = self._write_attachment(content, mime_type=att_type)
            allure_attachments.append(AllureAttachment(name=att_name, source=source, type=att_type))

        result: dict[str, Any] = {
            "uuid": test_uuid,
            "name": case_name,
            "fullName": f"{suite_name}::{case_name}",
            "status": status,
            "statusDetails": status_details,
            "stage": "finished",
            "start": start_ms,
            "stop": stop_ms,
            "labels": [
                {"name": "suite", "value": suite_name},
                {"name": "parentSuite", "value": "run-yaml"},
                {"name": "epic", "value": os.path.basename(file_path)},
            ],
            "attachments": [a.__dict__ for a in allure_attachments],
            "steps": steps or [],
            "parameters": [],
        }

        out = self._dir / f"{test_uuid}-result.json"
        out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return test_uuid

    def _write_attachment(self, content: str, *, mime_type: str) -> str:
        att_uuid = str(uuid.uuid4())
        ext = self._guess_ext(mime_type)
        source = f"{att_uuid}-attachment{ext}"
        p = self._dir / source
        p.write_text(content, encoding="utf-8")
        return source

    def _guess_ext(self, mime_type: str) -> str:
        mt = (mime_type or "").lower()
        if "json" in mt:
            return ".json"
        if "html" in mt:
            return ".html"
        return ".txt"


def now_ms() -> int:
    return int(time.time() * 1000)
