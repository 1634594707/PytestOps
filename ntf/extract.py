from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractStore:
    """替代旧框架把 extract 写进 YAML 文件的做法。

    - 测试运行期：放在内存里（fixture 级别更可控）
    - 需要持久化时：可以在上层自行 dump
    """

    data: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any | None = None) -> Any:
        return self.data.get(key, default)
