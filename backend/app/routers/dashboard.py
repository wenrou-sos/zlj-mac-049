from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/dashboard", tags=["总览"])


@router.get("", response_model=schemas.DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    today = date.today()

    total = db.query(func.count(models.Collection.id)).scalar() or 0

    status_rows = db.query(models.Collection.status, func.count(models.Collection.id)).group_by(
        models.Collection.status
    ).all()
    by_status = {s: 0 for s in ["在库", "出库中", "展陈中", "修复中", "借展中"]}
    for s, n in status_rows:
        by_status[s] = n

    category_rows = (
        db.query(models.Collection.category, func.count(models.Collection.id))
        .group_by(models.Collection.category)
        .order_by(func.count(models.Collection.id).desc())
        .all()
    )
    by_category = [{"name": k, "value": v} for k, v in category_rows]

    grade_rows = (
        db.query(models.Collection.grade, func.count(models.Collection.id))
        .filter(models.Collection.grade.isnot(None))
        .group_by(models.Collection.grade)
        .all()
    )
    grade_order = {"一级文物": 0, "二级文物": 1, "三级文物": 2, "一般文物": 3}
    grade_stats = [
        {"name": g, "value": n}
        for g, n in sorted(grade_rows, key=lambda r: grade_order.get(r[0], 9))
    ]

    active_alerts = (
        db.query(func.count(models.EnvAlert.id))
        .filter(models.EnvAlert.acknowledged.is_(False))
        .scalar()
    )
    critical_alerts = (
        db.query(func.count(models.EnvAlert.id))
        .filter(
            models.EnvAlert.acknowledged.is_(False),
            models.EnvAlert.level == models.ALERT_CRITICAL,
        )
        .scalar()
    )

    loans = db.query(models.LoanRecord).filter(models.LoanRecord.return_date.is_(None)).all()
    loans_overdue = sum(1 for l in loans if today > l.due_date)
    loans_due_soon = sum(
        1 for l in loans if today <= l.due_date <= today + timedelta(days=30)
    )

    exhibitions = db.query(models.Exhibition).all()
    exhibitions_active = sum(
        1 for e in exhibitions if e.start_date <= today <= e.end_date
    )
    restorations_active = (
        db.query(func.count(models.Restoration.id))
        .filter(models.Restoration.status == "进行中")
        .scalar()
    )

    env_status = []
    for loc in db.query(models.Location).order_by(models.Location.code).all():
        reading = (
            db.query(models.EnvReading)
            .filter(models.EnvReading.location_id == loc.id)
            .order_by(models.EnvReading.recorded_at.desc())
            .first()
        )
        alerts = (
            db.query(func.count(models.EnvAlert.id))
            .filter(
                models.EnvAlert.location_id == loc.id,
                models.EnvAlert.acknowledged.is_(False),
            )
            .scalar()
        )
        temp_status = hum_status = "正常"
        if reading:
            if reading.temperature < loc.temp_min or reading.temperature > loc.temp_max:
                temp_status = "异常"
            if reading.humidity < loc.hum_min or reading.humidity > loc.hum_max:
                hum_status = "异常"
        env_status.append(
            {
                "location_id": loc.id,
                "location_name": loc.name,
                "location_code": loc.code,
                "temperature": reading.temperature if reading else None,
                "humidity": reading.humidity if reading else None,
                "recorded_at": reading.recorded_at if reading else None,
                "temp_status": temp_status,
                "hum_status": hum_status,
                "active_alerts": alerts,
            }
        )

    return schemas.DashboardOut(
        total_collections=total,
        by_status=by_status,
        by_category=by_category,
        grade_stats=grade_stats,
        active_alerts=active_alerts,
        critical_alerts=critical_alerts,
        loans_active=len(loans),
        loans_overdue=loans_overdue,
        loans_due_soon=loans_due_soon,
        exhibitions_active=exhibitions_active,
        restorations_active=restorations_active or 0,
        env_status=env_status,
    )
