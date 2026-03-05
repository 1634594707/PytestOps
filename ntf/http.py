from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import requests


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    text: str
    json_data: Any | None


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        timeout_s: float | None = None,
    ) -> HttpResponse: ...


class RequestsTransport:
    def __init__(self) -> None:
        self._session = requests.Session()

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        timeout_s: float | None = None,
    ) -> HttpResponse:
        r = self._session.request(
            method=method,
            url=url,
            headers=dict(headers) if headers else None,
            cookies=dict(cookies) if cookies else None,
            params=dict(params) if params else None,
            data=data,
            json=json,
            timeout=timeout_s,
        )
        try:
            j = r.json()
        except Exception:
            j = None
        return HttpResponse(status_code=r.status_code, text=r.text, json_data=j)


class DummyTransport:
    """用于离线/单元测试，不发真实 HTTP 请求。"""

    def __init__(self, routes: dict[tuple[str, str], HttpResponse]):
        self._routes = routes

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        data: Any | None = None,
        json: Any | None = None,
        timeout_s: float | None = None,
    ) -> HttpResponse:
        key = (method.upper(), url)
        if key not in self._routes:
            raise KeyError(f"DummyTransport route not found: {key}")
        return self._routes[key]
