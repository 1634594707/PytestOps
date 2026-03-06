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
        proxy: str | None = None,
        verify: bool | str | None = None,
        cert: str | tuple[str, str] | None = None,
    ) -> HttpResponse: ...


class RequestsTransport:
    def __init__(
        self,
        *,
        proxy: str | None = None,
        verify: bool | str = True,
        cert: str | tuple[str, str] | None = None,
        session_persist: bool = True,
    ) -> None:
        self._session = requests.Session()
        self._proxy = proxy
        self._verify = verify
        self._cert = cert
        self._session_persist = session_persist

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
        proxy: str | None = None,
        verify: bool | str | None = None,
        cert: str | tuple[str, str] | None = None,
    ) -> HttpResponse:
        final_proxy = proxy if proxy is not None else self._proxy
        final_verify = verify if verify is not None else self._verify
        final_cert = cert if cert is not None else self._cert
        proxies = {"http": final_proxy, "https": final_proxy} if final_proxy else None

        if self._session_persist:
            r = self._session.request(
                method=method,
                url=url,
                headers=dict(headers) if headers else None,
                cookies=dict(cookies) if cookies else None,
                params=dict(params) if params else None,
                data=data,
                json=json,
                timeout=timeout_s,
                proxies=proxies,
                verify=final_verify,
                cert=final_cert,
            )
        else:
            r = requests.request(
                method=method,
                url=url,
                headers=dict(headers) if headers else None,
                cookies=dict(cookies) if cookies else None,
                params=dict(params) if params else None,
                data=data,
                json=json,
                timeout=timeout_s,
                proxies=proxies,
                verify=final_verify,
                cert=final_cert,
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
        proxy: str | None = None,
        verify: bool | str | None = None,
        cert: str | tuple[str, str] | None = None,
    ) -> HttpResponse:
        key = (method.upper(), url)
        if key not in self._routes:
            raise KeyError(f"DummyTransport route not found: {key}")
        return self._routes[key]
