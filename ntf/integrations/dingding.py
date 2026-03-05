from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse

import requests


class DingDingBot:
    def __init__(self, *, webhook: str, secret: str):
        self._webhook = webhook
        self._secret = secret

    def _sign(self) -> tuple[str, str]:
        timestamp = str(round(time.time() * 1000))
        secret_enc = self._secret.encode("utf-8")
        str_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(secret_enc, str_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign

    def send_text(self, content: str, *, at_all: bool = True) -> str:
        ts, sign = self._sign()
        url = f"{self._webhook}&timestamp={ts}&sign={sign}"

        headers = {"Content-Type": "application/json;charset=utf-8"}
        payload = {
            "msgtype": "text",
            "text": {"content": content},
            "at": {"isAtAll": at_all},
        }
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        return r.text
