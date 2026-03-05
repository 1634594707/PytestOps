from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jsonpath


@dataclass(frozen=True)
class AssertionResult:
    ok: bool
    message: str = ""


def _jsonpath_first(data: Any, expr: str) -> Any:
    res = jsonpath.jsonpath(data, expr)
    if not res:
        return None
    return res[0]


class AssertionEngine:
    """兼容旧框架的断言语义：contains/eq/ne/rv。

    输入 expected 建议是 list[dict]，例如：
    - [{"contains": {"status_code": 200, "msg": "ok"}}]
    - [{"eq": {"code": 0}}]
    """

    def assert_all(self, expected: list[dict[str, Any]], actual_json: Any, status_code: int) -> None:
        errors: list[str] = []

        for item in expected:
            if not isinstance(item, dict) or len(item) != 1:
                errors.append(f"Invalid assertion item: {item}")
                continue

            kind, payload = next(iter(item.items()))

            if kind == "contains":
                self._assert_contains(payload, actual_json, status_code, errors)
            elif kind == "inc":
                self._assert_inc(payload, actual_json, errors)
            elif kind == "eq":
                self._assert_eq(payload, actual_json, errors)
            elif kind == "ne":
                self._assert_ne(payload, actual_json, errors)
            elif kind == "rv":
                self._assert_rv(payload, actual_json, errors)
            else:
                errors.append(f"Unsupported assertion kind: {kind}")

        if errors:
            raise AssertionError("\n".join(errors))

    def _assert_contains(self, payload: dict[str, Any], actual_json: Any, status_code: int, errors: list[str]) -> None:
        for k, v in payload.items():
            if k == "status_code":
                if int(v) != int(status_code):
                    errors.append(f"status_code expected={v} actual={status_code}")
                continue

            actual_value = None
            if isinstance(actual_json, dict):
                actual_value = actual_json.get(k)

            if actual_value is None:
                actual_value = _jsonpath_first(actual_json, f"$..{k}")

            if actual_value is None:
                errors.append(f"contains: key not found: {k}")
                continue

            if str(v) not in str(actual_value):
                errors.append(f"contains: {k} expected to contain {v}, actual={actual_value}")

    def _assert_inc(self, payload: Any, actual_json: Any, errors: list[str]) -> None:
        """Legacy 'inc' assertion.

        Supported payload:
        - "key" / ["k1", "k2"]: assert key exists and value is not None
        - {"key": "expected_substr"}: assert key exists and contains expected substring
        """

        if isinstance(payload, str):
            keys: list[str] = [payload]
            mapping: dict[str, Any] | None = None
        elif isinstance(payload, list):
            keys = [str(k) for k in payload]
            mapping = None
        elif isinstance(payload, dict):
            keys = [str(k) for k in payload.keys()]
            mapping = payload
        else:
            errors.append(f"inc: invalid payload: {payload}")
            return

        for k in keys:
            actual_value = None
            if isinstance(actual_json, dict):
                actual_value = actual_json.get(k)
            if actual_value is None:
                actual_value = _jsonpath_first(actual_json, f"$..{k}")

            if actual_value is None:
                errors.append(f"inc: key not found: {k}")
                continue

            if mapping is not None:
                expected = mapping.get(k)
                if expected is not None and str(expected) not in str(actual_value):
                    errors.append(f"inc: {k} expected to contain {expected}, actual={actual_value}")

    def _assert_eq(self, payload: dict[str, Any], actual_json: Any, errors: list[str]) -> None:
        if not isinstance(actual_json, dict):
            errors.append(f"eq: actual_json must be dict, got {type(actual_json)}")
            return
        for k, v in payload.items():
            if actual_json.get(k) != v:
                errors.append(f"eq: {k} expected={v} actual={actual_json.get(k)}")

    def _assert_ne(self, payload: dict[str, Any], actual_json: Any, errors: list[str]) -> None:
        if not isinstance(actual_json, dict):
            errors.append(f"ne: actual_json must be dict, got {type(actual_json)}")
            return
        for k, v in payload.items():
            if actual_json.get(k) == v:
                errors.append(f"ne: {k} expected != {v} but got {v}")

    def _assert_rv(self, payload: dict[str, Any], actual_json: Any, errors: list[str]) -> None:
        if not isinstance(actual_json, dict):
            errors.append(f"rv: actual_json must be dict, got {type(actual_json)}")
            return
        if len(payload) != 1:
            errors.append(f"rv: invalid payload: {payload}")
            return
        k, v = next(iter(payload.items()))
        if actual_json.get(k) != v:
            errors.append(f"rv: {k} expected={v} actual={actual_json.get(k)}")
