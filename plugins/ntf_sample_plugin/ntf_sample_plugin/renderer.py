from __future__ import annotations

from typing import Any

from ntf.renderer import RenderContext, Renderer


class UpperRenderer:
    def __init__(self, ctx: RenderContext, functions: Any | None = None) -> None:
        self._inner = Renderer(ctx, functions=functions)

    def render(self, data: Any) -> Any:
        return self._upper(self._inner.render(data))

    def _upper(self, data: Any) -> Any:
        if isinstance(data, str):
            return data.upper()
        if isinstance(data, list):
            return [self._upper(i) for i in data]
        if isinstance(data, dict):
            return {k: self._upper(v) for k, v in data.items()}
        return data
