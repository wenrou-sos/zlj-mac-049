from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# ---------- Location ----------
class LocationBase(BaseModel):
    code: str
    name: str
    zone: str
    location_type: str = "库房"
    temp_min: float = 15.0
    temp_max: float = 22.0
    hum_min: float = 45.0
    hum_max: float = 60.0
    description: str | None = None


class LocationCreate(LocationBase):
    pass


class LocationOut(LocationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    collection_count: int = 0
    latest_temp: float | None = None
    latest_hum: float | None = None
    latest_reading_at: datetime | None = None
    active_alert_count: int = 0


# ---------- Collection ----------
class CollectionBase(BaseModel):
    accession_no: str
    name: str
    category: str
    dynasty: str | None = None
    material: str | None = None
    dimension: str | None = None
    weight: str | None = None
    grade: str | None = None
    source: str | None = None
    acquired_date: date | None = None
    location_id: int | None = None
    image_url: str | None = None
    description: str | None = None


class CollectionCreate(CollectionBase):
    pass


class CollectionUpdate(BaseModel):
    accession_no: str | None = None
    name: str | None = None
    category: str | None = None
    dynasty: str | None = None
    material: str | None = None
    dimension: str | None = None
    weight: str | None = None
    grade: str | None = None
    source: str | None = None
    acquired_date: date | None = None
    location_id: int | None = None
    image_url: str | None = None
    description: str | None = None


class CollectionList(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    accession_no: str
    name: str
    category: str
    dynasty: str | None
    grade: str | None
    status: str
    location_id: int | None
    image_url: str | None


class LocationBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


class CollectionDetail(CollectionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    created_at: datetime
    location: LocationBrief | None = None


# ---------- Movement ----------
class MovementCreate(BaseModel):
    move_type: str
    to_location_id: int | None = None
    purpose: str | None = None
    operator: str | None = None
    handler: str | None = None
    move_date: datetime | None = None
    remark: str | None = None


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    collection_id: int
    move_type: str
    from_location_id: int | None
    to_location_id: int | None
    from_location: LocationBrief | None
    to_location: LocationBrief | None
    purpose: str | None
    operator: str | None
    handler: str | None
    move_date: datetime
    remark: str | None
    collection_name: str | None = None
    accession_no: str | None = None


# ---------- Exhibition ----------
class ExhibitionBase(BaseModel):
    title: str
    venue: str
    start_date: date
    end_date: date
    curator: str | None = None
    description: str | None = None


class ExhibitionCreate(ExhibitionBase):
    pass


class ExhibitionItemAdd(BaseModel):
    collection_id: int
    display_location: str | None = None


class ExhibitionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    collection_id: int
    display_location: str | None
    mounted_at: datetime | None
    dismounted_at: datetime | None
    status: str
    collection_name: str | None = None
    accession_no: str | None = None


class ExhibitionOut(ExhibitionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    items: list[ExhibitionItemOut] = []


# ---------- Restoration ----------
class RestorationCreate(BaseModel):
    collection_id: int
    project_name: str
    reason: str | None = None
    plan: str | None = None
    restorer: str | None = None
    start_date: date | None = None


class TimelineEntry(BaseModel):
    date: date
    stage: str
    note: str | None = None


class RestorationComplete(BaseModel):
    result: str | None = None
    end_date: date | None = None


class RestorationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    collection_id: int
    project_name: str
    reason: str | None
    plan: str | None
    restorer: str | None
    start_date: date
    end_date: date | None
    status: str
    result: str | None
    timeline: list[Any] = []
    collection_name: str | None = None
    accession_no: str | None = None


# ---------- Loan ----------
class LoanCreate(BaseModel):
    collection_id: int
    borrowing_institution: str
    exhibition_title: str | None = None
    contact_person: str | None = None
    contact_phone: str | None = None
    loan_date: date | None = None
    due_date: date
    purpose: str | None = None
    remark: str | None = None


class LoanReturn(BaseModel):
    return_date: date | None = None
    to_location_id: int | None = None


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    collection_id: int
    borrowing_institution: str
    exhibition_title: str | None
    contact_person: str | None
    contact_phone: str | None
    loan_date: date
    due_date: date
    return_date: date | None
    status: str
    purpose: str | None
    remark: str | None
    collection_name: str | None = None
    accession_no: str | None = None
    days_remaining: int | None = None


# ---------- Environment ----------
class ReadingCreate(BaseModel):
    temperature: float
    humidity: float
    recorded_at: datetime | None = None
    source: str = "人工"


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    temperature: float
    humidity: float
    recorded_at: datetime
    source: str


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    level: str
    metric: str
    value: float
    threshold: float
    message: str
    created_at: datetime
    acknowledged: bool
    acknowledged_at: datetime | None
    acknowledged_by: str | None
    location_name: str | None = None
    location_code: str | None = None


class SimRequest(BaseModel):
    inject_anomaly: bool = False
    anomaly_location_id: int | None = None


class DashboardOut(BaseModel):
    total_collections: int
    by_status: dict[str, int]
    by_category: list[dict[str, Any]]
    grade_stats: list[dict[str, Any]]
    active_alerts: int
    critical_alerts: int
    loans_active: int
    loans_overdue: int
    loans_due_soon: int
    exhibitions_active: int
    restorations_active: int
    inventory_active: int = 0
    inventory_pending_review: int = 0
    env_status: list[dict[str, Any]]


# ---------- 馆藏盘点 ----------
class InventoryTaskCreate(BaseModel):
    title: str
    scope_type: str  # 库房/类别/等级
    scope_location_id: int | None = None
    scope_value: str | None = None
    initiator: str
    deadline: date
    remark: str | None = None


class InventoryScanRequest(BaseModel):
    accession_no: str
    actual_location_id: int | None = None
    damaged: bool = False
    condition_note: str | None = None
    checker: str


class InventoryItemCheck(BaseModel):
    """人工登记盘点结果(无法扫码时逐件核对,或确认盘亏)"""

    result: str  # 正常/错位/损坏/盘亏
    actual_location_id: int | None = None
    condition_note: str | None = None
    checker: str


class InventoryReviewRequest(BaseModel):
    approve: bool
    reviewer: str
    note: str | None = None


class InventoryAdjustmentCreate(BaseModel):
    adjust_type: str  # 变更位置/状态变更/损坏登记
    to_location_id: int | None = None
    to_status: str | None = None
    reason: str | None = None
    applicant: str


class InventoryAdjustmentProcess(BaseModel):
    processor: str
    note: str | None = None


class InventoryTaskClose(BaseModel):
    closed_by: str


class InventoryAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_id: int
    adjust_type: str
    to_location_id: int | None
    to_status: str | None
    reason: str | None
    status: str
    applicant: str
    created_at: datetime
    processed_by: str | None
    processed_at: datetime | None
    process_note: str | None
    to_location_name: str | None = None


class InventoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int
    collection_id: int
    book_location_id: int | None
    book_status: str
    result: str
    actual_location_id: int | None
    condition_note: str | None
    review_status: str
    checked_by: str | None
    checked_at: datetime | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None
    logs: list[Any] = []
    accession_no: str | None = None
    collection_name: str | None = None
    category: str | None = None
    grade: str | None = None
    book_location_name: str | None = None
    actual_location_name: str | None = None
    adjustments: list[InventoryAdjustmentOut] = []


class InventoryTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    title: str
    scope_type: str
    scope_location_id: int | None
    scope_value: str | None
    initiator: str
    deadline: date
    status: str
    remark: str | None
    created_at: datetime
    closed_at: datetime | None
    closed_by: str | None
    summary: dict[str, Any] | None
    scope_label: str | None = None
    total: int = 0
    checked: int = 0
    diff_count: int = 0
    pending_review: int = 0
    pending_adjust: int = 0
    result_counts: dict[str, int] = {}
    days_remaining: int | None = None


class InventoryTaskDetail(InventoryTaskOut):
    items: list[InventoryItemOut] = []
