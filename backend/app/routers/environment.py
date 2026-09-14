from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..services.env_service import evaluate_reading, simulate_reading

router = APIRouter(tags=["环境监测"])


def _alert_out(db: Session, a: models.EnvAlert) -> schemas.AlertOut:
    out = schemas.AlertOut.model_validate(a)
    loc = db.get(models.Location, a.location_id)
    if loc:
        out.location_name = loc.name
        out.location_code = loc.code
    return out


@router.get("/api/environment/readings", response_model=list[schemas.ReadingOut])
def list_readings(
    location_id: int,
    hours: int = Query(72, le=24 * 30),
    db: Session = Depends(get_db),
):
    if not db.get(models.Location, location_id):
        raise HTTPException(404, "存放位置不存在")
    since = datetime.utcnow().timestamp() - hours * 3600
    rows = (
        db.query(models.EnvReading)
        .filter(models.EnvReading.location_id == location_id)
        .order_by(models.EnvReading.recorded_at.desc())
        .limit(500)
        .all()
    )
    return rows


@router.post("/api/locations/{location_id}/readings", response_model=schemas.ReadingOut)
def add_reading(
    location_id: int, payload: schemas.ReadingCreate, db: Session = Depends(get_db)
):
    loc = db.get(models.Location, location_id)
    if not loc:
        raise HTTPException(404, "存放位置不存在")
    reading = models.EnvReading(
        location_id=location_id,
        temperature=payload.temperature,
        humidity=payload.humidity,
        recorded_at=payload.recorded_at or datetime.utcnow(),
        source=payload.source,
    )
    db.add(reading)
    db.flush()
    evaluate_reading(db, reading, loc)
    db.commit()
    db.refresh(reading)
    return reading


@router.post("/api/environment/simulate")
def simulate(payload: schemas.SimRequest, db: Session = Depends(get_db)):
    """为所有位置生成一次模拟采集;inject_anomaly=true 时在指定/随机位置制造一次异常。"""
    locations = db.query(models.Location).all()
    if payload.anomaly_location_id:
        target = db.get(models.Location, payload.anomaly_location_id)
        if not target:
            raise HTTPException(404, "存放位置不存在")
    else:
        target = None

    created_alerts: list[schemas.AlertOut] = []
    readings = []
    for loc in locations:
        force = payload.inject_anomaly and (target is loc or (target is None and loc is locations[0]))
        r = simulate_reading(db, loc, force_anomaly=force)
        readings.append({"location_id": loc.id, "temperature": r.temperature, "humidity": r.humidity})

    if payload.inject_anomaly:
        loc = target or locations[0]
        alerts = (
            db.query(models.EnvAlert)
            .filter(models.EnvAlert.location_id == loc.id, models.EnvAlert.acknowledged.is_(False))
            .order_by(models.EnvAlert.created_at.desc())
            .limit(2)
            .all()
        )
        created_alerts = [_alert_out(db, a) for a in alerts]

    return {"readings": readings, "alerts": created_alerts}


@router.get("/api/environment/alerts", response_model=list[schemas.AlertOut])
def list_alerts(
    acknowledged: bool | None = False,
    level: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.EnvAlert).options(joinedload(models.EnvAlert.location))
    if acknowledged is not None:
        q = q.filter(models.EnvAlert.acknowledged.is_(acknowledged))
    if level:
        q = q.filter(models.EnvAlert.level == level)
    rows = q.order_by(models.EnvAlert.created_at.desc()).limit(200).all()
    return [_alert_out(db, a) for a in rows]


@router.post("/api/environment/alerts/{alert_id}/ack", response_model=schemas.AlertOut)
def acknowledge_alert(
    alert_id: int, db: Session = Depends(get_db), by: str = "管理员"
):
    a = db.get(models.EnvAlert, alert_id)
    if not a:
        raise HTTPException(404, "告警不存在")
    if not a.acknowledged:
        a.acknowledged = True
        a.acknowledged_at = datetime.utcnow()
        a.acknowledged_by = by
        db.commit()
        db.refresh(a)
    return _alert_out(db, a)
