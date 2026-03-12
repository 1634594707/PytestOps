from __future__ import annotations

from typing import Any

from ntf.http import RequestsTransport


def requests_no_session(cfg: Any) -> RequestsTransport:
    return RequestsTransport(
        proxy=cfg.http_proxy,
        verify=cfg.http_verify,
        cert=cfg.http_cert,
        session_persist=False,
    )
