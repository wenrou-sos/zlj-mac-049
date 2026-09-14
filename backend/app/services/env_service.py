import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models
from ..models import ALERT_CRITICAL, ALERT_WARNING

METRIC_LABELS = {"temperature": "温度", "humidity": "相对湿度"}


def _level_for(metric: str, value: float, low: float, high: float) -> tuple[str, float]:
    """返回 (告警级别, 被突破的阈值)。严重:温度越界≥3℃ / 湿度越界≥10%。"""
    if value < low:
        delta = low - value
        critical = delta >= (3.0 if metric == "temperature" else 10.0)
        return (ALERT_CRITICAL if critical else ALERT_WARNING), low
    if value > high:
        delta = value - high
        critical = delta >= (3.0 if metric == "temperature" else 10.0)
        return (ALERT_CRITICAL if critical else ALERT_WARNING), high
    return "正常", 0.0


def evaluate_reading(db: Session, reading: models.EnvReading, location: models.Location) -> list[models.EnvAlert]:
    """根据存放位置阈值评估一次采集,生成(必要的)告警并入库。"""
    created: list[models.EnvAlert] = []
    checks = [
        ("temperature", reading.temperature, location.temp_min, location.temp_max, "℃"),
        ("humidity", reading.humidity, location.hum_min, location.hum_max, "%"),
    ]
    for metric, value, low, high, unit in checks:
        level, threshold = _level_for(metric, value, low, high)
        if level == "正常":
            continue
        direction = "低于下限" if value < low else "高于上限"
        message = (
            f"{location.name} {METRIC_LABELS[metric]}异常:{value:.1f}{unit},"
            f"{direction} {threshold:g}{unit}(允许区间 {low:g}~{high:g}{unit})"
        )
        alert = models.EnvAlert(
            location_id=location.id,
            reading_id=reading.id,
            level=level,
            metric=metric,
            value=value,
            threshold=threshold,
            message=message,
        )
        db.add(alert)
        created.append(alert)
    db.flush()
    return created


def simulate_reading(db: Session, location: models.Location, force_anomaly: bool = False) -> models.EnvReading:
    """在阈值区间内生成一次模拟采集;force_anomaly 时制造一次越界(用于演示提醒)。"""
    temp = round(random.uniform(location.temp_min + 0.5, location.temp_max - 0.5), 1)
    hum = round(random.uniform(location.hum_min + 1, location.hum_max - 1), 1)
    source = "模拟"

    if force_anomaly:
        # 随机挑选温/湿度制造越界,约一半概率达到"严重"
        metric = random.choice(["temperature", "humidity"])
        severe = random.random() < 0.5
        if metric == "temperature":
            pad = 3.5 if severe else 1.5
            temp = round(location.temp_max + pad, 1)
        else:
            pad = 12.0 if severe else 5.0
            hum = round(location.hum_max + pad, 1)

    reading = models.EnvReading(
        location_id=location.id, temperature=temp, humidity=hum, source=source
    )
    db.add(reading)
    db.flush()
    evaluate_reading(db, reading, location)
    db.commit()
    db.refresh(reading)
    return reading


def backfill_history(db: Session, location: models.Location, hours: int = 72, points: int = 48):
    """为一个位置补一段历史曲线(正常区间内小幅波动)。"""
    now = datetime.utcnow()
    existing = (
        db.query(models.EnvReading)
        .filter(models.EnvReading.location_id == location.id, models.EnvReading.source == "模拟")
        .count()
    )
    if existing:
        return
    t_mid = (location.temp_min + location.temp_max) / 2
    h_mid = (location.hum_min + location.hum_max) / 2
    for i in range(points, 0, -1):
        ts = now - timedelta(hours=hours * i / points)
        temp = round(t_mid + random.uniform(-1.8, 1.8), 1)
        hum = round(h_mid + random.uniform(-4, 4), 1)
        db.add(
            models.EnvReading(
                location_id=location.id,
                temperature=temp,
                humidity=hum,
                recorded_at=ts,
                source="模拟",
            )
        )
    db.commit()
