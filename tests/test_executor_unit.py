from ntf.assertions import AssertionEngine
from ntf.executor import RequestExecutor
from ntf.extract import ExtractStore
from ntf.http import DummyTransport, HttpResponse


def test_executor_extract_regex():
    store = ExtractStore()
    transport = DummyTransport(
        {(
            "GET",
            "http://example.local/hello",
        ): HttpResponse(status_code=200, text="token=abc123", json_data=None)}
    )

    ex = RequestExecutor(
        base_url="http://example.local",
        timeout_s=1,
        transport=transport,
        extract_store=store,
        assertion_engine=AssertionEngine(),
    )

    ex.execute(
        method="GET",
        url="/hello",
        extract={"token": r"token=(\w+)"},
        validation=[{"contains": {"status_code": 200}}],
    )

    assert store.get("token") == "abc123"
