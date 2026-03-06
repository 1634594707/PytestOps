from __future__ import annotations

import json
import random
import re
import time
import datetime
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from ntf.extract import ExtractStore
from ntf.plugins import function_plugins


_CALL_RE = re.compile(r"\$\{(?P<func>[a-zA-Z_][a-zA-Z0-9_]*)\((?P<args>.*?)\)\}")

_EXTERNAL_FUNCTIONS: Any | None = None


def set_external_functions(functions: Any) -> None:
    global _EXTERNAL_FUNCTIONS
    _EXTERNAL_FUNCTIONS = functions


def clear_external_functions() -> None:
    global _EXTERNAL_FUNCTIONS
    _EXTERNAL_FUNCTIONS = None


def get_external_functions() -> Any | None:
    return _EXTERNAL_FUNCTIONS


def _split_args(arg_str: str) -> list[str]:
    s = arg_str.strip()
    if not s:
        return []
    # 兼容旧框架：简单按逗号分隔，不支持嵌套表达式
    return [a.strip() for a in s.split(",")]


@dataclass
class RenderContext:
    extract_store: ExtractStore


class BuiltinFunctions:
    """最小内置函数集合。

    说明：旧框架把大量函数放在 DebugTalk 里。这里先覆盖最常用的：
    - get_extract_data(node_name, randoms=None)

    你可以把旧项目的 DebugTalk 逐步迁移/复制到这里（或做成外部插件）。
    """

    def __init__(self, ctx: RenderContext):
        self._ctx = ctx

    def get_extract_data(self, node_name: str, randoms: str | None = None) -> Any:
        value = self._ctx.extract_store.get(node_name)
        if value is None and isinstance(node_name, str) and not node_name.endswith("s"):
            # legacy compatibility: some suites extract plural key but consume singular key
            value = self._ctx.extract_store.get(f"{node_name}s")

        if randoms is None:
            return value

        # 兼容旧逻辑：randoms 若是数字字符串则走列表取值策略
        try:
            idx = int(str(randoms))
        except Exception:
            # 第二参数不是数字：当作二级 key（dict）
            if isinstance(value, dict):
                return value.get(str(randoms))
            return None

        if isinstance(value, list):
            if idx == 0:
                return random.choice(value) if value else None
            if idx == -1:
                return ",".join(str(x) for x in value)
            if idx == -2:
                return [str(x) for x in value]
            if idx > 0:
                return value[idx - 1] if (idx - 1) < len(value) else None

        return value

    def timestamp(self) -> int:
        return int(time.time())

    def timestamp_thirteen(self) -> int:
        return int(time.time() * 1000)

    def today_zero_stamp(self) -> int:
        now = datetime.datetime.now()
        zero = datetime.datetime(year=now.year, month=now.month, day=now.day)
        return int(zero.timestamp())

    def uuid4(self) -> str:
        return str(uuid.uuid4())

    def random_str(self, n: str = "8") -> str:
        try:
            ln = max(1, int(n))
        except Exception:
            ln = 8
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
        return "".join(random.choice(alphabet) for _ in range(ln))

    def random_email(self, prefix: str = "user") -> str:
        return f"{prefix}_{self.random_str('8')}@example.test"


class _PluginFunctionContainer:
    def __init__(self) -> None:
        self._funcs = function_plugins()

    def __getattr__(self, name: str) -> Any:
        fn = self._funcs.get(name)
        if fn is None:
            raise AttributeError(name)
        return fn


class Renderer:
    def __init__(self, ctx: RenderContext, functions: Any | None = None):
        self._ctx = ctx
        self._builtin = BuiltinFunctions(ctx)
        self._functions = functions or get_external_functions() or self._builtin
        self._plugin_functions = _PluginFunctionContainer()

    def render(self, data: Any) -> Any:
        """递归渲染 dict/list/str，替换 `${func(a,b)}` 形式。"""
        if data is None:
            return None

        if isinstance(data, str):
            return self._render_str(data)

        if isinstance(data, list):
            return [self.render(i) for i in data]

        if isinstance(data, dict):
            return {k: self.render(v) for k, v in data.items()}

        return data

    def _render_str(self, s: str) -> Any:
        original = s

        def repl(m: re.Match[str]) -> str:
            func_name = m.group("func")
            arg_str = m.group("args")
            args = _split_args(arg_str)

            fn: Callable[..., Any] | None = getattr(self._functions, func_name, None)
            if fn is None:
                fn = getattr(self._builtin, func_name, None)
            if fn is None:
                fn = getattr(self._plugin_functions, func_name)
            value = fn(*args)
            return str(value) if value is not None else ""

        rendered = _CALL_RE.sub(repl, s)

        # 若原始值不是纯字符串，而是被渲染成 JSON 字符串，尝试还原为 dict/list
        if original != rendered:
            stripped = rendered.strip()
            # only parse when it looks like JSON object/array/string
            if stripped.startswith("{") or stripped.startswith("[") or stripped.startswith('"'):
                try:
                    return json.loads(rendered)
                except Exception:
                    return rendered
            return rendered

        return rendered
