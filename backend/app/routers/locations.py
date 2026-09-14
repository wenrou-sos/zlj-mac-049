from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/locations", tags=["存放位置"])


@router.get("", response_model=list[schemas.LocationOut])
def list_locations(
    db: Session = Depends(get_db),
    location_type: str | None = None,
):
    q = db.query(models.Location)
    if location_type:
        q = q.filter(models.Location.location_type == location_type)
    locations = q.order_by(models.Location.code).all()

    counts = dict(
        db.query(models.Collection.location_id, func.count(models.Collection.id))
        .group_by(models.Collection.location_id)
        .all()
    )
    active_alerts = dict(
        db.query(models.EnvAlert.location_id, func.count(models.EnvAlert.id))
        .filter(models.EnvAlert.acknowledged.is_(False))
        .group_by(models.EnvAlert.location_id)
        .all()
    )
    latest: dict[int, models.EnvReading] = {}
    for loc in locations:
        reading = (
            db.query(models.EnvReading)
            .filter(models.EnvReading.location_id == loc.id)
            .order_by(models.EnvReading.recorded_at.desc())
            .first()
        )
        if reading:
            latest[loc.id] = reading

    result = []
    for loc in locations:
        out = schemas.LocationOut.model_validate(loc)
        out.collection_count = counts.get(loc.id, 0)
        out.active_alert_count = active_alerts.get(loc.id, 0)
        r = latest.get(loc.id)
        if r:
            out.latest_temp = r.temperature
            out.latest_hum = r.humidity
            out.latest_reading_at = r.recorded_at
        result.append(out)
    return result


@router.post("", response_model=schemas.LocationOut)
def create_location(payload: schemas.LocationCreate, db: Session = Depends(get_db)):
    if db.query(models.Location).filter(models.Location.code == payload.code).first():
        raise HTTPException(400, f"位置编号 {payload.code} 已存在")
    loc = models.Location(**payload.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return schemas.LocationOut.model_validate(loc)


@router.get("/{location_id}", response_model=schemas.LocationOut)
def get_location(location_id: int, db: Session = Depends(get_db)):
    loc = db.get(models.Location, location_id)
    if not loc:
        raise HTTPException(404, "存放位置不存在")
    return schemas.LocationOut.model_validate(loc)


@router.put("/{location_id}", response_model=schemas.LocationOut)
def update_location(
    location_id: int, payload: schemas.LocationCreate, db: Session = Depends(get_db)
):
    loc = db.get(models.Location, location_id)
    if not loc:
        raise HTTPException(404, "存放位置不存在")
    dup = (
        db.query(models.Location)
        .filter(models.Location.code == payload.code, models.Location.id != location_id)
        .first()
    )
    if dup:
        raise HTTPException(400, f"位置编号 {payload.code} 已存在")
    for k, v in payload.model_dump().items():
        setattr(loc, k, v)
    db.commit()
    db.refresh(loc)
    return schemas.LocationOut.model_validate(loc)


@router.delete("/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db)):
    loc = db.get(models.Location, location_id)
    if not loc:
        raise HTTPException(404, "存放位置不存在")
    in_use = db.query(models.Collection).filter(models.Collection.location_id == location_id).count()
    if in_use:
        raise HTTPException(400, f"该位置仍存放 {in_use} 件藏品,无法删除")
    db.delete(loc)
    db.commit()
    return {"ok": True}
