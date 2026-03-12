from __future__ import annotations

from typing import Any

import jsonpath


def _resolve_actual(actual_json: Any, status_code: int, locator: str) -> tuple[bool, Any]:
    if locator == "status_code":
        return True, status_code

    if locator.startswith("$"):
        values = jsonpath.jsonpath(actual_json, locator)
        if not values:
            return False, None
        return True, values[0]

    if isinstance(actual_json, dict) and locator in actual_json:
        return True, actual_json.get(locator)

    values = jsonpath.jsonpath(actual_json, f"$..{locator}")
    if not values:
        return False, None
    return True, values[0]


def assert_startswith(payload: Any, actual_json: Any, status_code: int) -> None:
    if not isinstance(payload, dict) or len(payload) != 1:
        raise AssertionError("startswith payload must be a dict with one locator")

    locator, expected_prefix = next(iter(payload.items()))
    found, actual = _resolve_actual(actual_json, status_code, str(locator))
    if not found:
        raise AssertionError(f"startswith locator not found: {locator}")

    if not str(actual).startswith(str(expected_prefix)):
        raise AssertionError(
            "startswith failed: locator={locator} expected_prefix={expected!r} actual={actual!r}".format(
                locator=locator,
                expected=expected_prefix,
                actual=actual,
            )
        )
