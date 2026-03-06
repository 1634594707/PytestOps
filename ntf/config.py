from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AppConfig:
    base_url: str
    timeout_s: float = 60.0
    http_proxy: str | None = None
    http_verify: bool | str = True
    http_cert: str | tuple[str, str] | None = None
    http_session_persist: bool = True
    sign: dict[str, Any] | None = None


def load_config(path: str | Path, *, profile: str | None = None) -> AppConfig:
    p = Path(path)
    data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    merged = deepcopy(data)

    if profile:
        profiles = data.get("profiles", {})
        if not isinstance(profiles, dict):
            raise ValueError("profiles must be a mapping")
        profile_data = profiles.get(profile)
        if profile_data is None:
            raise ValueError(f"profile not found: {profile}")
        if not isinstance(profile_data, dict):
            raise ValueError(f"profile '{profile}' must be a mapping")
        merged = _deep_merge(merged, profile_data)

    api = merged.get("api", {})
    http = merged.get("http", {})
    sign = merged.get("sign")

    base_url = str(api.get("base_url", ""))
    timeout_s = float(api.get("timeout_s", 60.0))
    http_proxy = http.get("proxy")
    http_verify: bool | str = http.get("verify", True)
    http_cert = http.get("cert")
    http_session_persist = bool(http.get("session_persist", True))

    # env > profile yaml > default yaml
    if os.getenv("NTF_BASE_URL"):
        base_url = str(os.getenv("NTF_BASE_URL"))
    if os.getenv("NTF_TIMEOUT_S"):
        timeout_s = float(str(os.getenv("NTF_TIMEOUT_S")))
    if os.getenv("NTF_HTTP_PROXY"):
        http_proxy = str(os.getenv("NTF_HTTP_PROXY"))
    if os.getenv("NTF_HTTP_VERIFY"):
        http_verify = _parse_verify_env(str(os.getenv("NTF_HTTP_VERIFY")))
    if os.getenv("NTF_HTTP_CERT"):
        http_cert = str(os.getenv("NTF_HTTP_CERT"))
    if os.getenv("NTF_HTTP_SESSION_PERSIST"):
        http_session_persist = _parse_bool(str(os.getenv("NTF_HTTP_SESSION_PERSIST")))

    cert_value: str | tuple[str, str] | None
    if isinstance(http_cert, list) and len(http_cert) == 2:
        cert_value = (str(http_cert[0]), str(http_cert[1]))
    elif http_cert is None:
        cert_value = None
    else:
        cert_value = str(http_cert)

    return AppConfig(
        base_url=base_url,
        timeout_s=timeout_s,
        http_proxy=str(http_proxy) if http_proxy else None,
        http_verify=http_verify,
        http_cert=cert_value,
        http_session_persist=http_session_persist,
        sign=sign if isinstance(sign, dict) else None,
    )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_verify_env(raw: str) -> bool | str:
    s = raw.strip()
    low = s.lower()
    if low in {"true", "1", "yes", "y", "on"}:
        return True
    if low in {"false", "0", "no", "n", "off"}:
        return False
    return s
