import json
from pathlib import Path
import shutil

import pytest


def test_run_yaml_writes_allure_results(monkeypatch):
    import ntf.cli as cli
    from ntf.config import load_config
    from ntf.http import DummyTransport, HttpResponse
    from ntf.yaml_case import load_yaml_cases

    def _dummy_requests_transport_factory(*args, **kwargs):
        cfg = load_config("configs/default.yaml")
        base, _cases = load_yaml_cases("tests/data/sample_api_pass_fail.yaml")

        full_url = base.url
        if base.url.startswith("/"):
            full_url = f"{cfg.base_url.rstrip('/')}{base.url}"
        elif not base.url.startswith("http"):
            full_url = f"{cfg.base_url.rstrip('/')}/{base.url}"

        # For this test we need different responses for different params.
        # DummyTransport only keys by (method,url), so return a response that
        # still passes status_code=200 but has msg_code=200 so first case passes
        # and second case (expecting msg_code=500) fails at validation stage.
        return DummyTransport(
            {
                (
                    base.method,
                    full_url,
                ): HttpResponse(
                    status_code=200,
                    text='{"user_id": "123456", "msg_code": 200, "msg": "查询成功"}',
                    json_data={"user_id": "123456", "msg_code": 200, "msg": "查询成功"},
                )
            }
        )

    monkeypatch.setattr(cli, "RequestsTransport", _dummy_requests_transport_factory)

    results_dir = Path("report/test-allure-results")
    shutil.rmtree(results_dir, ignore_errors=True)

    monkeypatch.setattr(
        cli.sys,
        "argv",
        [
            "ntf",
            "run-yaml",
            "--config",
            "configs/default.yaml",
            "--cases",
            "tests/data/sample_api_pass_fail.yaml",
            "--allure-dir",
            str(results_dir),
            "--continue-on-fail",
        ],
    )

    with pytest.raises(SystemExit) as ei:
        cli.main()

    assert ei.value.code == 1

    files = list(results_dir.glob("*-result.json"))
    assert len(files) >= 2

    statuses: list[str] = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        statuses.append(data.get("status"))

        # steps should exist
        steps = data.get("steps") or []
        assert steps

        att = data.get("attachments") or []
        assert att

        for a in att:
            src = a.get("source")
            if src:
                assert (results_dir / src).exists()

    assert "passed" in statuses
    assert "failed" in statuses
