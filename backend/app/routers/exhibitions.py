from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/exhibitions", tags=["展陈管理"])


def _effective_status(ex: models.Exhibition, today: date | None = None) -> str:
    today = today or date.today()
    if today < ex.start_date:
        return "筹备中"
    if today > ex.end_date:
        return "已结束"
    return "开展中"


def _serialize(db: Session, ex: models.Exhibition) -> schemas.ExhibitionOut:
    ex.status = _effective_status(ex)
    out = schemas.ExhibitionOut.model_validate(ex)
    for item in out.items:
        coll = db.get(models.Collection, item.collection_id)
        if coll:
            item.collection_name = coll.name
            item.accession_no = coll.accession_no
    return out


@router.get("", response_model=list[schemas.ExhibitionOut])
def list_exhibitions(status: str | None = None, db: Session = Depends(get_db)):
    rows = (
        db.query(models.Exhibition)
        .options(joinedload(models.Exhibition.items))
        .order_by(models.Exhibition.start_date.desc())
        .all()
    )
    result = []
    for ex in rows:
        if status and _effective_status(ex) != status:
            continue
        result.append(_serialize(db, ex))
    return result


@router.post("", response_model=schemas.ExhibitionOut)
def create_exhibition(payload: schemas.ExhibitionCreate, db: Session = Depends(get_db)):
    if payload.end_date <= payload.start_date:
        raise HTTPException(400, "结束日期必须晚于开始日期")
    ex = models.Exhibition(**payload.model_dump())
    db.add(ex)
    db.commit()
    db.refresh(ex)
    return _serialize(db, ex)


@router.get("/{exhibition_id}", response_model=schemas.ExhibitionOut)
def get_exhibition(exhibition_id: int, db: Session = Depends(get_db)):
    ex = (
        db.query(models.Exhibition)
        .options(joinedload(models.Exhibition.items))
        .filter(models.Exhibition.id == exhibition_id)
        .first()
    )
    if not ex:
        raise HTTPException(404, "展览不存在")
    return _serialize(db, ex)


@router.post("/{exhibition_id}/items", response_model=schemas.ExhibitionOut)
def add_exhibition_item(
    exhibition_id: int, payload: schemas.ExhibitionItemAdd, db: Session = Depends(get_db)
):
    ex = db.get(models.Exhibition, exhibition_id)
    if not ex:
        raise HTTPException(404, "展览不存在")
    c = db.get(models.Collection, payload.collection_id)
    if not c:
        raise HTTPException(404, "藏品不存在")
    exists = (
        db.query(models.ExhibitionItem)
        .filter(
            models.ExhibitionItem.exhibition_id == exhibition_id,
            models.ExhibitionItem.collection_id == c.id,
            models.ExhibitionItem.status == "已布展",
        )
        .first()
    )
    if exists:
        raise HTTPException(400, "该藏品已在本展览中展出")
    if c.status != models.STATUS_IN_STORAGE:
        hint = {
            models.STATUS_EXHIBITION: "藏品已在其他展览中,请先撤展",
            models.STATUS_RESTORATION: "藏品正在修复中",
            models.STATUS_LOAN_OUT: "藏品借展在外",
            models.STATUS_OUT_STORAGE: "藏品不在库,请先办理入库归库",
        }.get(c.status, "")
        raise HTTPException(
            400, f"藏品当前为「{c.status}」状态,无法布展。{hint}"
        )

    item = models.ExhibitionItem(
        exhibition_id=exhibition_id,
        collection_id=c.id,
        display_location=payload.display_location,
        mounted_at=datetime.utcnow(),
        status="已布展",
    )
    db.add(item)
    db.add(
        models.Movement(
            collection_id=c.id,
            move_type=models.MOVE_EXHIBIT,
            from_location_id=c.location_id,
            purpose=f"布展:{ex.title}",
            operator="策展部",
            move_date=datetime.utcnow(),
            remark=payload.display_location,
        )
    )
    c.status = models.STATUS_EXHIBITION
    c.location_id = None
    db.commit()
    db.refresh(ex)
    return _serialize(db, ex)


@router.delete("/{exhibition_id}/items/{item_id}", response_model=schemas.ExhibitionOut)
def dismount_item(
    exhibition_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    return_location_id: int | None = None,
):
    item = db.get(models.ExhibitionItem, item_id)
    if not item or item.exhibition_id != exhibition_id:
        raise HTTPException(404, "展陈条目不存在")
    if item.status == "已撤展":
        raise HTTPException(400, "该条目已撤展")
    ex = db.get(models.Exhibition, exhibition_id)
    c = db.get(models.Collection, item.collection_id)

    item.status = "已撤展"
    item.dismounted_at = datetime.utcnow()
    db.add(
        models.Movement(
            collection_id=c.id,
            move_type=models.MOVE_RETURN,
            to_location_id=return_location_id,
            purpose=f"撤展归库:{ex.title}",
            operator="策展部",
            move_date=datetime.utcnow(),
        )
    )
    if return_location_id and db.get(models.Location, return_location_id):
        c.location_id = return_location_id
        c.status = models.STATUS_IN_STORAGE
    else:
        c.status = models.STATUS_OUT_STORAGE
    db.commit()
    db.refresh(ex)
    return _serialize(db, ex)
