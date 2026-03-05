from __future__ import annotations

import os
import time
from dataclasses import dataclass


def _get_env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class _RunStats:
    start_time: float


def pytest_configure(config):
    config._ntf_stats = _RunStats(start_time=time.time())


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    stats: _RunStats | None = getattr(config, "_ntf_stats", None)
    duration = (time.time() - stats.start_time) if stats else 0.0

    total = terminalreporter._numcollected
    passed = len(terminalreporter.stats.get("passed", []))
    failed = len(terminalreporter.stats.get("failed", []))
    error = len(terminalreporter.stats.get("error", []))
    skipped = len(terminalreporter.stats.get("skipped", []))

    summary = (
        "\n自动化测试结果摘要：\n"
        f"测试用例总数：{total}\n"
        f"测试通过数：{passed}\n"
        f"测试失败数：{failed}\n"
        f"错误数量：{error}\n"
        f"跳过执行数量：{skipped}\n"
        f"执行总时长：{duration:.2f}s\n"
    )

    terminalreporter.write_line(summary)

    if _get_env_bool("NTF_DINGDING_ENABLED", False):
        webhook = os.getenv("NTF_DINGDING_WEBHOOK")
        secret = os.getenv("NTF_DINGDING_SECRET")
        if webhook and secret:
            try:
                from ntf.integrations.dingding import DingDingBot

                DingDingBot(webhook=webhook, secret=secret).send_text(summary, at_all=True)
            except Exception as e:
                terminalreporter.write_line(f"[ntf] DingDing notify failed: {e}")
        else:
            terminalreporter.write_line(
                "[ntf] DingDing enabled but missing NTF_DINGDING_WEBHOOK/NTF_DINGDING_SECRET"
            )
