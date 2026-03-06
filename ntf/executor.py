from __future__ import annotations

import json
import random
import re
import time
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
    request: dict[str, Any]
    timings_ms: dict[str, int]


@dataclass(frozen=True)
class ExecuteError(Exception):
    stage: str
    request: dict[str, Any]
    response: HttpResponse | None = None
    original: BaseException | None = None

    def __str__(self) -> str:  # pragma: no cover
        if self.original is not None:
            return str(self.original)
        return f"ExecuteError(stage={self.stage})"


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
        extract: dict[str, Any] | None = None,
        extract_list: dict[str, Any] | None = None,
        validation: list[dict[str, Any]] | None = None,
    ) -> ExecuteResult:
        t0 = _now_ms()
        full_url = url
        if url.startswith("/"):
            full_url = f"{self._base_url}{url}"
        elif not url.startswith("http"):
            full_url = f"{self._base_url}/{url}"

        headers = self._renderer.render(headers) if headers else None
        cookies = self._renderer.render(cookies) if cookies else None
        request_kwargs = self._renderer.render(request_kwargs or {})

        request_info: dict[str, Any] = {
            "method": method,
            "url": full_url,
            "headers": headers,
            "cookies": cookies,
            "params": request_kwargs.get("params"),
            "data": request_kwargs.get("data"),
            "json": request_kwargs.get("json"),
            "timeout_s": self._timeout_s,
        }

        try:
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
        except Exception as e:
            raise ExecuteError(stage="request", request=request_info, original=e) from e

        t1 = _now_ms()

        r = self._normalize_response(r)

        try:
            if extract:
                self._apply_extract(extract, r)

            if extract_list:
                self._apply_extract_list(extract_list, r)
        except Exception as e:
            raise ExecuteError(
                stage="extract",
                request=request_info,
                response=r,
                original=e,
            ) from e

        if validation is not None:
            actual_json = r.json_data if r.json_data is not None else {}
            try:
                self._assertions.assert_all(validation, actual_json, r.status_code)
            except Exception as e:
                raise ExecuteError(
                    stage="validation",
                    request=request_info,
                    response=r,
                    original=e,
                ) from e

        t2 = _now_ms()
        return ExecuteResult(
            response=r,
            request=request_info,
            timings_ms={
                "case_start": t0,
                "request_stop": t1,
                "case_stop": t2,
            },
        )


def _now_ms() -> int:
    return int(time.time() * 1000)


class RequestExecutor(RequestExecutor):
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

    def _apply_extract(self, rules: dict[str, Any], r: HttpResponse) -> None:
        text = r.text
        j = r.json_data

        for key, rule in rules.items():
            if rule is None:
                continue

            if isinstance(rule, str):
                value = self._extract_legacy_single(rule, text, j)
                self._store.set(key, value)
                continue

            if isinstance(rule, dict):
                value = self._extract_by_schema(
                    key=key,
                    rule=rule,
                    text=text,
                    json_data=j,
                    list_mode=False,
                )
                self._store.set(key, value)
                continue

            self._store.set(key, None)

    def _apply_extract_list(self, rules: dict[str, Any], r: HttpResponse) -> None:
        text = r.text
        j = r.json_data

        for key, rule in rules.items():
            if rule is None:
                continue

            if isinstance(rule, str):
                value = self._extract_legacy_list(rule, text, j)
                self._store.set(key, value)
                continue

            if isinstance(rule, dict):
                value = self._extract_by_schema(
                    key=key,
                    rule=rule,
                    text=text,
                    json_data=j,
                    list_mode=True,
                )
                self._store.set(key, value)
                continue

            self._store.set(key, [])

    def _extract_legacy_single(self, source: str, text: str, json_data: Any) -> Any:
        if source.strip().startswith("$") and json_data is not None:
            values = jsonpath.jsonpath(json_data, source)
            if values is False:
                values = []
            return values[0] if values else None

        m = re.search(source, text)
        if not m and "\\\\" in source:
            m = re.search(source.replace("\\\\", "\\"), text)
        if not m:
            return None
        if m.lastindex:
            return m.group(1)
        return m.group(0)

    def _extract_legacy_list(self, source: str, text: str, json_data: Any) -> list[Any]:
        if source.strip().startswith("$") and json_data is not None:
            values = jsonpath.jsonpath(json_data, source)
            if values is False:
                values = []
            return values or []

        found = re.findall(source, text, re.S)
        if not found and "\\\\" in source:
            found = re.findall(source.replace("\\\\", "\\"), text, re.S)
        return found

    def _extract_by_schema(
        self,
        *,
        key: str,
        rule: dict[str, Any],
        text: str,
        json_data: Any,
        list_mode: bool,
    ) -> Any:
        source = rule.get("source")
        if source is None:
            source = rule.get("expr")
        if source is None:
            source = rule.get("from")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"extract[{key}] invalid source: {source!r}")

        default_missing = object()
        default = rule.get("default", default_missing)
        strategy = rule.get("strategy")
        value_type = rule.get("type")
        join_sep = str(rule.get("join_sep", ","))

        values = self._extract_values(source, text, json_data, key)
        has_value = len(values) > 0

        if strategy is None:
            if list_mode:
                raw: Any = values if has_value else ([] if default is default_missing else default)
            else:
                raw = values[0] if has_value else (None if default is default_missing else default)
        else:
            raw = self._apply_strategy(
                key=key,
                source=source,
                strategy=str(strategy),
                values=values,
                default=default,
                default_missing=default_missing,
                join_sep=join_sep,
            )

        return self._convert_type(key=key, source=source, value=raw, value_type=value_type)

    def _extract_values(self, source: str, text: str, json_data: Any, key: str) -> list[Any]:
        if source.strip().startswith("$"):
            if json_data is None:
                return []
            values = jsonpath.jsonpath(json_data, source)
            if values is False:
                values = []
            return values or []

        try:
            found = re.findall(source, text, re.S)
        except re.error as e:
            raise ValueError(
                f"extract[{key}] invalid regex source={source!r}: {e}; response_snippet={self._snippet(text)!r}"
            ) from e

        if not found and "\\\\" in source:
            found = re.findall(source.replace("\\\\", "\\"), text, re.S)

        normalized: list[Any] = []
        for item in found:
            if isinstance(item, tuple):
                if len(item) == 1:
                    normalized.append(item[0])
                else:
                    normalized.append(item)
            else:
                normalized.append(item)
        return normalized

    def _apply_strategy(
        self,
        *,
        key: str,
        source: str,
        strategy: str,
        values: list[Any],
        default: Any,
        default_missing: Any,
        join_sep: str,
    ) -> Any:
        s = strategy.lower()
        if s not in {"first", "last", "random", "join"}:
            raise ValueError(
                f"extract[{key}] unsupported strategy={strategy!r} source={source!r}; "
                f"supported=first,last,random,join"
            )

        if not values:
            return None if default is default_missing else default

        if s == "first":
            return values[0]
        if s == "last":
            return values[-1]
        if s == "random":
            return random.choice(values)
        return join_sep.join(str(v) for v in values)

    def _convert_type(self, *, key: str, source: str, value: Any, value_type: Any) -> Any:
        if value_type is None:
            return value

        t = str(value_type).lower()
        if isinstance(value, list):
            return [self._convert_scalar_type(key=key, source=source, value=v, value_type=t) for v in value]
        return self._convert_scalar_type(key=key, source=source, value=value, value_type=t)

    def _convert_scalar_type(self, *, key: str, source: str, value: Any, value_type: str) -> Any:
        if value is None:
            return None
        try:
            if value_type == "str":
                return str(value)
            if value_type == "int":
                return int(value)
            if value_type == "float":
                return float(value)
            if value_type == "bool":
                if isinstance(value, bool):
                    return value
                if isinstance(value, (int, float)):
                    return bool(value)
                s = str(value).strip().lower()
                if s in {"true", "1", "yes", "y", "on"}:
                    return True
                if s in {"false", "0", "no", "n", "off"}:
                    return False
                raise ValueError(f"cannot cast to bool: {value!r}")
            raise ValueError(f"unsupported type: {value_type!r}")
        except Exception as e:
            raise ValueError(
                f"extract[{key}] type conversion failed source={source!r} type={value_type!r} value={value!r}: {e}"
            ) from e

    def _snippet(self, text: str, max_len: int = 180) -> str:
        s = text.replace("\n", "\\n")
        if len(s) <= max_len:
            return s
        return s[:max_len] + "...(truncated)"
