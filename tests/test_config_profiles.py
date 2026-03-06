from __future__ import annotations

import shutil
from pathlib import Path

from ntf.config import load_config


def test_load_config_profile_and_env_override(monkeypatch):
    cfg_dir = Path("report/test-config")
    shutil.rmtree(cfg_dir, ignore_errors=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = cfg_dir / "cfg.yaml"
    cfg_file.write_text(
        """
api:
  base_url: "http://default.local"
  timeout_s: 10
http:
  proxy: "http://proxy.default:8888"
  verify: true
profiles:
  test:
    api:
      base_url: "http://test.local"
      timeout_s: 20
    http:
      verify: false
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("NTF_BASE_URL", "http://env.local")
    monkeypatch.setenv("NTF_TIMEOUT_S", "30")

    cfg = load_config(Path(cfg_file), profile="test")
    assert cfg.base_url == "http://env.local"
    assert cfg.timeout_s == 30.0
    assert cfg.http_proxy == "http://proxy.default:8888"
    assert cfg.http_verify is False
