from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/loans", tags=["借展管理"])


def _status_and_days(loan: models.LoanRecord, today: date | None = None) -> tuple[str, int | None]:
    today = today or date.today()
    if loan.return_date:
        return "已归还", None
    if today > loan.due_date:
        return "已逾期", (today - loan.due_date).days
    return "借出", (loan.due_date - today).days


def _serialize(loan: models.LoanRecord) -> schemas.LoanOut:
    out = schemas.LoanOut.model_validate(loan)
    if loan.collection:
        out.collection_name = loan.collection.name
        out.accession_no = loan.collection.accession_no
    status, days = _status_and_days(loan)
    out.status = status
    out.days_remaining = days
    return out


@router.get("", response_model=list[schemas.LoanOut])
def list_loans(
    status: str | None = None,
    db: Session = Depends(get_db),
    overdue_only: bool = False,
    due_within_days: int | None = None,
):
    rows = (
        db.query(models.LoanRecord)
        .options(joinedload(models.LoanRecord.collection))
        .order_by(models.LoanRecord.due_date.asc())
        .all()
    )
    today = date.today()
    result = []
    for loan in rows:
        eff_status, days = _status_and_days(loan, today)
        if status and eff_status != status:
            continue
        if overdue_only and eff_status != "已逾期":
            continue
        if due_within_days is not None and eff_status == "借出" and days > due_within_days:
            continue
        out = _serialize(loan)
        result.append(out)
    return result


@router.post("", response_model=schemas.LoanOut)
def create_loan(payload: schemas.LoanCreate, db: Session = Depends(get_db)):
    c = db.get(models.Collection, payload.collection_id)
    if not c:
        raise HTTPException(404, "藏品不存在")
    if c.status != models.STATUS_IN_STORAGE:
        hint = {
            models.STATUS_EXHIBITION: "请先在展陈管理中办理撤展归库",
            models.STATUS_RESTORATION: "请先完成修复并结项归库",
            models.STATUS_LOAN_OUT: "该藏品已借展在外",
            models.STATUS_OUT_STORAGE: "请先办理入库归库",
        }.get(c.status, "")
        raise HTTPException(
            400, f"藏品当前为「{c.status}」状态,不能登记借展。{hint}"
        )
    if payload.due_date <= (payload.loan_date or date.today()):
        raise HTTPException(400, "应还日期必须晚于借出日期")

    loan = models.LoanRecord(
        collection_id=payload.collection_id,
        borrowing_institution=payload.borrowing_institution,
        exhibition_title=payload.exhibition_title,
        contact_person=payload.contact_person,
        contact_phone=payload.contact_phone,
        loan_date=payload.loan_date or date.today(),
        due_date=payload.due_date,
        purpose=payload.purpose,
        remark=payload.remark,
        status="借出",
    )
    db.add(loan)
    db.add(
        models.Movement(
            collection_id=c.id,
            move_type=models.MOVE_LOAN_OUT,
            from_location_id=c.location_id,
            purpose=f"借展:{payload.borrowing_institution}"
            + (f" / {payload.exhibition_title}" if payload.exhibition_title else ""),
            handler=payload.contact_person,
            move_date=datetime.utcnow(),
            remark=f"应还 {payload.due_date}",
        )
    )
    c.status = models.STATUS_LOAN_OUT
    c.location_id = None
    db.commit()
    db.refresh(loan)
    return _serialize(loan)


@router.post("/{loan_id}/return", response_model=schemas.LoanOut)
def return_loan(
    loan_id: int, payload: schemas.LoanReturn, db: Session = Depends(get_db)
):
    loan = db.get(models.LoanRecord, loan_id)
    if not loan:
        raise HTTPException(404, "借展记录不存在")
    if loan.return_date:
        raise HTTPException(400, "该藏品已归还")
    c = db.get(models.Collection, loan.collection_id)
    return_date = payload.return_date or date.today()
    loan.return_date = return_date
    loan.status = "已归还"

    loc_id = payload.to_location_id
    db.add(
        models.Movement(
            collection_id=c.id,
            move_type=models.MOVE_LOAN_BACK,
            to_location_id=loc_id,
            purpose=f"借展归还:{loan.borrowing_institution}",
            move_date=datetime.utcnow(),
        )
    )
    if loc_id and db.get(models.Location, loc_id):
        c.location_id = loc_id
        c.status = models.STATUS_IN_STORAGE
    else:
        c.status = models.STATUS_OUT_STORAGE
    db.commit()
    db.refresh(loan)
    return _serialize(loan)
