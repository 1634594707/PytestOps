from __future__ import annotations


def test_notify_dingding_run_yaml_enabled(monkeypatch):
    import ntf.cli as cli

    called = {"n": 0, "content": ""}

    class _Bot:
        def __init__(self, *, webhook: str, secret: str):
            assert webhook == "w"
            assert secret == "s"

        def send_text(self, content: str, *, at_all: bool = True):
            called["n"] += 1
            called["content"] = content
            assert at_all is True
            return "ok"

    monkeypatch.setattr(cli, "DingDingBot", _Bot)
    cli._notify_dingding_run_yaml(
        summary={"total": 2, "passed": 1, "failed": 1, "skipped": 0},
        failures=[{"file": "a.yaml", "case_name": "c1", "error": "boom"}],
        enabled=True,
        webhook="w",
        secret="s",
        at_all=True,
    )
    assert called["n"] == 1
    assert "total=2" in called["content"]
