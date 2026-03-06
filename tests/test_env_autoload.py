from __future__ import annotations

import shutil
from pathlib import Path

import pytest


def test_load_env_file_basic(monkeypatch):
    import ntf.cli as cli

    d = Path("report/test-env")
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    f = d / ".env"
    f.write_text(
        """
NTF_DINGDING_ENABLED=true
NTF_DINGDING_WEBHOOK=https://example.test/hook
# comment
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.delenv("NTF_DINGDING_ENABLED", raising=False)
    monkeypatch.delenv("NTF_DINGDING_WEBHOOK", raising=False)

    loaded = cli._load_env_file(f, override=False)
    assert loaded == 2
    assert cli.os.getenv("NTF_DINGDING_ENABLED") == "true"
    assert cli.os.getenv("NTF_DINGDING_WEBHOOK") == "https://example.test/hook"


def test_main_auto_load_dotenv(monkeypatch):
    import ntf.cli as cli

    d = Path("report/test-env-main")
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    env_file = d / ".env"
    env_file.write_text("NTF_DINGDING_ENABLED=true", encoding="utf-8")

    monkeypatch.chdir(d)
    monkeypatch.delenv("NTF_DINGDING_ENABLED", raising=False)
    monkeypatch.setattr(cli.sys, "argv", ["ntf", "--version"])
    with pytest.raises(SystemExit):
        cli.main()
    assert cli.os.getenv("NTF_DINGDING_ENABLED") == "true"
