"""馆藏盘点领域服务:范围解析、占用互斥、差异判定、调整落账。

规则要点:
- 盘点期间同一藏品不能被两个进行中的盘点任务重复占用(建账即占用,结案/撤销释放);
- 差异(盘盈/盘亏/错位/损坏)未复核前不允许直接改写正式档案;
- 调整申请批准后才落账(库位/档案/修复/盘盈建档/盘亏销账),并补登出入库台账。
"""

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models

DIFF_RESULTS = {
    models.INV_RESULT_SURPLUS,
    models.INV_RESULT_LOSS,
    models.INV_RESULT_MISPLACED,
    models.INV_RESULT_DAMAGED,
}


# ---------------- 范围解析 ----------------
def resolve_scope(
    db: Session, scope_type: str, scope_value: str, location_id: int | None
):
    """返回 (query, location_id):按库房/类别/等级圈定在账藏品。"""
    q = db.query(models.Collection)
    loc_id = None
    if scope_type == models.INV_SCOPE_LOCATION:
        if not location_id:
            loc = (
                db.query(models.Location)
                .filter(models.Location.name == scope_value)
                .first()
            )
            if not loc:
                raise HTTPException(404, f"库房「{scope_value}」不存在")
            loc_id = loc.id
        else:
            loc = db.get(models.Location, location_id)
            if not loc:
                raise HTTPException(404, "指定库房不存在")
            loc_id = loc.id
        q = q.filter(models.Collection.location_id == loc_id)
    elif scope_type == models.INV_SCOPE_CATEGORY:
        q = q.filter(models.Collection.category == scope_value)
    elif scope_type == models.INV_SCOPE_GRADE:
        q = q.filter(models.Collection.grade == scope_value)
    else:
        raise HTTPException(400, "盘点范围类型必须是 库房/类别/等级")
    return q, loc_id


def find_active_conflicts(db: Session, collection_ids: list[int]) -> list[dict]:
    """找出这些藏品当前被哪些进行中的盘点任务占用。"""
    if not collection_ids:
        return []
    rows = (
        db.query(
            models.InventoryItem.collection_id,
            models.InventoryTask.id,
            models.InventoryTask.title,
            models.InventoryTask.status,
        )
        .join(models.InventoryTask, models.InventoryItem.task_id == models.InventoryTask.id)
        .filter(
            models.InventoryItem.collection_id.in_(collection_ids),
            models.InventoryTask.status.in_(models.INV_ACTIVE_STATUSES),
        )
        .all()
    )
    conflicts = {}
    for cid, tid, title, status in rows:
        conflicts.setdefault(
            cid, {"task_id": tid, "task_title": title, "task_status": status}
        )
    return [{"collection_id": cid, **v} for cid, v in conflicts.items()]


def ensure_no_conflict(db: Session, collection_ids: list[int]) -> None:
    conflicts = find_active_conflicts(db, collection_ids)
    if conflicts:
        sample = conflicts[0]
        raise HTTPException(
            409,
            f"有 {len(conflicts)} 件藏品已被进行中的盘点任务占用"
            f"(如任务 #{sample['task_id']}「{sample['task_title']}」),"
            "同一藏品不能在盘点期间被多个任务重复占用",
        )


def is_collection_busy(db: Session, collection_id: int) -> models.InventoryTask | None:
    """返回占用该藏品的进行中盘点任务(没有则 None)。"""
    return (
        db.query(models.InventoryTask)
        .join(models.InventoryItem, models.InventoryItem.task_id == models.InventoryTask.id)
        .filter(
            models.InventoryItem.collection_id == collection_id,
            models.InventoryTask.status.in_(models.INV_ACTIVE_STATUSES),
        )
        .first()
    )


# ---------------- 任务流转 ----------------
def active_status(task: models.InventoryTask) -> None:
    if task.status not in models.INV_ACTIVE_STATUSES:
        raise HTTPException(400, f"任务已{task.status},不能再操作")


def add_log(
    db: Session,
    task: models.InventoryTask,
    action: str,
    detail: str | None = None,
    operator: str | None = None,
    item_id: int | None = None,
) -> None:
    db.add(
        models.InventoryLog(
            task_id=task.id,
            item_id=item_id,
            action=action,
            detail=detail,
            operator=operator,
        )
    )


def refresh_task_status(db: Session, task: models.InventoryTask) -> None:
    """根据明细盘点进度推进 待盘点 -> 盘点中;不自动结案。"""
    if task.status not in (models.INV_PENDING, models.INV_IN_PROGRESS):
        return
    checked = sum(1 for i in task.items if i.result != models.INV_RESULT_PENDING)
    if checked > 0:
        task.status = models.INV_IN_PROGRESS


def compute_stats(task: models.InventoryTask, today: date | None = None) -> dict:
    today = today or date.today()
    items = task.items
    total = len(items)
    pending = sum(1 for i in items if i.result == models.INV_RESULT_PENDING)
    checked = total - pending
    diff = sum(1 for i in items if i.result in DIFF_RESULTS)
    reviewed = sum(
        1 for i in items if i.result in DIFF_RESULTS and i.review_status != models.INV_REVIEW_PENDING
    )
    pending_adjust = sum(1 for a in task.adjustments if a.status == models.ADJUST_PENDING)
    days = None
    overdue = False
    if task.status in models.INV_ACTIVE_STATUSES:
        days = (task.due_date - today).days
        overdue = today > task.due_date
    return {
        "total_count": total,
        "checked_count": checked,
        "pending_count": pending,
        "diff_count": diff,
        "reviewed_count": reviewed,
        "pending_adjustments": pending_adjust,
        "overdue": overdue,
        "days_remaining": days,
    }


# ---------------- 调整落账(批准后才允许改正式档案) ----------------
def _apply_adjustment(db: Session, task: models.InventoryTask, adj: models.InventoryAdjustment):
    """批准调整 -> 改写正式档案 / 状态,并补登出入库台账。返回处理说明。"""
    p = adj.payload or {}
    note = f"盘点任务「{task.title}」(#{task.id})调整申请 #{adj.id}"
    now = datetime.utcnow()

    if adj.adjust_type == models.ADJUST_MOVE:
        item = adj.item
        c = db.get(models.Collection, item.collection_id)
        new_id = p.get("to_location_id")
        new_loc = db.get(models.Location, new_id) if new_id else None
        if not new_loc:
            raise HTTPException(400, "移库更正需要有效的目标库位")
        db.add(
            models.Movement(
                collection_id=c.id,
                move_type=models.MOVE_TRANSFER,
                from_location_id=c.location_id,
                to_location_id=new_id,
                purpose=f"盘点错位更正:{task.title}",
                operator=adj.approver,
                handler=item.checker,
                move_date=now,
                remark=adj.reason,
            )
        )
        c.location_id = new_id
        c.status = models.STATUS_IN_STORAGE
        return f"已移库至 {new_loc.code} {new_loc.name}"

    if adj.adjust_type == models.ADJUST_INFO:
        item = adj.item
        c = db.get(models.Collection, item.collection_id)
        fields = p.get("fields", {})
        allowed = {
            "name", "category", "dynasty", "material", "dimension",
            "weight", "grade", "source", "description",
        }
        changed = []
        for k, v in fields.items():
            if k in allowed and v is not None:
                setattr(c, k, v)
                changed.append(k)
        return f"已更正档案字段:{'、'.join(changed) if changed else '无'}"

    if adj.adjust_type == models.ADJUST_REPAIR:
        item = adj.item
        c = db.get(models.Collection, item.collection_id)
        if c.status != models.STATUS_IN_STORAGE:
            raise HTTPException(
                400, f"藏品当前为「{c.status}」,无法登记送修,请先归库"
            )
        r = models.Restoration(
            collection_id=c.id,
            project_name=p.get("project_name") or f"盘点损坏送修:{c.name}",
            reason=item.condition_note or adj.reason,
            plan=p.get("plan"),
            restorer=p.get("restorer"),
            start_date=date.today(),
            timeline=[
                {
                    "date": str(date.today()),
                    "stage": "立项",
                    "note": f"由盘点任务「{task.title}」发现损坏并立项送修",
                }
            ],
        )
        db.add(r)
        db.add(
            models.Movement(
                collection_id=c.id,
                move_type=models.MOVE_REPAIR_OUT,
                from_location_id=c.location_id,
                purpose=f"盘点损坏送修:{r.project_name}",
                operator=p.get("restorer"),
                move_date=now,
            )
        )
        c.status = models.STATUS_RESTORATION
        c.location_id = None
        return "已登记修复立项,藏品转为修复中"

    if adj.adjust_type == models.ADJUST_STATUS:
        action = p.get("action")
        if action == "gain":
            # 盘盈:为账外实物建立藏品档案
            loc_id = p.get("location_id")
            if loc_id and not db.get(models.Location, loc_id):
                raise HTTPException(400, "入库库位不存在")
            c = models.Collection(
                accession_no=p.get("accession_no"),
                name=p.get("name", "盘盈待建档实物"),
                category=p.get("category") or "待分类",
                dynasty=p.get("dynasty"),
                material=p.get("material"),
                dimension=p.get("dimension"),
                grade=p.get("grade"),
                source=p.get("source") or "盘点盘盈",
                acquired_date=date.today(),
                location_id=loc_id,
                description=p.get("description") or adj.reason,
                status=models.STATUS_IN_STORAGE if loc_id else models.STATUS_OUT_STORAGE,
            )
            db.add(c)
            db.flush()
            adj.collection_id = c.id
            if adj.item:
                adj.item.collection_id = c.id
                adj.item.snapshot_accession_no = c.accession_no
                adj.item.snapshot_name = c.name
            db.add(
                models.Movement(
                    collection_id=c.id,
                    move_type=models.MOVE_INVENTORY_GAIN,
                    to_location_id=loc_id,
                    purpose=f"盘点盘盈建档:{task.title}",
                    operator=adj.approver,
                    move_date=now,
                    remark=adj.reason,
                )
            )
            return f"盘盈实物已建档({c.accession_no})并入账"

        if action == "loss":
            item = adj.item
            c = db.get(models.Collection, item.collection_id)
            db.add(
                models.Movement(
                    collection_id=c.id,
                    move_type=models.MOVE_INVENTORY_LOSS,
                    from_location_id=c.location_id,
                    purpose=f"盘点盘亏销账:{task.title}",
                    operator=adj.approver,
                    handler=item.checker,
                    move_date=now,
                    remark=adj.reason,
                )
            )
            c.location_id = None
            c.status = models.STATUS_OUT_STORAGE  # 标记为账销案存,禁止常规流转
            return "已作盘亏销账处理,藏品标记为出库中(账销案存)"
        raise HTTPException(400, "状态处理需指定 action: gain / loss")

    raise HTTPException(400, f"未知调整类型:{adj.adjust_type}")
