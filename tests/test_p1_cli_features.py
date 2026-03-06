from __future__ import annotations

from dataclasses import dataclass

import pytest

from ntf.cli import _order_case_entries, _run_hooks, _should_retry
from ntf.executor import ExecuteError
from ntf.extract import ExtractStore
from ntf.http import HttpResponse
from ntf.yaml_case import YamlTestCase


@dataclass(frozen=True)
class _Base:
    api_name: str
    url: str
    method: str
    header: dict[str, str] | None = None


def _case(name: str, depends: list[str] | None = None) -> YamlTestCase:
    return YamlTestCase(case_name=name, request={}, validation=[{"contains": {"status_code": 200}}], depends_on=depends)


def test_order_case_entries_with_depends():
    entries = [
        {"id": "a.yaml::A", "file": "a.yaml", "base": _Base("a", "/x", "GET"), "tc": _case("A"), "cookies": None, "depends": []},
        {
            "id": "a.yaml::B",
            "file": "a.yaml",
            "base": _Base("a", "/x", "GET"),
            "tc": _case("B", depends=["A"]),
            "cookies": None,
            "depends": ["A"],
        },
    ]
    ordered = _order_case_entries(entries)
    assert [x["id"] for x in ordered] == ["a.yaml::A", "a.yaml::B"]
    assert ordered[1]["dep_ids"] == ["a.yaml::A"]


def test_order_case_entries_cycle_detected():
    entries = [
        {
            "id": "a.yaml::A",
            "file": "a.yaml",
            "base": _Base("a", "/x", "GET"),
            "tc": _case("A", depends=["B"]),
            "cookies": None,
            "depends": ["B"],
        },
        {
            "id": "a.yaml::B",
            "file": "a.yaml",
            "base": _Base("a", "/x", "GET"),
            "tc": _case("B", depends=["A"]),
            "cookies": None,
            "depends": ["A"],
        },
    ]
    with pytest.raises(ValueError):
        _order_case_entries(entries)


class _Funcs:
    def hello(self) -> str:
        return "world"


def test_run_hooks_support_set_and_call():
    store = ExtractStore()
    _run_hooks(
        [
            {"set": {"token": "abc"}},
            {"set": {"msg": "${hello()}"}},
            {"call": "${hello()}"},
        ],
        store,
        functions=_Funcs(),
        renderer_name=None,
        phase="setup_hooks",
        case_name="demo",
    )
    assert store.get("token") == "abc"
    assert store.get("msg") == "world"


def test_should_retry_for_stage_and_5xx():
    err = ExecuteError(
        stage="request",
        request={"url": "x"},
        response=HttpResponse(status_code=502, text="", json_data=None),
        original=TimeoutError("timeout"),
    )
    assert _should_retry(err, {"request"}) is True
    assert _should_retry(err, {"5xx"}) is True
    assert _should_retry(err, {"timeout"}) is True
    assert _should_retry(err, {"validation"}) is False
