from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/restorations", tags=["修复管理"])


def _serialize(r: models.Restoration) -> schemas.RestorationOut:
    out = schemas.RestorationOut.model_validate(r)
    if r.collection:
        out.collection_name = r.collection.name
        out.accession_no = r.collection.accession_no
    return out


@router.get("", response_model=list[schemas.RestorationOut])
def list_restorations(
    status: str | None = None,
    collection_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Restoration).options(joinedload(models.Restoration.collection))
    if status:
        q = q.filter(models.Restoration.status == status)
    if collection_id:
        q = q.filter(models.Restoration.collection_id == collection_id)
    rows = q.order_by(models.Restoration.start_date.desc()).all()
    return [_serialize(r) for r in rows]


@router.post("", response_model=schemas.RestorationOut)
def create_restoration(payload: schemas.RestorationCreate, db: Session = Depends(get_db)):
    c = db.get(models.Collection, payload.collection_id)
    if not c:
        raise HTTPException(404, "藏品不存在")
    if c.status == models.STATUS_RESTORATION:
        raise HTTPException(400, "该藏品已在修复中")
    if c.status == models.STATUS_LOAN_OUT:
        raise HTTPException(400, "藏品借展在外,无法送修")

    r = models.Restoration(
        collection_id=payload.collection_id,
        project_name=payload.project_name,
        reason=payload.reason,
        plan=payload.plan,
        restorer=payload.restorer,
        start_date=payload.start_date or date.today(),
        timeline=[
            {
                "date": str(payload.start_date or date.today()),
                "stage": "立项",
                "note": "建立修复项目,藏品送修复室",
            }
        ],
    )
    db.add(r)
    db.add(
        models.Movement(
            collection_id=c.id,
            move_type=models.MOVE_REPAIR_OUT,
            from_location_id=c.location_id,
            purpose=f"修复:{payload.project_name}",
            operator=payload.restorer,
            move_date=datetime.utcnow(),
        )
    )
    c.status = models.STATUS_RESTORATION
    c.location_id = None
    db.commit()
    db.refresh(r)
    return _serialize(r)


@router.post("/{restoration_id}/timeline", response_model=schemas.RestorationOut)
def add_timeline(
    restoration_id: int, entry: schemas.TimelineEntry, db: Session = Depends(get_db)
):
    r = db.get(models.Restoration, restoration_id)
    if not r:
        raise HTTPException(404, "修复项目不存在")
    if r.status == "已完成":
        raise HTTPException(400, "项目已完成,不可追加记录")
    timeline = list(r.timeline or [])
    timeline.append(
        {"date": str(entry.date), "stage": entry.stage, "note": entry.note}
    )
    r.timeline = timeline
    db.commit()
    db.refresh(r)
    return _serialize(r)


@router.post("/{restoration_id}/complete", response_model=schemas.RestorationOut)
def complete_restoration(
    restoration_id: int,
    payload: schemas.RestorationComplete,
    db: Session = Depends(get_db),
    return_location_id: int | None = None,
):
    r = db.get(models.Restoration, restoration_id)
    if not r:
        raise HTTPException(404, "修复项目不存在")
    if r.status == "已完成":
        raise HTTPException(400, "项目已完成")
    end = payload.end_date or date.today()
    r.status = "已完成"
    r.end_date = end
    r.result = payload.result
    timeline = list(r.timeline or [])
    timeline.append({"date": str(end), "stage": "结项", "note": payload.result or "修复完成"})
    r.timeline = timeline

    c = db.get(models.Collection, r.collection_id)
    loc_id = return_location_id or c.location_id
    db.add(
        models.Movement(
            collection_id=c.id,
            move_type=models.MOVE_REPAIR_BACK,
            to_location_id=loc_id,
            purpose=f"修复完成归库:{r.project_name}",
            operator=r.restorer,
            move_date=datetime.utcnow(),
            remark=payload.result,
        )
    )
    if loc_id and db.get(models.Location, loc_id):
        c.location_id = loc_id
        c.status = models.STATUS_IN_STORAGE
    else:
        c.status = models.STATUS_OUT_STORAGE
    db.commit()
    db.refresh(r)
    return _serialize(r)
