from ntf.config import AppConfig
from ntf.executor import RequestExecutor
from ntf.http import DummyTransport, HttpResponse
from ntf.yaml_case import load_yaml_cases


def test_yaml_driven_offline(extract_store, assertion_engine):
    cfg = AppConfig(base_url="http://example.local", timeout_s=3)

    base, cases = load_yaml_cases("tests/data/sample_api.yaml")

    transport = DummyTransport(
        {
            (
                base.method,
                f"{cfg.base_url}{base.url}",
            ): HttpResponse(
                status_code=200,
                text='{"user_id": "123456", "msg_code": 200, "msg": "查询成功"}',
                json_data={"user_id": "123456", "msg_code": 200, "msg": "查询成功"},
            )
        }
    )

    ex = RequestExecutor(
        base_url=cfg.base_url,
        timeout_s=cfg.timeout_s,
        transport=transport,
        extract_store=extract_store,
        assertion_engine=assertion_engine,
    )

    tc = cases[0]
    ex.execute(
        method=base.method,
        url=base.url,
        headers=base.header,
        request_kwargs=tc.request,
        extract=tc.extract,
        extract_list=tc.extract_list,
        validation=tc.validation,
    )

    assert extract_store.get("user_id") == "123456"


def test_legacy_rendering(extract_store, assertion_engine):
    extract_store.set("token", "t-123")
    cfg = AppConfig(base_url="http://example.local", timeout_s=3)

    base, cases = load_yaml_cases("tests/data/sample_api_legacy_render.yaml")

    transport = DummyTransport(
        {
            (
                base.method,
                f"{cfg.base_url}{base.url}",
            ): HttpResponse(
                status_code=200,
                text='{"user_id": "123456", "msg_code": 200, "msg": "查询成功"}',
                json_data={"user_id": "123456", "msg_code": 200, "msg": "查询成功"},
            )
        }
    )

    ex = RequestExecutor(
        base_url=cfg.base_url,
        timeout_s=cfg.timeout_s,
        transport=transport,
        extract_store=extract_store,
        assertion_engine=assertion_engine,
    )

    # 只验证 render 能在执行前完成（不发真实请求），以及断言链路正常
    for tc in cases:
        ex.execute(
            method=base.method,
            url=base.url,
            headers=base.header,
            request_kwargs=tc.request,
            extract=tc.extract,
            extract_list=tc.extract_list,
            validation=tc.validation,
        )
