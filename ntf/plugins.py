from __future__ import annotations

from importlib import metadata
from typing import Any, Callable

# Assertion plugin: func(payload, actual_json, status_code) -> None (raise AssertionError on fail)
AssertionPlugin = Callable[[Any, Any, int], None]
# Function plugin: any callable exposed for ${func()}
FunctionPlugin = Callable[..., Any]
# Transport plugin: factory(config) -> transport instance
TransportPlugin = Callable[[Any], Any]
# Reporter plugin: func(summary, failures) -> None
ReporterPlugin = Callable[[dict[str, Any], list[dict[str, Any]]], None]
# Renderer plugin: class/factory compatible with Renderer(ctx, functions=?)
RendererPlugin = Callable[..., Any]


_assertion_plugins: dict[str, AssertionPlugin] = {}
_function_plugins: dict[str, FunctionPlugin] = {}
_transport_plugins: dict[str, TransportPlugin] = {}
_reporter_plugins: dict[str, ReporterPlugin] = {}
_renderer_plugins: dict[str, RendererPlugin] = {}
_loaded = False


def ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True

    _load_group("ntf.assertions", _assertion_plugins)
    _load_group("ntf.functions", _function_plugins)
    _load_group("ntf.transports", _transport_plugins)
    _load_group("ntf.reporters", _reporter_plugins)
    _load_group("ntf.renderers", _renderer_plugins)


def register_assertion(name: str, plugin: AssertionPlugin) -> None:
    _assertion_plugins[name] = plugin


def register_function(name: str, plugin: FunctionPlugin) -> None:
    _function_plugins[name] = plugin


def register_transport(name: str, plugin: TransportPlugin) -> None:
    _transport_plugins[name] = plugin


def register_reporter(name: str, plugin: ReporterPlugin) -> None:
    _reporter_plugins[name] = plugin


def register_renderer(name: str, plugin: RendererPlugin) -> None:
    _renderer_plugins[name] = plugin


def assertion_plugins() -> dict[str, AssertionPlugin]:
    ensure_loaded()
    return dict(_assertion_plugins)


def function_plugins() -> dict[str, FunctionPlugin]:
    ensure_loaded()
    return dict(_function_plugins)


def transport_plugins() -> dict[str, TransportPlugin]:
    ensure_loaded()
    return dict(_transport_plugins)


def reporter_plugins() -> dict[str, ReporterPlugin]:
    ensure_loaded()
    return dict(_reporter_plugins)


def renderer_plugins() -> dict[str, RendererPlugin]:
    ensure_loaded()
    return dict(_renderer_plugins)


def plugin_counts() -> dict[str, int]:
    ensure_loaded()
    return {
        "assertions": len(_assertion_plugins),
        "functions": len(_function_plugins),
        "transports": len(_transport_plugins),
        "reporters": len(_reporter_plugins),
        "renderers": len(_renderer_plugins),
    }


def _load_group(group: str, target: dict[str, Any]) -> None:
    try:
        eps = metadata.entry_points(group=group)
    except Exception:
        eps = []

    for ep in eps:
        try:
            obj = ep.load()
        except Exception:
            continue

        # `ntf.functions` supports mapping/object style to expose multiple functions.
        if group == "ntf.functions" and isinstance(obj, dict):
            for k, v in obj.items():
                if callable(v):
                    target[str(k)] = v
            continue

        if callable(obj):
            target[ep.name] = obj
            continue

        if group == "ntf.functions":
            for name in dir(obj):
                if name.startswith("_"):
                    continue
                val = getattr(obj, name, None)
                if callable(val):
                    target[name] = val
