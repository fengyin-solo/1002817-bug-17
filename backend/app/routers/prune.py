"""修剪造型接口：维护修剪任务，覆盖安排修剪、开始修剪、返工登记、取数与补录等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.prune import PruneService

router = APIRouter(prefix="/api/prune", tags=["修剪造型"])

service = PruneService()

LIST_FIELDS = ["修剪编号", "修剪对象", "修剪类型", "修剪量", "造型要求", "作业日期", "操作人员", "修剪状态"]
STATUSES = ["待修剪", "修剪中", "已完成", "需返工", "待补"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按修剪编号检索"),
    status: str | None = Query(default=None, description="待修剪、修剪中、已完成、需返工、待补"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按修剪编号与状态过滤修剪造型列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats", response_model=dict[str, int])
def prune_stats() -> dict[str, int]:
    """修剪看板统计：待返工等数字实时按明细重算。"""
    return service.stats()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出修剪造型清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "prune", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条修剪任务明细；与列表同一个序列化出口，修剪量等字段保持一致。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"修剪任务 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条修剪任务；同一修剪编号重复提交只认第一次，缺项按待补说明。"""
    entry, message, ok = service.create_entry(payload.values)
    return ActionResult(ok=ok, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条修剪任务执行安排修剪、开始修剪、返工登记、接回原结果；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message, ok = service.run_action(entry_id, action)
    return ActionResult(ok=ok, message=message, entry=entry)


@router.post("/{entry_id}/fetch-quantity", response_model=ActionResult)
def fetch_quantity(entry_id: int) -> ActionResult:
    """从测量系统取修剪量；取不到时返回失败原因，前端据此提示重试或补录。"""
    entry, message, ok = service.fetch_quantity(entry_id)
    return ActionResult(ok=ok, message=message, entry=entry)


@router.post("/{entry_id}/supplement", response_model=ActionResult)
def supplement(entry_id: int, payload: EntryPayload) -> ActionResult:
    """补录缺项字段：只填空缺，已有值（含已填的修剪量）不覆盖。"""
    entry, message, ok = service.supplement(entry_id, payload.values)
    return ActionResult(ok=ok, message=message, entry=entry)
