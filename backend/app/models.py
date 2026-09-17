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

# 温湿度告警级别
ALERT_NORMAL = "正常"
ALERT_WARNING = "预警"
ALERT_CRITICAL = "严重"

# 盘点任务状态
INV_PENDING = "待盘点"
INV_IN_PROGRESS = "盘点中"
INV_REVIEWING = "待复核"
INV_ADJUSTING = "调整审批中"
INV_COMPLETED = "已结案"
INV_CANCELLED = "已撤销"

# 盘点进行中(藏品被任务占用)的状态集合
INV_ACTIVE_STATUSES = (
    INV_PENDING,
    INV_IN_PROGRESS,
    INV_REVIEWING,
    INV_ADJUSTING,
)

# 盘点结果
INV_RESULT_PENDING = "未盘"
INV_RESULT_MATCH = "相符"
INV_RESULT_SURPLUS = "盘盈"
INV_RESULT_LOSS = "盘亏"
INV_RESULT_MISPLACED = "错位"
INV_RESULT_DAMAGED = "损坏"

# 盘点任务范围
INV_SCOPE_LOCATION = "库房"
INV_SCOPE_CATEGORY = "类别"
INV_SCOPE_GRADE = "等级"

# 差异复核结论
INV_REVIEW_CONFIRM = "差异属实"
INV_REVIEW_FALSE = "复核无误"
INV_REVIEW_PENDING = "待复核"

# 调整申请
ADJUST_MOVE = "移库更正"
ADJUST_REPAIR = "送修登记"
ADJUST_INFO = "档案更正"
ADJUST_STATUS = "状态处理"  # 盘盈建档 / 盘亏销账
ADJUST_PENDING = "待审批"
ADJUST_APPROVED = "已批准"
ADJUST_REJECTED = "已驳回"

# 盘点调整产生的出入库流转类型
MOVE_INVENTORY_GAIN = "盘盈入库"
MOVE_INVENTORY_LOSS = "盘亏销账"


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
    adjustments: Mapped[list["InventoryAdjustment"]] = relationship(
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
    """馆藏盘点任务:按库房 / 类别 / 等级发起,带截止日期"""

    __tablename__ = "inventory_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    scope_type: Mapped[str] = mapped_column(String(10))  # 库房/类别/等级
    scope_value: Mapped[str] = mapped_column(String(100))  # 具体库房名/类别名/等级名
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )  # scope_type=库房 时指向具体库房
    librarian: Mapped[str] = mapped_column(String(50))  # 发起人(馆员)
    checker: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 指定盘点员
    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    due_date: Mapped[date] = mapped_column(Date, index=True)  # 截止日期
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=INV_PENDING, index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    items: Mapped[list["InventoryItem"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    logs: Mapped[list["InventoryLog"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="InventoryLog.id"
    )
    adjustments: Mapped[list["InventoryAdjustment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class InventoryItem(Base):
    """盘点任务明细:任务发起时对在册藏品建立快照,逐件核对"""

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("inventory_tasks.id"), index=True)
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id"), nullable=True, index=True
    )  # 盘盈(账外实物)在建档前为空
    # 建账快照(盘点期间正式档案可能因审批而变更,快照保留盘点时的原始依据)
    snapshot_accession_no: Mapped[str] = mapped_column(String(32))
    snapshot_name: Mapped[str] = mapped_column(String(200))
    snapshot_location_id: Mapped[int | None] = mapped_column(nullable=True)
    snapshot_location_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    snapshot_status: Mapped[str] = mapped_column(String(20))

    result: Mapped[str] = mapped_column(String(10), default=INV_RESULT_PENDING, index=True)
    actual_location_id: Mapped[int | None] = mapped_column(nullable=True)
    actual_location_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    condition_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # 残损/保管信息
    checker: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 实际盘点人
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    review_status: Mapped[str] = mapped_column(String(10), default=INV_REVIEW_PENDING)
    review_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    task: Mapped["InventoryTask"] = relationship(back_populates="items")
    collection: Mapped["Collection | None"] = relationship(back_populates="inventory_items")
    adjustments: Mapped[list["InventoryAdjustment"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class InventoryAdjustment(Base):
    """差异处理调整申请:批准前不动正式档案,批准后才落账"""

    __tablename__ = "inventory_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("inventory_tasks.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id"), nullable=True
    )  # 盘盈(账外实物)没有明细行
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id"), nullable=True
    )  # 盘盈建档后回填
    adjust_type: Mapped[str] = mapped_column(String(20))  # 移库更正/送修登记/档案更正/状态处理
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # 申请内容(目标库位/档案字段/新藏品)
    applicant: Mapped[str | None] = mapped_column(String(50), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(10), default=ADJUST_PENDING, index=True)
    approver: Mapped[str | None] = mapped_column(String(50), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approve_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["InventoryTask"] = relationship(back_populates="adjustments")
    item: Mapped["InventoryItem | None"] = relationship(back_populates="adjustments")
    collection: Mapped["Collection | None"] = relationship(back_populates="adjustments")


class InventoryLog(Base):
    """盘点操作留痕:盘点 / 复核 / 申请 / 审批 / 结案全链路可回溯"""

    __tablename__ = "inventory_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("inventory_tasks.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    task: Mapped["InventoryTask"] = relationship(back_populates="logs")
