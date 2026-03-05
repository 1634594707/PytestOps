from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import jsonpath

from ntf.assertions import AssertionEngine
from ntf.extract import ExtractStore
from ntf.renderer import RenderContext, Renderer
from ntf.http import HttpResponse, Transport


@dataclass(frozen=True)
class ExecuteResult:
    response: HttpResponse


class RequestExecutor:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float,
        transport: Transport,
        extract_store: ExtractStore,
        assertion_engine: AssertionEngine | None = None,
        functions: Any | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._transport = transport
        self._store = extract_store
        self._assertions = assertion_engine or AssertionEngine()
        self._renderer = Renderer(RenderContext(extract_store=self._store), functions=functions)

    def execute(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        cookies: dict[str, Any] | None = None,
        request_kwargs: dict[str, Any] | None = None,
        extract: dict[str, str] | None = None,
        extract_list: dict[str, str] | None = None,
        validation: list[dict[str, Any]] | None = None,
    ) -> ExecuteResult:
        full_url = url
        if url.startswith("/"):
            full_url = f"{self._base_url}{url}"
        elif not url.startswith("http"):
            full_url = f"{self._base_url}/{url}"

        headers = self._renderer.render(headers) if headers else None
        cookies = self._renderer.render(cookies) if cookies else None
        request_kwargs = self._renderer.render(request_kwargs or {})

        r = self._transport.request(
            method=method,
            url=full_url,
            headers=headers,
            cookies=cookies,
            params=request_kwargs.get("params"),
            data=request_kwargs.get("data"),
            json=request_kwargs.get("json"),
            timeout_s=self._timeout_s,
        )

        r = self._normalize_response(r)

        if extract:
            self._apply_extract(extract, r)

        if extract_list:
            self._apply_extract_list(extract_list, r)

        if validation is not None:
            actual_json = r.json_data if r.json_data is not None else {}
            self._assertions.assert_all(validation, actual_json, r.status_code)

        return ExecuteResult(response=r)

    def _normalize_response(self, r: HttpResponse) -> HttpResponse:
        """Normalize legacy mock responses.

        Some legacy mocks return a JSON string inside the 'data' field.
        For compatibility, parse it and merge its keys to top-level.
        """

        j = r.json_data
        if not isinstance(j, dict):
            return r

        data = j.get("data")
        if isinstance(data, str):
            s = data.strip()
            if s.startswith("{") and s.endswith("}"):
                try:
                    parsed = json.loads(s)
                except Exception:
                    parsed = None
                if isinstance(parsed, dict):
                    j["data"] = parsed
                    for k, v in parsed.items():
                        if k not in j:
                            j[k] = v

        return HttpResponse(status_code=r.status_code, text=r.text, json_data=j)

    def _apply_extract(self, rules: dict[str, str], r: HttpResponse) -> None:
        text = r.text
        j = r.json_data

        for k, expr in rules.items():
            if expr is None:
                continue

            if isinstance(expr, str) and expr.strip().startswith("$") and j is not None:
                values = jsonpath.jsonpath(j, expr)
                if values is False:
                    values = []
                self._store.set(k, values[0] if values else None)
                continue

            if isinstance(expr, str):
                m = re.search(expr, text)
                if not m and "\\\\" in expr:
                    m = re.search(expr.replace("\\\\", "\\"), text)
                self._store.set(k, m.group(1) if m else None)
                continue

            self._store.set(k, None)

    def _apply_extract_list(self, rules: dict[str, str], r: HttpResponse) -> None:
        text = r.text
        j = r.json_data

        for k, expr in rules.items():
            if expr is None:
                continue

            if isinstance(expr, str) and expr.strip().startswith("$") and j is not None:
                values = jsonpath.jsonpath(j, expr)
                if values is False:
                    values = []
                self._store.set(k, values or [])
                continue

            if isinstance(expr, str):
                found = re.findall(expr, text, re.S)
                if not found and "\\\\" in expr:
                    found = re.findall(expr.replace("\\\\", "\\"), text, re.S)
                self._store.set(k, found)
                continue

            self._store.set(k, [])
