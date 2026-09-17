"""馆藏盘点:任务发起 → 逐件盘点 → 差异复核 → 调整审批 → 结案归档。

关键约束:
- 同一藏品在同一时间只能被一个「进行中」任务占用(创建任务与盘盈登记时校验);
- 差异必须经复核后才允许提请调整,调整审批通过时才改写正式藏品档案;
- 全部明细已盘、差异已复核、调整已处理后方可结案,结案汇总与处理痕迹留档可溯。
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/inventory", tags=["馆藏盘点"])


# ---------- 序列化 ----------
def _log(item: models.InventoryItem, actor: str, action: str, note: str | None = None):
    logs = list(item.logs or [])
    logs.append(
        {
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "actor": actor,
            "action": action,
            "note": note,
        }
    )
    item.logs = logs


def _task_stats(task: models.InventoryTask) -> dict:
    counts: dict[str, int] = {}
    pending_review = 0
    pending_adjust = 0
    for it in task.items:
        counts[it.result] = counts.get(it.result, 0) + 1
        if it.review_status == models.INV_REVIEW_PENDING:
            pending_review += 1
        pending_adjust += sum(
            1 for a in it.adjustments if a.status == models.INV_ADJUST_PENDING
        )
    total = len(task.items)
    checked = total - counts.get(models.INV_RESULT_PENDING, 0)
    diff = sum(counts.get(r, 0) for r in models.INV_DIFF_RESULTS)
    return {
        "total": total,
        "checked": checked,
        "diff_count": diff,
        "pending_review": pending_review,
        "pending_adjust": pending_adjust,
        "result_counts": counts,
    }


def _scope_label(task: models.InventoryTask) -> str:
    if task.scope_type == models.INV_SCOPE_LOCATION and task.scope_location:
        return f"{task.scope_location.code} {task.scope_location.name}"
    return f"{task.scope_type}:{task.scope_value}"


def _serialize_task(task: models.InventoryTask) -> schemas.InventoryTaskOut:
    out = schemas.InventoryTaskOut.model_validate(task)
    out.scope_label = _scope_label(task)
    for k, v in _task_stats(task).items():
        setattr(out, k, v)
    if task.status == models.INV_TASK_ACTIVE:
        out.days_remaining = (task.deadline - date.today()).days
    return out


def _serialize_item(item: models.InventoryItem) -> schemas.InventoryItemOut:
    out = schemas.InventoryItemOut.model_validate(item)
    c = item.collection
    if c:
        out.accession_no = c.accession_no
        out.collection_name = c.name
        out.category = c.category
        out.grade = c.grade
    out.book_location_name = item.book_location.name if item.book_location else None
    out.actual_location_name = (
        item.actual_location.name if item.actual_location else None
    )
    adjs = []
    for a in item.adjustments:
        ao = schemas.InventoryAdjustmentOut.model_validate(a)
        ao.to_location_name = a.to_location.name if a.to_location else None
        adjs.append(ao)
    out.adjustments = adjs
    return out


def _get_task_or_404(db: Session, task_id: int) -> models.InventoryTask:
    t = db.get(models.InventoryTask, task_id)
    if not t:
        raise HTTPException(404, "盘点任务不存在")
    return t


def _active_collection_ids(db: Session, exclude_task_id: int | None = None) -> set[int]:
    """被「进行中」任务占用的藏品 id 集合(互斥占用约束)。"""
    q = (
        db.query(models.InventoryItem.collection_id)
        .join(models.InventoryTask, models.InventoryItem.task_id == models.InventoryTask.id)
        .filter(models.InventoryTask.status == models.INV_TASK_ACTIVE)
    )
    if exclude_task_id:
        q = q.filter(models.InventoryTask.id != exclude_task_id)
    return {r[0] for r in q.all()}


# ---------- 任务 ----------
@router.get("/tasks", response_model=list[schemas.InventoryTaskOut])
def list_tasks(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(models.InventoryTask).options(
        joinedload(models.InventoryTask.scope_location),
        joinedload(models.InventoryTask.items).joinedload(models.InventoryItem.adjustments),
    )
    if status:
        q = q.filter(models.InventoryTask.status == status)
    rows = q.order_by(models.InventoryTask.created_at.desc()).all()
    return [_serialize_task(t) for t in rows]


@router.post("/tasks", response_model=schemas.InventoryTaskOut)
def create_task(payload: schemas.InventoryTaskCreate, db: Session = Depends(get_db)):
    if payload.scope_type not in (
        models.INV_SCOPE_LOCATION,
        models.INV_SCOPE_CATEGORY,
        models.INV_SCOPE_GRADE,
    ):
        raise HTTPException(400, "盘点范围类型须为:库房 / 类别 / 等级")
    if payload.deadline < date.today():
        raise HTTPException(400, "截止日期不能早于今天")

    q = db.query(models.Collection)
    if payload.scope_type == models.INV_SCOPE_LOCATION:
        if not payload.scope_location_id:
            raise HTTPException(400, "按库房盘点必须选择库房")
        loc = db.get(models.Location, payload.scope_location_id)
        if not loc:
            raise HTTPException(404, "库房不存在")
        q = q.filter(models.Collection.location_id == loc.id)
    elif payload.scope_type == models.INV_SCOPE_CATEGORY:
        if not payload.scope_value:
            raise HTTPException(400, "按类别盘点必须选择类别")
        q = q.filter(models.Collection.category == payload.scope_value)
    else:
        if not payload.scope_value:
            raise HTTPException(400, "按等级盘点必须选择等级")
        q = q.filter(models.Collection.grade == payload.scope_value)
    collections = q.order_by(models.Collection.accession_no).all()
    if not collections:
        raise HTTPException(400, "该盘点范围内没有藏品,无法发起任务")

    # 互斥占用:同一藏品不能被多个进行中任务重复占用
    occupied = _active_collection_ids(db)
    conflicts = [c for c in collections if c.id in occupied]
    if conflicts:
        names = "、".join(f"{c.accession_no} {c.name}" for c in conflicts[:5])
        more = f" 等 {len(conflicts)} 件" if len(conflicts) > 5 else ""
        raise HTTPException(
            409, f"{names}{more}已被其他进行中的盘点任务占用,请先结案或取消该任务"
        )

    task = models.InventoryTask(
        code="TMP",
        title=payload.title,
        scope_type=payload.scope_type,
        scope_location_id=(
            payload.scope_location_id
            if payload.scope_type == models.INV_SCOPE_LOCATION
            else None
        ),
        scope_value=(
            payload.scope_value
            if payload.scope_type != models.INV_SCOPE_LOCATION
            else None
        ),
        initiator=payload.initiator,
        deadline=payload.deadline,
        remark=payload.remark,
    )
    db.add(task)
    db.flush()
    task.code = f"PD-{datetime.now():%Y%m%d}-{task.id:03d}"

    for c in collections:
        db.add(
            models.InventoryItem(
                task_id=task.id,
                collection_id=c.id,
                book_location_id=c.location_id,
                book_status=c.status,
            )
        )
    db.commit()
    db.refresh(task)
    return _serialize_task(task)


@router.get("/tasks/{task_id}", response_model=schemas.InventoryTaskDetail)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = (
        db.query(models.InventoryTask)
        .options(
            joinedload(models.InventoryTask.scope_location),
            joinedload(models.InventoryTask.items).joinedload(
                models.InventoryItem.collection
            ),
            joinedload(models.InventoryTask.items).joinedload(
                models.InventoryItem.book_location
            ),
            joinedload(models.InventoryTask.items).joinedload(
                models.InventoryItem.actual_location
            ),
            joinedload(models.InventoryTask.items)
            .joinedload(models.InventoryItem.adjustments)
            .joinedload(models.InventoryAdjustment.to_location),
        )
        .filter(models.InventoryTask.id == task_id)
        .first()
    )
    if not task:
        raise HTTPException(404, "盘点任务不存在")
    out = schemas.InventoryTaskDetail(**_serialize_task(task).model_dump())
    out.items = [_serialize_item(it) for it in task.items]
    return out


@router.post("/tasks/{task_id}/cancel", response_model=schemas.InventoryTaskOut)
def cancel_task(task_id: int, db: Session = Depends(get_db)):
    task = _get_task_or_404(db, task_id)
    if task.status != models.INV_TASK_ACTIVE:
        raise HTTPException(400, "仅进行中的任务可以取消")
    pending = sum(
        1
        for it in task.items
        for a in it.adjustments
        if a.status == models.INV_ADJUST_PENDING
    )
    if pending:
        raise HTTPException(400, f"尚有 {pending} 条调整申请待审批,请先处理后再取消")
    task.status = models.INV_TASK_CANCELLED
    task.closed_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return _serialize_task(task)


@router.post("/tasks/{task_id}/close", response_model=schemas.InventoryTaskOut)
def close_task(
    task_id: int, payload: schemas.InventoryTaskClose, db: Session = Depends(get_db)
):
    task = _get_task_or_404(db, task_id)
    if task.status != models.INV_TASK_ACTIVE:
        raise HTTPException(400, "任务已结案或已取消")
    stats = _task_stats(task)
    unchecked = stats["total"] - stats["checked"]
    if unchecked:
        raise HTTPException(400, f"尚有 {unchecked} 件未盘点,不能结案")
    if stats["pending_review"]:
        raise HTTPException(
            400, f"尚有 {stats['pending_review']} 条差异未复核,不能结案"
        )
    if stats["pending_adjust"]:
        raise HTTPException(
            400, f"尚有 {stats['pending_adjust']} 条调整申请待审批,不能结案"
        )

    counts = stats["result_counts"]
    executed = rejected = 0
    handlers = sorted({it.checked_by for it in task.items if it.checked_by})
    for it in task.items:
        for a in it.adjustments:
            if a.status == models.INV_ADJUST_EXECUTED:
                executed += 1
            elif a.status == models.INV_ADJUST_REJECTED:
                rejected += 1
    task.summary = {
        "总数": stats["total"],
        "正常": counts.get(models.INV_RESULT_NORMAL, 0),
        "错位": counts.get(models.INV_RESULT_MISPLACED, 0),
        "损坏": counts.get(models.INV_RESULT_DAMAGED, 0),
        "盘亏": counts.get(models.INV_RESULT_LOSS, 0),
        "盘盈": counts.get(models.INV_RESULT_SURPLUS, 0),
        "调整已执行": executed,
        "调整已驳回": rejected,
        "盘点人员": handlers,
    }
    task.status = models.INV_TASK_CLOSED
    task.closed_at = datetime.utcnow()
    task.closed_by = payload.closed_by
    db.commit()
    db.refresh(task)
    return _serialize_task(task)


# ---------- 盘点登记 ----------
def _apply_check(
    item: models.InventoryItem,
    result: str,
    checker: str,
    actual_location_id: int | None,
    condition_note: str | None,
):
    item.result = result
    item.actual_location_id = actual_location_id
    item.condition_note = condition_note
    item.checked_by = checker
    item.checked_at = datetime.utcnow()
    item.review_status = (
        models.INV_REVIEW_PENDING
        if result in models.INV_DIFF_RESULTS
        else models.INV_REVIEW_NONE
    )
    loc_hint = ""
    if actual_location_id and item.actual_location:
        loc_hint = f",实物位置:{item.actual_location.name}"
    _log(item, checker, f"盘点登记:{result}", (condition_note or "") + loc_hint)


@router.post("/tasks/{task_id}/scan", response_model=schemas.InventoryItemOut)
def scan_item(
    task_id: int, payload: schemas.InventoryScanRequest, db: Session = Depends(get_db)
):
    task = _get_task_or_404(db, task_id)
    if task.status != models.INV_TASK_ACTIVE:
        raise HTTPException(400, "任务已结案或已取消,不能登记盘点")

    c = (
        db.query(models.Collection)
        .filter(models.Collection.accession_no == payload.accession_no.strip())
        .first()
    )
    if not c:
        raise HTTPException(404, f"未找到登记号为 {payload.accession_no} 的藏品")

    item = next((it for it in task.items if it.collection_id == c.id), None)
    actual_loc_id = payload.actual_location_id
    if actual_loc_id and not db.get(models.Location, actual_loc_id):
        raise HTTPException(404, "实物位置不存在")

    if item is None:
        # 任务范围外藏品 → 盘盈;同样受互斥占用约束
        if c.id in _active_collection_ids(db, exclude_task_id=task.id):
            raise HTTPException(409, "该藏品已被其他进行中的盘点任务占用")
        if actual_loc_id is None and task.scope_type == models.INV_SCOPE_LOCATION:
            actual_loc_id = task.scope_location_id
        item = models.InventoryItem(
            task_id=task.id,
            collection_id=c.id,
            book_location_id=c.location_id,
            book_status=c.status,
        )
        db.add(item)
        db.flush()
        db.refresh(item)
        _apply_check(
            item, models.INV_RESULT_SURPLUS, payload.checker, actual_loc_id,
            payload.condition_note,
        )
    else:
        if item.result != models.INV_RESULT_PENDING:
            raise HTTPException(400, "该藏品在本任务中已盘点,请勿重复登记")
        if actual_loc_id is None:
            actual_loc_id = item.book_location_id
        if payload.damaged:
            result = models.INV_RESULT_DAMAGED
        elif actual_loc_id != item.book_location_id:
            result = models.INV_RESULT_MISPLACED
        else:
            result = models.INV_RESULT_NORMAL
        _apply_check(item, result, payload.checker, actual_loc_id, payload.condition_note)

    db.commit()
    db.refresh(item)
    return _serialize_item(item)


@router.post("/items/{item_id}/check", response_model=schemas.InventoryItemOut)
def check_item(
    item_id: int, payload: schemas.InventoryItemCheck, db: Session = Depends(get_db)
):
    item = db.get(models.InventoryItem, item_id)
    if not item:
        raise HTTPException(404, "盘点明细不存在")
    task = _get_task_or_404(db, item.task_id)
    if task.status != models.INV_TASK_ACTIVE:
        raise HTTPException(400, "任务已结案或已取消,不能登记盘点")
    if item.result != models.INV_RESULT_PENDING:
        raise HTTPException(400, "该藏品已盘点,如需更正请先由复核退回")
    allowed = (
        models.INV_RESULT_NORMAL,
        models.INV_RESULT_MISPLACED,
        models.INV_RESULT_DAMAGED,
        models.INV_RESULT_LOSS,
    )
    if payload.result not in allowed:
        raise HTTPException(400, f"盘点结果须为:{' / '.join(allowed)}")
    if payload.result == models.INV_RESULT_MISPLACED:
        if not payload.actual_location_id:
            raise HTTPException(400, "登记错位须选择实物所在位置")
        if payload.actual_location_id == item.book_location_id:
            raise HTTPException(400, "实物位置与账面一致,不属于错位")
    if payload.actual_location_id and not db.get(models.Location, payload.actual_location_id):
        raise HTTPException(404, "实物位置不存在")

    actual_loc_id = payload.actual_location_id
    if payload.result == models.INV_RESULT_LOSS:
        actual_loc_id = None
    elif payload.result == models.INV_RESULT_NORMAL and actual_loc_id is None:
        actual_loc_id = item.book_location_id
    _apply_check(
        item, payload.result, payload.checker, actual_loc_id, payload.condition_note
    )
    db.commit()
    db.refresh(item)
    return _serialize_item(item)


# ---------- 复核 ----------
@router.post("/items/{item_id}/review", response_model=schemas.InventoryItemOut)
def review_item(
    item_id: int, payload: schemas.InventoryReviewRequest, db: Session = Depends(get_db)
):
    item = db.get(models.InventoryItem, item_id)
    if not item:
        raise HTTPException(404, "盘点明细不存在")
    task = _get_task_or_404(db, item.task_id)
    if task.status != models.INV_TASK_ACTIVE:
        raise HTTPException(400, "任务已结案或已取消,不能复核")
    if item.review_status != models.INV_REVIEW_PENDING:
        raise HTTPException(400, "该明细不在待复核状态")

    if payload.approve:
        item.review_status = models.INV_REVIEW_DONE
        item.reviewed_by = payload.reviewer
        item.reviewed_at = datetime.utcnow()
        item.review_note = payload.note
        _log(item, payload.reviewer, "复核通过", payload.note)
    else:
        # 复核退回:回到未盘,由盘点人重新核对(痕迹保留在 logs)
        _log(item, payload.reviewer, f"复核退回(原结果:{item.result})", payload.note)
        item.result = models.INV_RESULT_PENDING
        item.review_status = models.INV_REVIEW_NONE
        item.actual_location_id = None
        item.condition_note = None
        item.checked_by = None
        item.checked_at = None
        item.reviewed_by = payload.reviewer
        item.reviewed_at = datetime.utcnow()
        item.review_note = payload.note
    db.commit()
    db.refresh(item)
    return _serialize_item(item)


# ---------- 调整申请 ----------
@router.post(
    "/items/{item_id}/adjustments", response_model=schemas.InventoryAdjustmentOut
)
def create_adjustment(
    item_id: int, payload: schemas.InventoryAdjustmentCreate, db: Session = Depends(get_db)
):
    item = db.get(models.InventoryItem, item_id)
    if not item:
        raise HTTPException(404, "盘点明细不存在")
    task = _get_task_or_404(db, item.task_id)
    if task.status != models.INV_TASK_ACTIVE:
        raise HTTPException(400, "任务已结案或已取消,不能提请调整")
    # 差异未复核前不能直接改写正式档案:调整申请须以复核通过为前提
    if item.review_status != models.INV_REVIEW_DONE:
        raise HTTPException(400, "差异须先复核通过,才能提请调整")
    if any(a.status == models.INV_ADJUST_PENDING for a in item.adjustments):
        raise HTTPException(400, "该明细已有待审批的调整申请")

    if payload.adjust_type == models.INV_ADJUST_LOCATION:
        if not payload.to_location_id:
            raise HTTPException(400, "变更位置须选择目标位置")
        if not db.get(models.Location, payload.to_location_id):
            raise HTTPException(404, "目标位置不存在")
    elif payload.adjust_type == models.INV_ADJUST_STATUS:
        if not payload.to_status:
            raise HTTPException(400, "状态变更须选择目标状态")
    elif payload.adjust_type != models.INV_ADJUST_DAMAGE:
        raise HTTPException(
            400,
            f"调整类型须为:{models.INV_ADJUST_LOCATION} / "
            f"{models.INV_ADJUST_STATUS} / {models.INV_ADJUST_DAMAGE}",
        )

    adj = models.InventoryAdjustment(
        item_id=item.id,
        adjust_type=payload.adjust_type,
        to_location_id=payload.to_location_id,
        to_status=payload.to_status,
        reason=payload.reason,
        applicant=payload.applicant,
    )
    db.add(adj)
    _log(
        item,
        payload.applicant,
        f"提请调整:{payload.adjust_type}",
        payload.reason,
    )
    db.commit()
    db.refresh(adj)
    out = schemas.InventoryAdjustmentOut.model_validate(adj)
    out.to_location_name = adj.to_location.name if adj.to_location else None
    return out


def _apply_adjustment(
    db: Session, adj: models.InventoryAdjustment, processor: str, note: str | None
):
    """审批通过,正式改写藏品档案并登记流转台账。"""
    item = adj.item
    task = item.task
    c = item.collection
    now = datetime.utcnow()
    ref = f"盘点任务 {task.code}"

    if adj.adjust_type == models.INV_ADJUST_LOCATION:
        old_loc = c.location_id
        c.location_id = adj.to_location_id
        if c.status in (models.STATUS_OUT_STORAGE, models.STATUS_MISSING):
            c.status = models.STATUS_IN_STORAGE
        db.add(
            models.Movement(
                collection_id=c.id,
                move_type=models.MOVE_INVENTORY_ADJUST,
                from_location_id=old_loc,
                to_location_id=adj.to_location_id,
                purpose=f"盘点调整({item.result}):{ref}",
                operator=processor,
                move_date=now,
                remark=adj.reason,
            )
        )
    elif adj.adjust_type == models.INV_ADJUST_STATUS:
        old_status = c.status
        c.status = adj.to_status
        if adj.to_status == models.STATUS_MISSING:
            c.location_id = None
        db.add(
            models.Movement(
                collection_id=c.id,
                move_type=models.MOVE_INVENTORY_ADJUST,
                from_location_id=c.location_id,
                purpose=f"盘点状态调整:{old_status} → {adj.to_status}({ref})",
                operator=processor,
                move_date=now,
                remark=adj.reason,
            )
        )
    else:  # 损坏登记:仅留痕,不改动位置与状态
        db.add(
            models.Movement(
                collection_id=c.id,
                move_type=models.MOVE_INVENTORY_ADJUST,
                from_location_id=c.location_id,
                to_location_id=c.location_id,
                purpose=f"盘点损坏登记({ref})",
                operator=processor,
                move_date=now,
                remark=adj.reason,
            )
        )
    adj.status = models.INV_ADJUST_EXECUTED
    adj.processed_by = processor
    adj.processed_at = now
    adj.process_note = note
    _log(item, processor, f"调整已执行:{adj.adjust_type}", note)


@router.post(
    "/adjustments/{adjustment_id}/approve", response_model=schemas.InventoryAdjustmentOut
)
def approve_adjustment(
    adjustment_id: int,
    payload: schemas.InventoryAdjustmentProcess,
    db: Session = Depends(get_db),
):
    adj = db.get(models.InventoryAdjustment, adjustment_id)
    if not adj:
        raise HTTPException(404, "调整申请不存在")
    if adj.status != models.INV_ADJUST_PENDING:
        raise HTTPException(400, "该申请已处理")
    if adj.item.task.status != models.INV_TASK_ACTIVE:
        raise HTTPException(400, "所属任务已结案或取消")
    _apply_adjustment(db, adj, payload.processor, payload.note)
    db.commit()
    db.refresh(adj)
    out = schemas.InventoryAdjustmentOut.model_validate(adj)
    out.to_location_name = adj.to_location.name if adj.to_location else None
    return out


@router.post(
    "/adjustments/{adjustment_id}/reject", response_model=schemas.InventoryAdjustmentOut
)
def reject_adjustment(
    adjustment_id: int,
    payload: schemas.InventoryAdjustmentProcess,
    db: Session = Depends(get_db),
):
    adj = db.get(models.InventoryAdjustment, adjustment_id)
    if not adj:
        raise HTTPException(404, "调整申请不存在")
    if adj.status != models.INV_ADJUST_PENDING:
        raise HTTPException(400, "该申请已处理")
    adj.status = models.INV_ADJUST_REJECTED
    adj.processed_by = payload.processor
    adj.processed_at = datetime.utcnow()
    adj.process_note = payload.note
    _log(adj.item, payload.processor, f"调整已驳回:{adj.adjust_type}", payload.note)
    db.commit()
    db.refresh(adj)
    out = schemas.InventoryAdjustmentOut.model_validate(adj)
    out.to_location_name = adj.to_location.name if adj.to_location else None
    return out
