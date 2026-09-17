from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# 藏品状态
STATUS_IN_STORAGE = "在库"
STATUS_OUT_STORAGE = "出库中"
STATUS_EXHIBITION = "展陈中"
STATUS_RESTORATION = "修复中"
STATUS_LOAN_OUT = "借展中"
STATUS_MISSING = "盘亏"  # 盘点确认遗失,待后续处置

# 出入库 / 流转类型
MOVE_IN = "入库"
MOVE_OUT = "出库"
MOVE_TRANSFER = "移库"
MOVE_EXHIBIT = "布展"
MOVE_RETURN = "撤展归库"
MOVE_REPAIR_OUT = "修复出库"
MOVE_REPAIR_BACK = "修复归库"
MOVE_LOAN_OUT = "借展出库"
MOVE_LOAN_BACK = "借展归还"
MOVE_INVENTORY_ADJUST = "盘点调整"

# 盘点任务状态
INV_TASK_ACTIVE = "进行中"
INV_TASK_CLOSED = "已结案"
INV_TASK_CANCELLED = "已取消"

# 盘点范围类型
INV_SCOPE_LOCATION = "库房"
INV_SCOPE_CATEGORY = "类别"
INV_SCOPE_GRADE = "等级"

# 盘点明细结果
INV_RESULT_PENDING = "未盘"
INV_RESULT_NORMAL = "正常"
INV_RESULT_MISPLACED = "错位"
INV_RESULT_DAMAGED = "损坏"
INV_RESULT_LOSS = "盘亏"
INV_RESULT_SURPLUS = "盘盈"
INV_DIFF_RESULTS = (
    INV_RESULT_MISPLACED,
    INV_RESULT_DAMAGED,
    INV_RESULT_LOSS,
    INV_RESULT_SURPLUS,
)

# 复核状态
INV_REVIEW_NONE = "无需复核"
INV_REVIEW_PENDING = "待复核"
INV_REVIEW_DONE = "已复核"

# 调整申请
INV_ADJUST_LOCATION = "变更位置"
INV_ADJUST_STATUS = "状态变更"
INV_ADJUST_DAMAGE = "损坏登记"
INV_ADJUST_PENDING = "待审批"
INV_ADJUST_EXECUTED = "已执行"
INV_ADJUST_REJECTED = "已驳回"

# 温湿度告警级别
ALERT_NORMAL = "正常"
ALERT_WARNING = "预警"
ALERT_CRITICAL = "严重"


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    zone: Mapped[str] = mapped_column(String(50))  # 库区/楼层
    location_type: Mapped[str] = mapped_column(String(20), default="库房")  # 库房/展厅/修复室
    temp_min: Mapped[float] = mapped_column(Float, default=15.0)
    temp_max: Mapped[float] = mapped_column(Float, default=22.0)
    hum_min: Mapped[float] = mapped_column(Float, default=45.0)
    hum_max: Mapped[float] = mapped_column(Float, default=60.0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    collections: Mapped[list["Collection"]] = relationship(back_populates="location")
    readings: Mapped[list["EnvReading"]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["EnvAlert"]] = relationship(
        back_populates="location", cascade="all, delete-orphan"
    )


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    accession_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # 总登记号
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50))  # 陶瓷/书画/青铜器...
    dynasty: Mapped[str | None] = mapped_column(String(50), nullable=True)
    material: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dimension: Mapped[str | None] = mapped_column(String(200), nullable=True)
    weight: Mapped[str | None] = mapped_column(String(50), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 一级/二级/三级
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 来源(征集/捐赠)
    acquired_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_IN_STORAGE, index=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    location: Mapped["Location"] = relationship(back_populates="collections")
    movements: Mapped[list["Movement"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )
    exhibition_items: Mapped[list["ExhibitionItem"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )
    restorations: Mapped[list["Restoration"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )
    loans: Mapped[list["LoanRecord"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )
    inventory_items: Mapped[list["InventoryItem"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )


class Movement(Base):
    """出入库 / 流转记录"""

    __tablename__ = "movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), index=True)
    move_type: Mapped[str] = mapped_column(String(20), index=True)
    from_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )
    to_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(200), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(50), nullable=True)
    handler: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 经手人
    move_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    collection: Mapped["Collection"] = relationship(back_populates="movements")
    from_location: Mapped["Location | None"] = relationship(foreign_keys=[from_location_id])
    to_location: Mapped["Location | None"] = relationship(foreign_keys=[to_location_id])


class Exhibition(Base):
    __tablename__ = "exhibitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    venue: Mapped[str] = mapped_column(String(100))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="筹备中")  # 筹备中/开展中/已结束
    curator: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["ExhibitionItem"]] = relationship(
        back_populates="exhibition", cascade="all, delete-orphan"
    )


class ExhibitionItem(Base):
    __tablename__ = "exhibition_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    exhibition_id: Mapped[int] = mapped_column(ForeignKey("exhibitions.id"), index=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), index=True)
    display_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mounted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dismounted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="已布展")  # 已布展/已撤展

    exhibition: Mapped["Exhibition"] = relationship(back_populates="items")
    collection: Mapped["Collection"] = relationship(back_populates="exhibition_items")


class Restoration(Base):
    """修复过程记录"""

    __tablename__ = "restorations"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), index=True)
    project_name: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # 残损状况
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)  # 修复方案
    restorer: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="进行中")  # 进行中/已完成
    result: Mapped[str | None] = mapped_column(Text, nullable=True)  # 修复结果
    timeline: Mapped[list] = mapped_column(JSON, default=list)  # 过程节点 [{date,stage,note}]

    collection: Mapped["Collection"] = relationship(back_populates="restorations")


class LoanRecord(Base):
    """借展记录(出入馆借展)"""

    __tablename__ = "loan_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), index=True)
    borrowing_institution: Mapped[str] = mapped_column(String(200))
    exhibition_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    loan_date: Mapped[date] = mapped_column(Date, default=date.today)
    due_date: Mapped[date] = mapped_column(Date, index=True)  # 应还日期
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # 实际归还
    status: Mapped[str] = mapped_column(String(20), default="借出", index=True)  # 借出/已归还/已逾期
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    collection: Mapped["Collection"] = relationship(back_populates="loans")


class EnvReading(Base):
    """环境温湿度采集记录"""

    __tablename__ = "env_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    temperature: Mapped[float] = mapped_column(Float)
    humidity: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    source: Mapped[str] = mapped_column(String(20), default="传感器")  # 传感器/人工/模拟

    location: Mapped["Location"] = relationship(back_populates="readings")


class EnvAlert(Base):
    """温湿度异常提醒"""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    reading_id: Mapped[int | None] = mapped_column(ForeignKey("env_readings.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(10), default=ALERT_WARNING)  # 预警/严重
    metric: Mapped[str] = mapped_column(String(10))  # temperature / humidity
    value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    message: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(50), nullable=True)

    location: Mapped["Location"] = relationship(back_populates="alerts")


class InventoryTask(Base):
    """馆藏盘点任务(按库房/类别/等级发起,带截止日期)"""

    __tablename__ = "inventory_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # 任务单号
    title: Mapped[str] = mapped_column(String(200))
    scope_type: Mapped[str] = mapped_column(String(10))  # 库房/类别/等级
    scope_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )
    scope_value: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 类别/等级值
    initiator: Mapped[str] = mapped_column(String(50))  # 发起馆员
    deadline: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default=INV_TASK_ACTIVE, index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 结案汇总快照

    scope_location: Mapped["Location | None"] = relationship()
    items: Mapped[list["InventoryItem"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class InventoryItem(Base):
    """盘点明细:一件藏品在某次任务中的账面快照与盘点结果"""

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("inventory_tasks.id"), index=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"), index=True)
    book_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )  # 账面位置快照
    book_status: Mapped[str] = mapped_column(String(20))  # 账面状态快照
    result: Mapped[str] = mapped_column(String(10), default=INV_RESULT_PENDING, index=True)
    actual_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )  # 实物核对位置
    condition_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # 保管/完残情况
    review_status: Mapped[str] = mapped_column(String(20), default=INV_REVIEW_NONE, index=True)
    checked_by: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 盘点人
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[list] = mapped_column(JSON, default=list)  # 处理痕迹 [{time,actor,action,note}]

    task: Mapped["InventoryTask"] = relationship(back_populates="items")
    collection: Mapped["Collection"] = relationship(back_populates="inventory_items")
    book_location: Mapped["Location | None"] = relationship(foreign_keys=[book_location_id])
    actual_location: Mapped["Location | None"] = relationship(
        foreign_keys=[actual_location_id]
    )
    adjustments: Mapped[list["InventoryAdjustment"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class InventoryAdjustment(Base):
    """盘点差异调整申请:复核通过后提请,审批执行时才改写正式档案"""

    __tablename__ = "inventory_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    adjust_type: Mapped[str] = mapped_column(String(20))  # 变更位置/状态变更/损坏登记
    to_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # 申请理由
    status: Mapped[str] = mapped_column(String(20), default=INV_ADJUST_PENDING, index=True)
    applicant: Mapped[str] = mapped_column(String(50))  # 申请人
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 审批人
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    process_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    item: Mapped["InventoryItem"] = relationship(back_populates="adjustments")
    to_location: Mapped["Location | None"] = relationship()
