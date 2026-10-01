"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any, Callable

from app.seed import SEED_ROWS

# 模块自定义看板口径：返回 (待处理, 异常)。未注册的模块沿用 pending/abnormal 标记。
OverviewFn = Callable[[list[dict[str, Any]]], tuple[int, int]]
_OVERVIEW_FNS: dict[str, OverviewFn] = {}


def register_overview(module: str, fn: OverviewFn) -> None:
    """注册模块的看板重算函数，供对应服务在导入时挂上来。"""
    _OVERVIEW_FNS[module] = fn


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            fn = _OVERVIEW_FNS.get(name)
            if fn is not None:
                pending, abnormal = fn(rows)
            else:
                pending = sum(1 for row in rows if row.get("pending"))
                abnormal = sum(1 for row in rows if row.get("abnormal"))
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": pending,
                "abnormal": abnormal,
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
