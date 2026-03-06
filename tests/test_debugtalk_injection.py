from ntf.assertions import AssertionEngine
from ntf.executor import RequestExecutor
from ntf.extract import ExtractStore
from ntf.http import DummyTransport, HttpResponse
from ntf.renderer import clear_external_functions, set_external_functions


class _Funcs:
    def hello(self):
        return "world"


def test_debugtalk_external_functions_affect_renderer():
    store = ExtractStore()
    transport = DummyTransport(
        {
            (
                "GET",
                "http://example.local/hello",
            ): HttpResponse(status_code=200, text="ok", json_data={"msg": "ok"})
        }
    )

    set_external_functions(_Funcs())
    try:
        ex = RequestExecutor(
            base_url="http://example.local",
            timeout_s=1,
            transport=transport,
            extract_store=store,
            assertion_engine=AssertionEngine(),
        )

        r = ex.execute(
            method="GET",
            url="/hello",
            request_kwargs={"params": {"x": "${hello()}"}},
            validation=[{"contains": {"status_code": 200}}],
        )

        assert r.request["params"]["x"] == "world"
    finally:
        clear_external_functions()
