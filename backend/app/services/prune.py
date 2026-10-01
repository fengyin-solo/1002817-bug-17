"""修剪造型业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "prune"
IDENTITY_FIELD = "修剪编号"
QUANTITY_FIELD = "修剪量"
QUANTITY_SOURCE_FIELD = "修剪量来源"
REWORK_SNAPSHOT_FIELD = "原修剪结果"
# 登记后仍要补齐的字段：缺了按“待补”展示并说明原因，补齐前不允许完工
SUPPLEMENT_FIELDS = ["修剪对象", "修剪类型", "造型要求"]
# 允许通过补录写入的字段；已有值的字段一律不覆盖
FILLABLE_FIELDS = ["修剪对象", "修剪类型", "造型要求", "修剪量", "作业日期", "操作人员"]
STATUS_ORDER = ["待修剪", "修剪中", "已完成", "需返工"]
PENDING_SUPPLEMENT_STATUS = "待补"
# 模拟外部测量系统：按修剪编号取修剪量；取不到编号时视为取数失败，走重试或人工补录
MEASUREMENT_SOURCE = {
    "PRUN-0001": "120株",
    "PRUN-0002": "260平方米",
    "PRUN-0003": "80株",
}
# 动作 -> 流转规则；requires_complete 表示完工前必须没有待补字段
ACTION_RULES: dict[str, dict[str, Any]] = {
    "安排修剪": {"from": {"待修剪"}, "to": "修剪中"},
    "开始修剪": {"from": {"修剪中"}, "to": "已完成", "requires_complete": True},
    "返工登记": {"from": {"已完成"}, "to": "需返工", "snapshot": True},
    "接回原结果": {"from": {"需返工"}, "restore": True},
}


class PruneService:
    def missing_fields(self, entry: dict[str, Any]) -> list[str]:
        """缺项口径：应填字段 + 修剪量，任一为空都算待补。"""
        missing = [
            field
            for field in SUPPLEMENT_FIELDS
            if not str(entry.get(field) or "").strip()
        ]
        if not str(entry.get(QUANTITY_FIELD) or "").strip():
            missing.append(QUANTITY_FIELD)
        return missing

    def present(self, entry: dict[str, Any]) -> dict[str, Any]:
        """列表、详情、导出共用的序列化出口，保证各处读到的修剪量等字段一致。"""
        data = dict(entry)
        data["修剪状态"] = str(entry.get("status") or "")
        missing = self.missing_fields(entry)
        data["待补字段"] = missing
        data["待补原因"] = "、".join(missing)
        return data

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
            rows = [row for row in rows if keyword in str(row.get(IDENTITY_FIELD, ""))]
        if status == PENDING_SUPPLEMENT_STATUS:
            rows = [row for row in rows if self.missing_fields(row)]
        elif status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self.present(entry) if entry is not None else None

    def stats(self) -> dict[str, int]:
        """修剪看板统计：待返工等数字每次都按明细重算，不缓存。"""
        rows = store.rows(MODULE)
        counts = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            status = str(row.get("status") or "")
            if status in counts:
                counts[status] += 1
        counts[PENDING_SUPPLEMENT_STATUS] = sum(1 for row in rows if self.missing_fields(row))
        counts["total"] = len(rows)
        return counts

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        code = str(values.get(IDENTITY_FIELD) or "").strip()
        if not code:
            return None, "缺少必填字段：修剪编号", False
        existing = self._find_by_code(code)
        if existing is not None:
            return (
                self.present(existing),
                f"修剪编号 {code} 已登记，重复提交以首次为准，未重复建档",
                False,
            )
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry[IDENTITY_FIELD] = code
        for field in FILLABLE_FIELDS:
            value = str(values.get(field) or "").strip()
            if value:
                entry[field] = value
        if str(entry.get(QUANTITY_FIELD) or "").strip():
            entry[QUANTITY_SOURCE_FIELD] = "人工补录"
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        missing = self.missing_fields(entry)
        if missing:
            return self.present(entry), f"修剪任务已登记，待补字段：{'、'.join(missing)}，可取数或补录", True
        return self.present(entry), "修剪任务已登记", True

    def fetch_quantity(self, entry_id: int) -> tuple[dict[str, Any] | None, str, bool]:
        """从测量系统取修剪量；取不到时明确失败原因，由调用方提示重试或补录。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"修剪任务 {entry_id} 不存在或已归档", False
        current = str(entry.get(QUANTITY_FIELD) or "").strip()
        if current:
            return self.present(entry), f"修剪量已存在（{current}），无需重复取数", True
        code = str(entry.get(IDENTITY_FIELD) or "")
        value = MEASUREMENT_SOURCE.get(code)
        if value is None:
            return (
                self.present(entry),
                f"修剪量取数失败：测量系统暂时没有 {code} 的数据，可稍后重试或人工补录",
                False,
            )
        entry[QUANTITY_FIELD] = value
        entry[QUANTITY_SOURCE_FIELD] = "自动取数"
        return self.present(entry), f"修剪量取数成功：{value}", True

    def supplement(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str, bool]:
        """补录缺项：只填当前为空的字段，已有值不覆盖，已填的修剪量始终留住。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"修剪任务 {entry_id} 不存在或已归档", False
        filled: list[str] = []
        kept: list[str] = []
        for field in FILLABLE_FIELDS:
            value = str(values.get(field) or "").strip()
            if not value:
                continue
            if str(entry.get(field) or "").strip():
                kept.append(field)
                continue
            entry[field] = value
            filled.append(field)
        if QUANTITY_FIELD in filled:
            entry[QUANTITY_SOURCE_FIELD] = "人工补录"
        if not filled:
            return self.present(entry), "没有可补录的内容：待补字段未填写，或已有值无需覆盖", False
        message = f"已补录：{'、'.join(filled)}"
        if kept:
            message += f"；已有值未覆盖：{'、'.join(kept)}"
        remaining = self.missing_fields(entry)
        if remaining:
            message += f"；仍待补：{'、'.join(remaining)}"
        return self.present(entry), message, True

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str, bool]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"修剪任务 {entry_id} 不存在或已归档", False
        rule = ACTION_RULES.get(action)
        if rule is None:
            return None, f"动作「{action}」不属于修剪造型可执行范围", False
        current = str(entry.get("status") or "")
        if current not in rule["from"]:
            allowed = "、".join(sorted(rule["from"]))
            return None, f"当前状态「{current}」不允许{action}，仅「{allowed}」可执行", False
        if rule.get("requires_complete"):
            missing = self.missing_fields(entry)
            if missing:
                return (
                    self.present(entry),
                    f"存在待补字段（{'、'.join(missing)}），请先取数或补录再{action}",
                    False,
                )
        if rule.get("snapshot"):
            entry[REWORK_SNAPSHOT_FIELD] = {
                "status": current,
                QUANTITY_FIELD: entry.get(QUANTITY_FIELD),
                "造型要求": entry.get("造型要求"),
                "作业日期": entry.get("作业日期"),
                "操作人员": entry.get("操作人员"),
                "登记时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        if rule.get("restore"):
            snapshot = entry.get(REWORK_SNAPSHOT_FIELD)
            if not isinstance(snapshot, dict) or not snapshot.get("status"):
                return None, "没有可接回的原修剪结果，请核实返工登记是否完整", False
            entry["status"] = str(snapshot["status"])
            # 接回原结果时只补空缺：已填的修剪量等字段一律保留，不被快照覆盖
            for field in (QUANTITY_FIELD, "造型要求", "作业日期", "操作人员"):
                if not str(entry.get(field) or "").strip() and snapshot.get(field):
                    entry[field] = snapshot[field]
            message = "已接回原修剪结果，已填的修剪量保持不变"
        else:
            entry["status"] = str(rule["to"])
            message = f"修剪任务已{action}"
            if rule.get("snapshot"):
                message = "修剪任务已登记返工，原修剪结果已留存，可随时接回"
        entry["pending"] = entry["status"] != "已完成"
        entry["abnormal"] = entry["status"] == "需返工"
        return self.present(entry), message, True

    def _find_by_code(self, code: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if str(row.get(IDENTITY_FIELD) or "") == code:
                return row
        return None
