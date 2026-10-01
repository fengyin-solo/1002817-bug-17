"""修剪造型接口：维护修剪任务，覆盖建档、缺项补录、修剪量取数/重试与返工接回等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.prune import LIST_FIELDS, PruneService

router = APIRouter(prefix="/api/prune", tags=["修剪造型"])

service = PruneService()

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
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不在可选范围内")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, int]:
    """修剪看板统计：待返工数等待办指标始终由明细实时重算。"""
    return service.stats()


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条修剪任务明细；与列表共用同一展示口径，修剪量不会对不上。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"修剪任务 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条修剪任务，缺必填字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段或编号重复：{'、'.join(missing)}")
    if entry and entry.get("_待补"):
        return ActionResult(ok=True, message="修剪任务已登记，但存在待补项：" + "；".join(entry["_缺项"]), entry=entry)
    return ActionResult(ok=True, message="修剪任务已登记", entry=entry)


@router.patch("/{entry_id}", response_model=ActionResult)
def supplement_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """补录缺项：造型要求/作业日期等字段或人工修剪量；补全会自动退出待补。"""
    entry, message = service.supplement(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/quantity", response_model=ActionResult)
def fetch_quantity(entry_id: int) -> ActionResult:
    """重新向计量服务取修剪量：取数失败给重试入口，空清单则引导人工补录，两者不混为一谈。"""
    entry, message, ok = service.fetch_quantity(entry_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=ok, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条修剪任务执行安排修剪、开始修剪、返工登记、返工完成；不允许的动作、缺项、重复提交都会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message, accepted = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=accepted, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出修剪造型清单：返回当前全量数据，口径与列表一致。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "prune", "total": total, "fields": LIST_FIELDS, "items": items}
