from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..services import inventory_service as svc

router = APIRouter(prefix="/api/inventories", tags=["馆藏盘点"])


# ---------------- 序列化 ----------------
def _location_name(db: Session, loc_id: int | None) -> str | None:
    if not loc_id:
        return None
    loc = db.get(models.Location, loc_id)
    return f"{loc.code} {loc.name}" if loc else None


def _serialize_adjustment(a: models.InventoryAdjustment) -> schemas.InventoryAdjustmentOut:
    out = schemas.InventoryAdjustmentOut.model_validate(a)
    if a.collection:
        out.collection_name = a.collection.name
        out.accession_no = a.collection.accession_no
    return out


def _serialize_item(db: Session, item: models.InventoryItem) -> schemas.InventoryItemOut:
    out = schemas.InventoryItemOut.model_validate(item)
    out.adjustments = [_serialize_adjustment(a) for a in item.adjustments]
    if item.collection_id:
        c = db.get(models.Collection, item.collection_id)
        if c:
            out.current_location_name = _location_name(db, c.location_id)
            out.current_status = c.status
    return out


def _serialize_task(db: Session, task: models.InventoryTask, detail: bool = False):
    stats = svc.compute_stats(task)
    out = schemas.InventoryTaskOut.model_validate(task)
    for k, v in stats.items():
        setattr(out, k, v)
    if detail:
        out.items = [_serialize_item(db, i) for i in task.items]
        out.logs = [schemas.InventoryLogOut.model_validate(l) for l in task.logs]
    return out


def _get_task(db: Session, task_id: int) -> models.InventoryTask:
    task = db.get(models.InventoryTask, task_id)
    if not task:
        raise HTTPException(404, "盘点任务不存在")
    return task


# ---------------- 任务列表 / 范围预览 / 发起 ----------------
@router.get("", response_model=list[schemas.InventoryTaskOut])
def list_tasks(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(models.InventoryTask)
    if status:
        q = q.filter(models.InventoryTask.status == status)
    tasks = (
        q.options(joinedload(models.InventoryTask.items), joinedload(models.InventoryTask.adjustments))
        .order_by(models.InventoryTask.created_at.desc())
        .all()
    )
    return [_serialize_task(db, t) for t in tasks]


@router.get("/meta")
def inventory_meta(db: Session = Depends(get_db)):
    """发起盘点所需的候选库房 / 类别 / 等级。"""
    locations = [
        {"id": l.id, "label": f"{l.code} {l.name}"}
        for l in db.query(models.Location)
        .filter(models.Location.location_type == "库房")
        .order_by(models.Location.code)
        .all()
    ]
    categories = sorted(
        r[0] for r in db.query(models.Collection.category).distinct().all() if r[0]
    )
    grades = [
        r[0]
        for r in db.query(models.Collection.grade)
        .filter(models.Collection.grade.isnot(None))
        .distinct()
        .all()
        if r[0]
    ]
    grade_order = {"一级文物": 0, "二级文物": 1, "三级文物": 2, "一般文物": 3}
    grades.sort(key=lambda g: grade_order.get(g, 9))
    return {"locations": locations, "categories": categories, "grades": grades}


@router.get("/scope-preview", response_model=schemas.InventoryScopePreview)
def scope_preview(
    scope_type: str,
    scope_value: str,
    location_id: int | None = None,
    db: Session = Depends(get_db),
):
    q, loc_id = svc.resolve_scope(db, scope_type, scope_value, location_id)
    colls = q.order_by(models.Collection.accession_no).all()
    ids = [c.id for c in colls]
    conflicts = svc.find_active_conflicts(db, ids)
    busy_ids = {c["collection_id"] for c in conflicts}
    return schemas.InventoryScopePreview(
        scope_type=scope_type,
        scope_value=scope_value,
        location_id=loc_id,
        count=len(ids),
        occupied=len(busy_ids),
        conflicts=[
            {
                "collection_id": c["collection_id"],
                "accession_no": next(
                    (x.accession_no for x in colls if x.id == c["collection_id"]), ""
                ),
                "name": next((x.name for x in colls if x.id == c["collection_id"]), ""),
                **c,
            }
            for c in conflicts
        ],
    )


@router.post("", response_model=schemas.InventoryTaskOut)
def create_task(payload: schemas.InventoryCreate, db: Session = Depends(get_db)):
    if payload.due_date < (payload.start_date or date.today()):
        raise HTTPException(400, "盘点截止日期不能早于开始日期")

    q, loc_id = svc.resolve_scope(
        db, payload.scope_type, payload.scope_value, payload.location_id
    )
    colls = q.order_by(models.Collection.accession_no).all()
    if not colls:
        raise HTTPException(400, "所选范围内没有在账藏品,无法发起盘点")

    svc.ensure_no_conflict(db, [c.id for c in colls])

    task = models.InventoryTask(
        title=payload.title,
        scope_type=payload.scope_type,
        scope_value=payload.scope_value,
        location_id=loc_id,
        librarian=payload.librarian,
        checker=payload.checker,
        start_date=payload.start_date or date.today(),
        due_date=payload.due_date,
        status=models.INV_PENDING,
        remark=payload.remark,
    )
    db.add(task)
    db.flush()

    for c in colls:
        db.add(
            models.InventoryItem(
                task_id=task.id,
                collection_id=c.id,
                snapshot_accession_no=c.accession_no,
                snapshot_name=c.name,
                snapshot_location_id=c.location_id,
                snapshot_location_name=_location_name(db, c.location_id),
                snapshot_status=c.status,
            )
        )
    svc.add_log(
        db,
        task,
        "发起盘点",
        f"范围:{payload.scope_type}「{payload.scope_value}」,共 {len(colls)} 件;截止 {payload.due_date}",
        operator=payload.librarian,
    )
    db.commit()
    db.refresh(task)
    return _serialize_task(db, task, detail=True)


# ---------------- 任务详情 / 撤销 ----------------
@router.get("/{task_id}", response_model=schemas.InventoryTaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    return _serialize_task(db, _get_task(db, task_id), detail=True)


@router.post("/{task_id}/cancel", response_model=schemas.InventoryTaskOut)
def cancel_task(
    task_id: int,
    payload: schemas.InventoryCompleteIn,
    db: Session = Depends(get_db),
):
    task = _get_task(db, task_id)
    svc.active_status(task)
    task.status = models.INV_CANCELLED
    task.finished_at = datetime.utcnow()
    svc.add_log(db, task, "撤销任务", payload.summary, operator=payload.operator)
    db.commit()
    db.refresh(task)
    return _serialize_task(db, task, detail=True)


# ---------------- 盘点员逐件核对 ----------------
@router.post("/{task_id}/items/{item_id}/check", response_model=schemas.InventoryTaskOut)
def check_item(
    task_id: int,
    item_id: int,
    payload: schemas.InventoryCheckIn,
    db: Session = Depends(get_db),
):
    task = _get_task(db, task_id)
    svc.active_status(task)
    if task.status in (models.INV_REVIEWING, models.INV_ADJUSTING):
        raise HTTPException(400, "任务已进入复核 / 调整阶段,盘点结果不可再修改")
    item = db.get(models.InventoryItem, item_id)
    if not item or item.task_id != task_id:
        raise HTTPException(404, "盘点明细不存在")
    if item.collection_id is None:
        raise HTTPException(400, "账外盘盈条目请通过盘盈建档申请处理,不能按在册藏品核对")

    valid = {
        models.INV_RESULT_MATCH,
        models.INV_RESULT_SURPLUS,
        models.INV_RESULT_LOSS,
        models.INV_RESULT_MISPLACED,
        models.INV_RESULT_DAMAGED,
    }
    if payload.result not in valid:
        raise HTTPException(400, f"盘点结果必须是:{'/'.join(sorted(valid))}")

    c = db.get(models.Collection, item.collection_id)
    actual_name = None
    if payload.actual_location_id:
        loc = db.get(models.Location, payload.actual_location_id)
        if not loc:
            raise HTTPException(400, "实物所在位置不存在")
        actual_name = f"{loc.code} {loc.name}"
    else:
        payload.actual_location_id = c.location_id
        actual_name = item.snapshot_location_name

    # 错位自动校验:实物位置与账面位置不一致才允许登记为错位
    if payload.result == models.INV_RESULT_MISPLACED and (
        not payload.actual_location_id
        or payload.actual_location_id == item.snapshot_location_id
    ):
        raise HTTPException(400, "登记错位必须指定与账面不同的实物位置")
    if payload.result == models.INV_RESULT_LOSS:
        payload.actual_location_id = None
        actual_name = None

    item.result = payload.result
    item.actual_location_id = payload.actual_location_id
    item.actual_location_name = actual_name
    item.condition_note = payload.condition_note
    item.checker = payload.checker or task.checker or "盘点员"
    item.checked_at = datetime.utcnow()
    # 重新核对后,此前的复核结论作废,需要重新复核
    item.review_status = models.INV_REVIEW_PENDING
    item.review_opinion = None
    item.reviewer = None
    item.reviewed_at = None

    detail = f"{item.snapshot_accession_no} {item.snapshot_name}:{payload.result}"
    if actual_name and payload.result in (models.INV_RESULT_MISPLACED, models.INV_RESULT_MATCH):
        detail += f"(实物位置 {actual_name})"
    if payload.condition_note:
        detail += f";{payload.condition_note}"
    svc.add_log(db, task, "盘点核对", detail, operator=item.checker, item_id=item.id)
    svc.refresh_task_status(db, task)
    db.commit()
    db.refresh(task)
    return _serialize_task(db, task, detail=True)


# ---------------- 扫描账外实物(盘盈登记) ----------------
@router.post("/{task_id}/surplus", response_model=schemas.InventoryTaskOut)
def register_surplus(
    task_id: int,
    payload: schemas.InventoryCheckIn,
    db: Session = Depends(get_db),
):
    """盘点时扫到不在账内的实物,先登记为待建档盘盈条目(不动正式总账)。"""
    task = _get_task(db, task_id)
    svc.active_status(task)

    name = payload.condition_note or "账外实物(待建档)"
    actual_name = _location_name(db, payload.actual_location_id or task.location_id)
    item = models.InventoryItem(
        task_id=task.id,
        collection_id=None,
        snapshot_accession_no="账外",
        snapshot_name=name,
        snapshot_location_id=None,
        snapshot_location_name=None,
        snapshot_status="账外",
        result=models.INV_RESULT_SURPLUS,
        actual_location_id=payload.actual_location_id or task.location_id,
        actual_location_name=actual_name,
        condition_note=payload.condition_note,
        checker=payload.checker or task.checker or "盘点员",
        checked_at=datetime.utcnow(),
    )
    db.add(item)
    db.flush()
    svc.add_log(
        db,
        task,
        "盘盈登记",
        f"发现账外实物:{name},实物位置 {actual_name or '未填'},待盘盈审批建档",
        operator=item.checker,
        item_id=item.id,
    )
    svc.refresh_task_status(db, task)
    db.commit()
    db.refresh(task)
    return _serialize_task(db, task, detail=True)


# ---------------- 复核 ----------------
@router.post("/{task_id}/items/{item_id}/review", response_model=schemas.InventoryTaskOut)
def review_item(
    task_id: int,
    item_id: int,
    payload: schemas.InventoryReviewIn,
    db: Session = Depends(get_db),
):
    task = _get_task(db, task_id)
    svc.active_status(task)
    item = db.get(models.InventoryItem, item_id)
    if not item or item.task_id != task_id:
        raise HTTPException(404, "盘点明细不存在")
    if item.result == models.INV_RESULT_PENDING:
        raise HTTPException(400, "该藏品尚未盘点,无法复核")
    if item.result == models.INV_RESULT_MATCH:
        raise HTTPException(400, "账实相符条目无需复核")

    item.review_status = (
        models.INV_REVIEW_CONFIRM if payload.confirm else models.INV_REVIEW_FALSE
    )
    item.review_opinion = payload.opinion
    item.reviewer = payload.reviewer or "复核人"
    item.reviewed_at = datetime.utcnow()
    svc.add_log(
        db,
        task,
        "差异复核",
        f"{item.snapshot_accession_no}:{item.review_status}"
        + (f";{payload.opinion}" if payload.opinion else ""),
        operator=item.reviewer,
        item_id=item.id,
    )

    # 复核无误 -> 差异解除,回归相符
    if not payload.confirm:
        item.result = models.INV_RESULT_MATCH

    _maybe_enter_review_phase(task)
    db.commit()
    db.refresh(task)
    return _serialize_task(db, task, detail=True)


def _maybe_enter_review_phase(task: models.InventoryTask) -> None:
    """所有实物核对完后进入待复核;差异全部复核完进入调整审批/可结案。"""
    if any(i.result == models.INV_RESULT_PENDING for i in task.items):
        return
    diffs = [i for i in task.items if i.result in svc.DIFF_RESULTS]
    if any(i.review_status == models.INV_REVIEW_PENDING for i in diffs):
        task.status = models.INV_REVIEWING
    elif any(a.status == models.ADJUST_PENDING for a in task.adjustments):
        task.status = models.INV_ADJUSTING


# ---------------- 调整申请 ----------------
@router.post("/{task_id}/adjustments", response_model=schemas.InventoryTaskOut)
def apply_adjustment(
    task_id: int,
    payload: schemas.InventoryAdjustmentIn,
    db: Session = Depends(get_db),
):
    task = _get_task(db, task_id)
    svc.active_status(task)

    allowed_types = {
        models.ADJUST_MOVE,
        models.ADJUST_REPAIR,
        models.ADJUST_INFO,
        models.ADJUST_STATUS,
    }
    if payload.adjust_type not in allowed_types:
        raise HTTPException(400, f"调整类型必须是:{'/'.join(sorted(allowed_types))}")

    item = None
    if payload.item_id:
        item = db.get(models.InventoryItem, payload.item_id)
        if not item or item.task_id != task_id:
            raise HTTPException(404, "盘点明细不存在")
        # 关键约束:差异未复核(且未确认属实)前不能发起落账调整
        if item.result in svc.DIFF_RESULTS and item.review_status != models.INV_REVIEW_CONFIRM:
            raise HTTPException(400, "差异尚未复核确认,不能提交调整申请(正式档案受保护)")

    # 类型与差异一致性校验
    p = payload.payload or {}
    if payload.adjust_type == models.ADJUST_MOVE and (
        not item or item.result != models.INV_RESULT_MISPLACED
    ):
        raise HTTPException(400, "移库更正仅适用于已复核确认的错位条目")
    if payload.adjust_type == models.ADJUST_REPAIR and (
        not item or item.result != models.INV_RESULT_DAMAGED
    ):
        raise HTTPException(400, "送修登记仅适用于已复核确认的损坏条目")
    if payload.adjust_type == models.ADJUST_STATUS:
        if p.get("action") == "loss" and (
            not item or item.result != models.INV_RESULT_LOSS
        ):
            raise HTTPException(400, "盘亏销账仅适用于已复核确认的盘亏条目")
        if p.get("action") == "gain":
            if not p.get("accession_no"):
                raise HTTPException(400, "盘盈建档必须提供总登记号")
            if db.query(models.Collection).filter(
                models.Collection.accession_no == p["accession_no"]
            ).first():
                raise HTTPException(400, f"总登记号 {p['accession_no']} 已存在")

    applicant = payload.applicant or (item.checker if item else None)
    adj = models.InventoryAdjustment(
        task_id=task.id,
        item_id=item.id if item else None,
        adjust_type=payload.adjust_type,
        reason=payload.reason,
        payload=p,
        applicant=applicant,
        status=models.ADJUST_PENDING,
    )
    db.add(adj)
    db.flush()
    target = item.snapshot_accession_no if item else "账外实物"
    svc.add_log(
        db,
        task,
        "提交调整申请",
        f"{target}:{payload.adjust_type}(申请 #{adj.id})"
        + (f";{payload.reason}" if payload.reason else ""),
        operator=adj.applicant,
        item_id=item.id if item else None,
    )
    task.status = models.INV_ADJUSTING
    db.commit()
    db.refresh(task)
    return _serialize_task(db, task, detail=True)


@router.post(
    "/{task_id}/adjustments/{adj_id}/decide",
    response_model=schemas.InventoryTaskOut,
)
def decide_adjustment(
    task_id: int,
    adj_id: int,
    payload: schemas.InventoryAdjustmentDecide,
    db: Session = Depends(get_db),
):
    task = _get_task(db, task_id)
    svc.active_status(task)
    adj = db.get(models.InventoryAdjustment, adj_id)
    if not adj or adj.task_id != task_id:
        raise HTTPException(404, "调整申请不存在")
    if adj.status != models.ADJUST_PENDING:
        raise HTTPException(400, "该申请已处理")

    adj.approver = payload.approver or "审批人"
    adj.approved_at = datetime.utcnow()
    adj.approve_opinion = payload.opinion

    if not payload.approve:
        adj.status = models.ADJUST_REJECTED
        svc.add_log(
            db,
            task,
            "驳回调整申请",
            f"申请 #{adj.id} {adj.adjust_type} 已驳回"
            + (f";{payload.opinion}" if payload.opinion else ""),
            operator=adj.approver,
        )
    else:
        result_note = svc._apply_adjustment(db, task, adj)
        adj.status = models.ADJUST_APPROVED
        if adj.item:
            adj.item.actual_location_name = _location_name(
                db, adj.item.actual_location_id
            )
        svc.add_log(
            db,
            task,
            "批准调整并落账",
            f"申请 #{adj.id} {adj.adjust_type}:{result_note}",
            operator=adj.approver,
            item_id=adj.item_id,
        )

    db.flush()
    # 若已无待审批申请,回落到待复核 / 盘点中,等待结案
    if not any(a.status == models.ADJUST_PENDING for a in task.adjustments):
        diffs = [i for i in task.items if i.result in svc.DIFF_RESULTS]
        if any(i.review_status == models.INV_REVIEW_PENDING for i in diffs):
            task.status = models.INV_REVIEWING
        else:
            task.status = models.INV_IN_PROGRESS
    db.commit()
    db.refresh(task)
    return _serialize_task(db, task, detail=True)


# ---------------- 结案 ----------------
@router.post("/{task_id}/complete", response_model=schemas.InventoryTaskOut)
def complete_task(
    task_id: int,
    payload: schemas.InventoryCompleteIn,
    db: Session = Depends(get_db),
):
    task = _get_task(db, task_id)
    svc.active_status(task)

    unchecked = [i for i in task.items if i.result == models.INV_RESULT_PENDING]
    if unchecked:
        raise HTTPException(
            400, f"仍有 {len(unchecked)} 件未盘点,不能结案"
        )
    diffs = [i for i in task.items if i.result in svc.DIFF_RESULTS]
    confirmed_diffs = [
        i for i in diffs if i.review_status == models.INV_REVIEW_CONFIRM
    ]
    unreviewed = [i for i in diffs if i.review_status == models.INV_REVIEW_PENDING]
    if unreviewed:
        raise HTTPException(
            400, f"仍有 {len(unreviewed)} 条差异未复核,不能结案"
        )
    pending_adj = [a for a in task.adjustments if a.status == models.ADJUST_PENDING]
    if pending_adj:
        raise HTTPException(
            400, f"仍有 {len(pending_adj)} 条调整申请待审批,不能结案"
        )
    # 每条确认属实的差异都要有处置:已批准落账的调整,或结案说明中注明处置结论
    handled_item_ids = {
        a.item_id
        for a in task.adjustments
        if a.status == models.ADJUST_APPROVED and a.item_id is not None
    }
    no_disposition = [
        i
        for i in confirmed_diffs
        if i.id not in handled_item_ids and not (payload.summary or "").strip()
    ]
    if no_disposition:
        labels = "、".join(
            f"{i.snapshot_accession_no}({i.result})" for i in no_disposition[:5]
        )
        raise HTTPException(
            400,
            f"有 {len(no_disposition)} 条确认差异尚无已批准调整(如 {labels}),"
            "请先提交并审批调整申请,或在结案说明中注明处置结论",
        )

    # 结案汇总:相符 / 各类差异及处理结果
    summary_parts = []
    for label, res in (
        ("盘盈", models.INV_RESULT_SURPLUS),
        ("盘亏", models.INV_RESULT_LOSS),
        ("错位", models.INV_RESULT_MISPLACED),
        ("损坏", models.INV_RESULT_DAMAGED),
    ):
        n = sum(1 for i in confirmed_diffs if i.result == res)
        if n:
            summary_parts.append(f"{label}{n}")
    adj_ok = sum(1 for a in task.adjustments if a.status == models.ADJUST_APPROVED)
    summary = (
        f"共盘 {len(task.items)} 件,"
        + ("、".join(summary_parts) if summary_parts else "账实全部相符")
        + f";批准调整 {adj_ok} 项"
    )

    task.status = models.INV_COMPLETED
    task.finished_at = datetime.utcnow()
    svc.add_log(
        db,
        task,
        "结案",
        summary + (f";{payload.summary}" if payload.summary else ""),
        operator=payload.operator or task.librarian,
    )
    db.commit()
    db.refresh(task)
    return _serialize_task(db, task, detail=True)
