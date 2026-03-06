from __future__ import annotations

import pytest


def test_ntf_version_exit(monkeypatch):
    import ntf.cli as cli

    monkeypatch.setattr(cli.sys, "argv", ["ntf", "--version"])
    with pytest.raises(SystemExit) as ei:
        cli.main()
    assert ei.value.code == 0


def test_doctor_collect_has_core_items():
    import ntf.cli as cli

    checks = cli._collect_doctor_checks("configs/default.yaml", profile=None)
    names = {c["name"] for c in checks}
    assert "version" in names
    assert "python" in names
    assert "config" in names
