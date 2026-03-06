from __future__ import annotations

from ntf.assertions import AssertionEngine
from ntf.cli import _build_transport, _dispatch_reporter
from ntf.data_factory import random_email, random_phone, unique_id
from ntf.extract import ExtractStore
from ntf.fixtures import FixtureStore
from ntf.plugins import register_assertion, register_function, register_renderer, register_reporter, register_transport
from ntf.renderer import RenderContext, Renderer, build_renderer


def test_plugin_assertion_and_function():
    def assert_even(payload, actual_json, status_code):
        k = str(payload)
        v = actual_json.get(k)
        if v % 2 != 0:
            raise AssertionError(f"{k} is not even")

    def hello():
        return "plugin-world"

    register_assertion("even", assert_even)
    register_function("hello_plugin", hello)

    engine = AssertionEngine()
    engine.assert_all([{"even": "n"}], {"n": 2}, status_code=200)

    store = ExtractStore()
    r = Renderer(RenderContext(extract_store=store))
    assert r.render("${hello_plugin()}") == "plugin-world"


def test_fixture_store_and_data_factory():
    store = FixtureStore("tests/fixtures")
    data = store.load("users")
    assert data["users"][0]["name"] == "alice"

    uid1 = unique_id("u")
    uid2 = unique_id("u")
    assert uid1 != uid2
    assert "@" in random_email()
    assert len(random_phone()) == 11


def test_plugin_transport_and_reporter():
    class _DummyTransport:
        pass

    seen = {"called": False}

    def transport_factory(cfg):
        return _DummyTransport()

    def reporter(summary, failures):
        seen["called"] = True
        assert "total" in summary
        assert isinstance(failures, list)

    register_transport("dummy", transport_factory)
    register_reporter("dummy", reporter)

    t = _build_transport("dummy", cfg=object())
    assert isinstance(t, _DummyTransport)
    _dispatch_reporter("dummy", summary={"total": 1, "passed": 1, "failed": 0, "skipped": 0}, failures=[])
    assert seen["called"] is True


def test_plugin_renderer_override():
    class MyRenderer(Renderer):
        def _render_str(self, s: str):
            if s == "${special()}":
                return "from-renderer-plugin"
            return super()._render_str(s)

    register_renderer("my_renderer", MyRenderer)
    store = ExtractStore()
    r = build_renderer(RenderContext(extract_store=store), renderer_name="my_renderer")
    assert r.render("${special()}") == "from-renderer-plugin"
