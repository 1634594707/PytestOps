from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class YamlBaseInfo:
    api_name: str
    url: str
    method: str
    header: dict[str, str] | None = None
    cookies: str | dict[str, Any] | None = None


@dataclass(frozen=True)
class YamlTestCase:
    case_name: str
    request: dict[str, Any]
    validation: list[dict[str, Any]]
    extract: dict[str, Any] | None = None
    extract_list: dict[str, Any] | None = None
    setup_hooks: list[Any] | None = None
    teardown_hooks: list[Any] | None = None
    depends_on: list[str] | None = None
    timeout_s: float | None = None
    retry: int | None = None


def load_yaml_cases(path: str | Path) -> tuple[YamlBaseInfo, list[YamlTestCase]]:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))

    suite = load_yaml_suite_from_data(data)
    if len(suite) != 1:
        raise ValueError("YAML contains multiple baseInfo blocks; use load_yaml_suite()")
    return suite[0]


def load_yaml_suite(path: str | Path) -> list[tuple[YamlBaseInfo, list[YamlTestCase]]]:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return load_yaml_suite_from_data(data)


def load_yaml_suite_from_data(data: Any) -> list[tuple[YamlBaseInfo, list[YamlTestCase]]]:
    """Parse YAML into a suite.

    Supported legacy formats:
    - Single block: a list with one dict containing baseInfo/testCase
    - Multi block: a list of dicts, each containing baseInfo/testCase
    """

    if not isinstance(data, list) or not data:
        raise ValueError("YAML root must be a non-empty list")

    suite: list[tuple[YamlBaseInfo, list[YamlTestCase]]] = []

    for block in data:
        if not isinstance(block, dict):
            continue

        base_info_raw = block.get("baseInfo")
        if not isinstance(base_info_raw, dict):
            raise ValueError("baseInfo missing or invalid")

        base = YamlBaseInfo(
            api_name=str(base_info_raw.get("api_name", "")),
            url=str(base_info_raw.get("url", "")),
            method=str(base_info_raw.get("method", "GET")).upper(),
            header=base_info_raw.get("header"),
            cookies=base_info_raw.get("cookies"),
        )

        tcs: list[YamlTestCase] = []
        for item in block.get("testCase", []) or []:
            if not isinstance(item, dict):
                continue
            case_name = str(item.get("case_name", ""))
            validation = item.get("validation")
            if isinstance(validation, str):
                validation = eval(validation)
            if not isinstance(validation, list):
                raise ValueError(f"validation must be list for case: {case_name}")

            extract = item.get("extract")
            extract_list = item.get("extract_list")
            setup_hooks = item.get("setup_hooks")
            teardown_hooks = item.get("teardown_hooks")
            depends_on_raw = item.get("depends_on")
            timeout_s_raw = item.get("timeout_s")
            retry_raw = item.get("retry")

            depends_on: list[str] | None = None
            if isinstance(depends_on_raw, str) and depends_on_raw.strip():
                depends_on = [depends_on_raw.strip()]
            elif isinstance(depends_on_raw, list):
                depends_on = [str(x).strip() for x in depends_on_raw if str(x).strip()]

            timeout_s: float | None = None
            if timeout_s_raw is not None:
                timeout_s = float(timeout_s_raw)

            retry: int | None = None
            if retry_raw is not None:
                retry = int(retry_raw)

            req = dict(item)
            req.pop("case_name", None)
            req.pop("validation", None)
            req.pop("extract", None)
            req.pop("extract_list", None)
            req.pop("setup_hooks", None)
            req.pop("teardown_hooks", None)
            req.pop("depends_on", None)
            req.pop("timeout_s", None)
            req.pop("retry", None)

            tcs.append(
                YamlTestCase(
                    case_name=case_name,
                    request=req,
                    validation=validation,
                    extract=extract,
                    extract_list=extract_list,
                    setup_hooks=setup_hooks,
                    teardown_hooks=teardown_hooks,
                    depends_on=depends_on,
                    timeout_s=timeout_s,
                    retry=retry,
                )
            )

        suite.append((base, tcs))

    return suite
