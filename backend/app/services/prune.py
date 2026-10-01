"""修剪造型业务规则：缺项待补、修剪量取数/补录、返工接回、幂等提交与看板口径都收在这里。

列表与详情共用同一套展示口径（present），保证两个入口读到的修剪量一致；
看板统计（stats）始终由明细实时重算，不缓存任何数字。
"""
from __future__ import annotations

from typing import Any

from app.store import register_overview, store

MODULE = "prune"

# 登记修剪任务时必须给全的字段；缺任一项都不能建档
REQUIRED_FIELDS = ["修剪编号", "修剪对象", "修剪类型"]
# 正式开始修剪前必须补齐的字段；缺了就停在「待补」并说明原因
START_FIELDS = ["修剪对象", "造型要求"]

STATUS_ORDER = ["待修剪", "修剪中", "已完成", "需返工", "待补"]
# 各状态允许继续执行的动作，非法跳转一律拦下
# 安排修剪：待修剪 → 修剪中；开始修剪（即正式提交完工）：修剪中 → 已完成
ACTION_RULES = {
    "安排修剪": {"from": ["待修剪", "待补"], "to": "修剪中"},
    "开始修剪": {"from": ["修剪中"], "to": "已完成"},
    "返工登记": {"from": ["已完成"], "to": "需返工"},
    "返工完成": {"from": ["需返工"], "to": "已完成"},
}

# 修剪量取数的三种状态：有值 / 取数失败（可重试）/ 清单为空（只能补录）
QTY_OK = "ok"
QTY_FAILED = "failed"
QTY_EMPTY = "empty"

# 编号命中该前缀的对象，模拟外部计量服务故障，供演示「取数失败 → 重试」
FETCH_FAIL_PREFIX = "PRUN-FAIL"

# 列表展示的业务字段（不含内部状态机字段）
LIST_FIELDS = ["修剪编号", "修剪对象", "修剪类型", "修剪量", "造型要求", "作业日期", "操作人员", "修剪状态"]


def _text(value: Any) -> str:
    """把任意入参收敛成去空白的字符串。"""
    return str(value if value is not None else "").strip()


def missing_reasons(entry: dict[str, Any]) -> list[str]:
    """逐条给出待补原因；没有缺项时返回空列表。"""
    reasons: list[str] = []
    for field in START_FIELDS:
        if not _text(entry.get(field)):
            reasons.append(f"{field}未填写")
    if entry.get("修剪量状态") == QTY_EMPTY:
        reasons.append("修剪量取不到数：计量清单为空，需要人工补录")
    elif entry.get("修剪量状态") == QTY_FAILED:
        reasons.append("修剪量取数失败，可重试取数或人工补录")
    elif entry.get("修剪量状态") != QTY_OK:
        reasons.append("修剪量尚未取数")
    return reasons


def _present(entry: dict[str, Any]) -> dict[str, Any]:
    """内部记录 → 对外展示结构。

    列表、详情、动作返回值都走这一个出口，确保修剪量在不同入口口径一致。
    """
    reasons = missing_reasons(entry)
    status = _text(entry.get("status"))
    # 处于正常流程状态但仍有缺项时，展示口径上归到「待补」，避免缺项单混在待办里
    display_status = "待补" if reasons and status not in ("需返工", "已完成") else status

    qty_state = entry.get("修剪量状态")
    qty_value = entry.get("修剪量")
    if qty_state == QTY_OK and qty_value is not None:
        qty_text: Any = qty_value
    elif qty_state == QTY_FAILED:
        qty_text = "取数失败"
    elif qty_state == QTY_EMPTY:
        qty_text = "清单为空"
    else:
        qty_text = "待补"

    item: dict[str, Any] = {
        "id": entry.get("id"),
        "修剪编号": entry.get("修剪编号", ""),
        "修剪对象": entry.get("修剪对象") or "待补",
        "修剪类型": entry.get("修剪类型", ""),
        "修剪量": qty_text,
        "造型要求": entry.get("造型要求") or "待补",
        "作业日期": entry.get("作业日期") or "—",
        "操作人员": entry.get("操作人员") or "—",
        "修剪状态": display_status,
        # 供前端区分状态、渲染重试/补录入口
        "_status": status,
        "_缺项": reasons,
        "_待补": bool(reasons) and status not in ("需返工", "已完成"),
        "_修剪量状态": qty_state,
        "_修剪量错误": entry.get("修剪量错误") or "",
        "_可返工接回": status == "需返工" and bool(entry.get("返工快照")),
        "_已提交": bool(entry.get("已提交")),
        "_返工快照": entry.get("返工快照"),
    }
    return item


class PruneService:
    # ---- 查询 ----------------------------------------------------------------

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in _text(row.get("修剪编号"))]
        if status:
            # 按展示状态过滤：缺项单统一归到「待补」
            rows = [row for row in rows if _present(row)["修剪状态"] == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _present(entry) if entry is not None else None

    def stats(self) -> dict[str, int]:
        """看板统计：待返工数等指标一律由当前明细实时重算。"""
        rows = [_present(row) for row in store.rows(MODULE)]
        return {
            "待修剪": sum(1 for row in rows if row["修剪状态"] == "待修剪"),
            "修剪中": sum(1 for row in rows if row["修剪状态"] == "修剪中"),
            "已完成": sum(1 for row in rows if row["修剪状态"] == "已完成"),
            "待返工": sum(1 for row in rows if row["修剪状态"] == "需返工"),
            "待补": sum(1 for row in rows if row["修剪状态"] == "待补"),
        }

    # ---- 建档与补录 -----------------------------------------------------------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not _text(values.get(field))]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        code = _text(values.get("修剪编号"))
        if any(_text(row.get("修剪编号")) == code for row in rows):
            return None, [f"修剪编号 {code} 已存在，不能重复建档"]

        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "修剪编号": code,
            "修剪对象": _text(values.get("修剪对象")),
            "修剪类型": _text(values.get("修剪类型")),
            "造型要求": _text(values.get("造型要求")),
            "作业日期": _text(values.get("作业日期")),
            "操作人员": _text(values.get("操作人员")),
            "修剪量": None,
            "修剪量状态": None,
            "修剪量错误": "",
            "取数次数": 0,
            "已提交": False,
            "返工快照": None,
        }
        # 建档后自动取一次修剪量；取数结果决定是待修剪还是待补
        self._fetch_quantity(entry)
        entry["status"] = "待补" if missing_reasons(entry) else "待修剪"
        rows.append(entry)
        return _present(entry), []

    def supplement(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """补录缺项：造型要求/作业日期等字段或手工修剪量。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"修剪任务 {entry_id} 不存在或已归档"

        for field in ("造型要求", "作业日期", "操作人员", "修剪对象"):
            if field in values and _text(values.get(field)):
                entry[field] = _text(values.get(field))

        if "修剪量" in values and _text(values.get("修剪量")):
            amount = self._parse_amount(values.get("修剪量"))
            if amount is None:
                return _present(entry), "补录的修剪量需为非负数值，未保存"
            entry["修剪量"] = amount
            entry["修剪量状态"] = QTY_OK
            entry["修剪量错误"] = ""

        # 补齐后：返工单维持返工态，其余缺项单回到待修剪
        if entry["status"] == "待补" and not missing_reasons(entry):
            entry["status"] = "待修剪"
        return _present(entry), "缺项已补录" if not missing_reasons(entry) else "仍有缺项待补"

    # ---- 修剪量取数 -----------------------------------------------------------

    def fetch_quantity(self, entry_id: int) -> tuple[dict[str, Any] | None, str, bool]:
        """重新向计量服务取修剪量。返回 (明细, 说明, 是否取到)。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"修剪任务 {entry_id} 不存在或已归档", False
        state = self._fetch_quantity(entry)
        if state == QTY_OK:
            if entry["status"] == "待补" and not missing_reasons(entry):
                entry["status"] = "待修剪"
            return _present(entry), f"修剪量取数成功：{entry['修剪量']}", True
        if state == QTY_EMPTY:
            return _present(entry), "计量清单为空，取数重试无意义，请直接人工补录修剪量", False
        return _present(entry), f"修剪量仍取数失败：{entry.get('修剪量错误') or '计量服务不可用'}，可稍后重试或人工补录", False

    def _fetch_quantity(self, entry: dict[str, Any]) -> str:
        """模拟外部计量服务：按编号决定成功/失败/空清单，并把结论写回记录。"""
        entry["取数次数"] = int(entry.get("取数次数", 0)) + 1
        code = _text(entry.get("修剪编号"))
        if code.startswith(FETCH_FAIL_PREFIX):
            entry["修剪量状态"] = QTY_FAILED
            entry["修剪量错误"] = "对接的修剪量计量服务暂不可用（HTTP 503）"
            return QTY_FAILED
        if entry.get("修剪量状态") is None:
            # 建档时未预置计量数据的对象，按空清单处理，引导人工补录
            entry["修剪量状态"] = QTY_EMPTY
            entry["修剪量错误"] = "计量清单为空：该对象本期暂无待修剪计量数据"
            return QTY_EMPTY
        # 已带量或已补录的对象，取数保持原值成功
        state = entry.get("修剪量状态")
        return state if state in (QTY_OK, QTY_EMPTY, QTY_FAILED) else QTY_EMPTY

    @staticmethod
    def _parse_amount(value: Any) -> float | int | None:
        text = _text(value)
        try:
            amount = float(text)
        except ValueError:
            return None
        if amount < 0:
            return None
        return int(amount) if amount.is_integer() else amount

    # ---- 状态流转 -------------------------------------------------------------

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str, bool]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"修剪任务 {entry_id} 不存在或已归档", False
        rule = ACTION_RULES.get(action)
        if rule is None:
            return None, f"动作「{action}」不属于修剪造型可执行范围", False

        current = entry["status"]

        # 幂等优先于状态守卫：同一单的正式提交只认第一次，重复点提交明确拒绝
        if action == "开始修剪" and entry.get("已提交"):
            return _present(entry), "该修剪单已提交过，重复提交不再受理，以第一次提交为准", False

        if current not in rule["from"]:
            return None, f"当前状态「{current}」不允许执行「{action}」", False

        target = rule["to"]

        if action == "安排修剪":
            # 安排前先确保取过数：没取过的先取，取不到的按失败/空清单分流
            if entry.get("修剪量状态") not in (QTY_OK, QTY_FAILED, QTY_EMPTY):
                self._fetch_quantity(entry)
            reasons = missing_reasons(entry)
            if reasons:
                # 缺项单按「待补」挂起并说明原因，不允许带着缺项进入修剪中
                entry["status"] = "待补"
                return _present(entry), "暂不能安排修剪，缺项已按待补列出：" + "；".join(reasons), False

        if action == "开始修剪":
            # 正式提交完工前再兜底核对一次缺项与修剪量
            reasons = missing_reasons(entry)
            if reasons:
                entry["status"] = "待补"
                return _present(entry), "暂不能提交，缺项已按待补列出：" + "；".join(reasons), False

        if action == "返工登记":
            # 留住原修剪结果与已填修剪量，供返工中途断掉后接回
            entry["返工快照"] = {
                "原状态": current,
                "修剪量": entry.get("修剪量"),
                "造型要求": entry.get("造型要求"),
                "作业日期": entry.get("作业日期"),
                "操作人员": entry.get("操作人员"),
            }

        if action == "返工完成":
            snapshot = entry.get("返工快照")
            if snapshot:
                # 返工中途断掉也能接回原修剪结果；已填修剪量优先保留，没填则接回原值
                if entry.get("修剪量状态") != QTY_OK or entry.get("修剪量") is None:
                    entry["修剪量"] = snapshot.get("修剪量")
                entry["修剪量状态"] = QTY_OK
                entry["修剪量错误"] = ""
                if not _text(entry.get("造型要求")):
                    entry["造型要求"] = snapshot.get("造型要求")
                entry["返工快照"] = None

        entry["status"] = target
        if action == "开始修剪":
            entry["已提交"] = True
        return _present(entry), self._success_message(action, entry), True

    @staticmethod
    def _success_message(action: str, entry: dict[str, Any]) -> str:
        if action == "返工完成":
            return "返工已完成，已接回原修剪结果并保留修剪量"
        if action == "返工登记":
            return "已登记返工，原修剪结果已留存，可随时返工接回"
        if action == "开始修剪":
            return "修剪结果已提交，同一单重复提交只认第一次"
        return f"修剪任务已{action}"


def _overview(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """全局看板里的修剪口径：待处理含待办与缺项，异常量即待补与待返工之和。"""
    presented = [_present(row) for row in rows]
    pending = sum(1 for row in presented if row["修剪状态"] not in ("已完成",))
    abnormal = sum(1 for row in presented if row["修剪状态"] in ("待补", "需返工"))
    return pending, abnormal


# 挂到全局看板，确保 overview 与修剪页明细同源、随明细重算
register_overview(MODULE, _overview)
