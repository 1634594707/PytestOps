from ntf.assertions import AssertionEngine
from ntf.executor import ExecuteError, RequestExecutor
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


def test_executor_extract_schema_default_type_strategy():
    store = ExtractStore()
    transport = DummyTransport(
        {
            ("GET", "http://example.local/users"): HttpResponse(
                status_code=200,
                text="id=10;id=20",
                json_data={"items": [{"id": "1"}, {"id": "2"}, {"id": "3"}], "meta": {"active": "true"}},
            )
        }
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
        url="/users",
        extract={
            "id_first": {"source": "$.items[*].id", "type": "int", "strategy": "first"},
            "id_last": {"source": "$.items[*].id", "type": "int", "strategy": "last"},
            "ids_join": {"source": "$.items[*].id", "strategy": "join", "join_sep": "|"},
            "missing_default": {"source": "$.not_exists", "default": "N/A"},
            "regex_last": {"source": r"id=(\d+)", "type": "int", "strategy": "last"},
            "flag": {"source": "$.meta.active", "type": "bool"},
        },
        extract_list={
            "ids": {"source": "$.items[*].id", "type": "int"},
            "regex_all": {"source": r"id=(\d+)", "type": "int"},
            "missing_list_default": {"source": "$.not_exists[*]", "default": [9, 8]},
        },
        validation=[{"contains": {"status_code": 200}}],
    )

    assert store.get("id_first") == 1
    assert store.get("id_last") == 3
    assert store.get("ids_join") == "1|2|3"
    assert store.get("missing_default") == "N/A"
    assert store.get("regex_last") == 20
    assert store.get("flag") is True
    assert store.get("ids") == [1, 2, 3]
    assert store.get("regex_all") == [10, 20]
    assert store.get("missing_list_default") == [9, 8]


def test_executor_extract_invalid_strategy_error_readable():
    store = ExtractStore()
    transport = DummyTransport(
        {
            ("GET", "http://example.local/users"): HttpResponse(
                status_code=200,
                text='{"items":[1,2]}',
                json_data={"items": [1, 2]},
            )
        }
    )

    ex = RequestExecutor(
        base_url="http://example.local",
        timeout_s=1,
        transport=transport,
        extract_store=store,
        assertion_engine=AssertionEngine(),
    )

    try:
        ex.execute(
            method="GET",
            url="/users",
            extract={"bad": {"source": "$.items[*]", "strategy": "bad"}},
            validation=[{"contains": {"status_code": 200}}],
        )
        assert False, "expected ExecuteError"
    except ExecuteError as e:
        assert e.stage == "extract"
        assert e.original is not None
        msg = str(e.original)
        assert "extract[bad]" in msg
        assert "strategy" in msg
