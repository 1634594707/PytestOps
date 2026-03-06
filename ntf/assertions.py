from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import jsonpath


@dataclass(frozen=True)
class AssertionResult:
    ok: bool
    message: str = ""


@dataclass(frozen=True)
class AssertionFailure:
    kind: str
    locator: str
    expected: Any
    actual: Any
    reason: str = ""

    def format(self) -> str:
        suffix = f" reason={self.reason}" if self.reason else ""
        return (
            f"{self.kind}: locator={self.locator} expected={self.expected!r} "
            f"actual={self.actual!r}{suffix}"
        )


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
        failures: list[AssertionFailure] = []

        for item in expected:
            if not isinstance(item, dict) or len(item) != 1:
                failures.append(
                    AssertionFailure(
                        kind="invalid",
                        locator="",
                        expected=item,
                        actual=None,
                        reason="assertion item must be dict with one operator",
                    )
                )
                continue

            kind, payload = next(iter(item.items()))

            if kind == "contains":
                self._assert_contains(payload, actual_json, status_code, failures)
            elif kind == "inc":
                self._assert_inc(payload, actual_json, status_code, failures)
            elif kind == "eq":
                self._assert_eq(payload, actual_json, status_code, failures)
            elif kind == "ne":
                self._assert_ne(payload, actual_json, status_code, failures)
            elif kind == "rv":
                self._assert_rv(payload, actual_json, status_code, failures)
            elif kind == "lt":
                self._assert_cmp(kind, payload, actual_json, status_code, failures)
            elif kind == "lte":
                self._assert_cmp(kind, payload, actual_json, status_code, failures)
            elif kind == "gt":
                self._assert_cmp(kind, payload, actual_json, status_code, failures)
            elif kind == "gte":
                self._assert_cmp(kind, payload, actual_json, status_code, failures)
            elif kind == "in":
                self._assert_in(payload, actual_json, status_code, failures, expect_in=True)
            elif kind == "not_in":
                self._assert_in(payload, actual_json, status_code, failures, expect_in=False)
            elif kind == "regex":
                self._assert_regex(payload, actual_json, status_code, failures)
            elif kind == "jsonschema":
                self._assert_jsonschema(payload, actual_json, failures)
            else:
                failures.append(
                    AssertionFailure(
                        kind=kind,
                        locator="",
                        expected=payload,
                        actual=None,
                        reason="unsupported assertion kind",
                    )
                )

        if failures:
            raise AssertionError("\n".join(f.format() for f in failures))

    def _assert_contains(
        self,
        payload: dict[str, Any],
        actual_json: Any,
        status_code: int,
        failures: list[AssertionFailure],
    ) -> None:
        if not isinstance(payload, dict):
            failures.append(
                AssertionFailure(
                    kind="contains",
                    locator="",
                    expected=payload,
                    actual=None,
                    reason="payload must be dict",
                )
            )
            return
        for k, v in payload.items():
            found, actual_value = self._resolve_actual(actual_json, status_code, k)
            if not found:
                failures.append(
                    AssertionFailure(
                        kind="contains",
                        locator=str(k),
                        expected=v,
                        actual=None,
                        reason="key/jsonpath not found",
                    )
                )
                continue

            ok = False
            if isinstance(actual_value, (list, tuple, set)):
                ok = v in actual_value
            else:
                ok = str(v) in str(actual_value)
            if not ok:
                failures.append(AssertionFailure(kind="contains", locator=str(k), expected=v, actual=actual_value))

    def _assert_inc(
        self,
        payload: Any,
        actual_json: Any,
        status_code: int,
        failures: list[AssertionFailure],
    ) -> None:
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
            failures.append(
                AssertionFailure(
                    kind="inc",
                    locator="",
                    expected=payload,
                    actual=None,
                    reason="invalid payload",
                )
            )
            return

        for k in keys:
            found, actual_value = self._resolve_actual(actual_json, status_code, k)
            if not found:
                failures.append(
                    AssertionFailure(kind="inc", locator=str(k), expected="exists", actual=None, reason="key/jsonpath not found")
                )
                continue

            if mapping is not None:
                expected = mapping.get(k)
                if expected is not None and str(expected) not in str(actual_value):
                    failures.append(AssertionFailure(kind="inc", locator=str(k), expected=expected, actual=actual_value))

    def _assert_eq(
        self,
        payload: dict[str, Any],
        actual_json: Any,
        status_code: int,
        failures: list[AssertionFailure],
    ) -> None:
        if not isinstance(payload, dict):
            failures.append(
                AssertionFailure(kind="eq", locator="", expected=payload, actual=None, reason="payload must be dict")
            )
            return
        for k, v in payload.items():
            found, actual_value = self._resolve_actual(actual_json, status_code, k)
            if not found:
                failures.append(AssertionFailure(kind="eq", locator=str(k), expected=v, actual=None, reason="key/jsonpath not found"))
                continue
            if actual_value != v:
                failures.append(AssertionFailure(kind="eq", locator=str(k), expected=v, actual=actual_value))

    def _assert_ne(
        self,
        payload: dict[str, Any],
        actual_json: Any,
        status_code: int,
        failures: list[AssertionFailure],
    ) -> None:
        if not isinstance(payload, dict):
            failures.append(
                AssertionFailure(kind="ne", locator="", expected=payload, actual=None, reason="payload must be dict")
            )
            return
        for k, v in payload.items():
            found, actual_value = self._resolve_actual(actual_json, status_code, k)
            if not found:
                failures.append(AssertionFailure(kind="ne", locator=str(k), expected=v, actual=None, reason="key/jsonpath not found"))
                continue
            if actual_value == v:
                failures.append(AssertionFailure(kind="ne", locator=str(k), expected=f"!= {v!r}", actual=actual_value))

    def _assert_rv(
        self,
        payload: dict[str, Any],
        actual_json: Any,
        status_code: int,
        failures: list[AssertionFailure],
    ) -> None:
        if not isinstance(payload, dict):
            failures.append(
                AssertionFailure(kind="rv", locator="", expected=payload, actual=None, reason="payload must be dict")
            )
            return
        if len(payload) != 1:
            failures.append(
                AssertionFailure(kind="rv", locator="", expected=payload, actual=None, reason="payload must have one key")
            )
            return
        k, v = next(iter(payload.items()))
        found, actual_value = self._resolve_actual(actual_json, status_code, k)
        if not found:
            failures.append(AssertionFailure(kind="rv", locator=str(k), expected=v, actual=None, reason="key/jsonpath not found"))
            return
        if actual_value != v:
            failures.append(AssertionFailure(kind="rv", locator=str(k), expected=v, actual=actual_value))

    def _assert_cmp(
        self,
        kind: str,
        payload: dict[str, Any],
        actual_json: Any,
        status_code: int,
        failures: list[AssertionFailure],
    ) -> None:
        if not isinstance(payload, dict):
            failures.append(AssertionFailure(kind=kind, locator="", expected=payload, actual=None, reason="payload must be dict"))
            return

        for locator, expected in payload.items():
            found, actual = self._resolve_actual(actual_json, status_code, str(locator))
            if not found:
                failures.append(
                    AssertionFailure(kind=kind, locator=str(locator), expected=expected, actual=None, reason="key/jsonpath not found")
                )
                continue

            e_num = self._as_number(expected)
            a_num = self._as_number(actual)
            if e_num is None or a_num is None:
                failures.append(
                    AssertionFailure(
                        kind=kind,
                        locator=str(locator),
                        expected=expected,
                        actual=actual,
                        reason="numeric comparison requires number-like values",
                    )
                )
                continue

            ok = {
                "lt": a_num < e_num,
                "lte": a_num <= e_num,
                "gt": a_num > e_num,
                "gte": a_num >= e_num,
            }[kind]
            if not ok:
                failures.append(AssertionFailure(kind=kind, locator=str(locator), expected=expected, actual=actual))

    def _assert_in(
        self,
        payload: dict[str, Any],
        actual_json: Any,
        status_code: int,
        failures: list[AssertionFailure],
        *,
        expect_in: bool,
    ) -> None:
        kind = "in" if expect_in else "not_in"
        if not isinstance(payload, dict):
            failures.append(AssertionFailure(kind=kind, locator="", expected=payload, actual=None, reason="payload must be dict"))
            return

        for locator, expected_container in payload.items():
            found, actual = self._resolve_actual(actual_json, status_code, str(locator))
            if not found:
                failures.append(
                    AssertionFailure(kind=kind, locator=str(locator), expected=expected_container, actual=None, reason="key/jsonpath not found")
                )
                continue

            try:
                included = actual in expected_container
            except Exception:
                failures.append(
                    AssertionFailure(
                        kind=kind,
                        locator=str(locator),
                        expected=expected_container,
                        actual=actual,
                        reason="expected value must be a container",
                    )
                )
                continue

            if expect_in and not included:
                failures.append(AssertionFailure(kind=kind, locator=str(locator), expected=expected_container, actual=actual))
            if not expect_in and included:
                failures.append(AssertionFailure(kind=kind, locator=str(locator), expected=expected_container, actual=actual))

    def _assert_regex(
        self,
        payload: dict[str, Any],
        actual_json: Any,
        status_code: int,
        failures: list[AssertionFailure],
    ) -> None:
        if not isinstance(payload, dict):
            failures.append(AssertionFailure(kind="regex", locator="", expected=payload, actual=None, reason="payload must be dict"))
            return
        for locator, pattern in payload.items():
            found, actual = self._resolve_actual(actual_json, status_code, str(locator))
            if not found:
                failures.append(
                    AssertionFailure(kind="regex", locator=str(locator), expected=pattern, actual=None, reason="key/jsonpath not found")
                )
                continue
            if re.search(str(pattern), str(actual)) is None:
                failures.append(AssertionFailure(kind="regex", locator=str(locator), expected=pattern, actual=actual))

    def _assert_jsonschema(self, payload: Any, actual_json: Any, failures: list[AssertionFailure]) -> None:
        try:
            import jsonschema
        except Exception:
            failures.append(
                AssertionFailure(
                    kind="jsonschema",
                    locator="$",
                    expected=payload,
                    actual=actual_json,
                    reason="jsonschema package not installed",
                )
            )
            return

        target = actual_json
        schema = payload
        locator = "$"
        if isinstance(payload, dict) and "schema" in payload:
            schema = payload.get("schema")
            locator = str(payload.get("locator") or "$")
            if locator != "$":
                found, actual = self._resolve_actual(actual_json, status_code=0, locator=locator)
                if not found:
                    failures.append(
                        AssertionFailure(
                            kind="jsonschema",
                            locator=locator,
                            expected=schema,
                            actual=None,
                            reason="key/jsonpath not found",
                        )
                    )
                    return
                target = actual

        try:
            jsonschema.validate(instance=target, schema=schema)
        except Exception as e:
            failures.append(AssertionFailure(kind="jsonschema", locator=locator, expected=schema, actual=target, reason=str(e)))

    def _resolve_actual(self, actual_json: Any, status_code: int, locator: str) -> tuple[bool, Any]:
        if locator == "status_code":
            return True, status_code

        if locator.startswith("$"):
            values = jsonpath.jsonpath(actual_json, locator)
            if not values:
                return False, None
            return True, values[0]

        if isinstance(actual_json, dict) and locator in actual_json:
            return True, actual_json.get(locator)

        fallback = _jsonpath_first(actual_json, f"$..{locator}")
        if fallback is None:
            return False, None
        return True, fallback

    def _as_number(self, value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except Exception:
                return None
        return None
