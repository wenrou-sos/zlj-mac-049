"""播种博物馆样例数据。

用法:
    python -m app.seed            # 已播种过则跳过
    python -m app.seed --reset    # 清空后重新播种(SQLite 重置自增;PostgreSQL 删除全部业务数据)
"""

import random
import sys
from datetime import date, datetime, timedelta

from .database import Base, SessionLocal, engine
from . import models
from .services.env_service import backfill_history, evaluate_reading


def _reset_all() -> None:
    """清空全部业务表(SQLite / PostgreSQL 通用)。"""
    import sqlalchemy as sa

    tables = [
        "inventory_logs",
        "inventory_adjustments",
        "inventory_items",
        "inventory_tasks",
        "alerts",
        "env_readings",
        "restorations",
        "loan_records",
        "exhibition_items",
        "exhibitions",
        "movements",
        "collections",
        "locations",
    ]
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            for t in tables:
                conn.execute(sa.text(f"DELETE FROM {t}"))
            exists = conn.execute(
                sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
            ).fetchone()
            if exists:
                conn.execute(sa.text("DELETE FROM sqlite_sequence"))
        else:
            conn.execute(
                sa.text(
                    "TRUNCATE TABLE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"
                )
            )


def _dt(d: date, h: int = 10, m: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, m)


def _seed(db) -> None:
    today = date.today()

    # ---------------- 存放位置(含温湿度阈值) ----------------
    locations_data = [
        ("A-101", "陶瓷珍品库", "一层库区", "库房", 16, 20, 48, 55),
        ("A-102", "青铜器库房", "一层库区", "库房", 16, 20, 40, 50),
        ("A-201", "书画恒温恒湿库", "二层库区", "库房", 14, 18, 50, 58),
        ("A-202", "丝织品库房", "二层库区", "库房", 15, 19, 52, 60),
        ("A-301", "玉石器库房", "三层库区", "库房", 15, 21, 45, 55),
        ("B-101", "第一展厅(古代陶瓷)", "一层展区", "展厅", 18, 22, 45, 60),
        ("B-201", "第二展厅(书画)", "二层展区", "展厅", 18, 22, 50, 60),
        ("B-301", "第三展厅(青铜文明)", "三层展区", "展厅", 18, 22, 40, 55),
        ("B-T1", "临时展厅", "一层展区", "展厅", 18, 23, 45, 60),
        ("R-101", "文物修复室", "一层工作区", "修复室", 18, 24, 40, 60),
        ("A-401", "暂存周转库", "四层库区", "库房", 15, 22, 40, 60),
        ("R-102", "文物摄影室", "一层工作区", "其他", 18, 24, 35, 60),
    ]
    locs: dict[str, models.Location] = {}
    for code, name, zone, ltype, tlo, thi, hlo, hhi in locations_data:
        loc = models.Location(
            code=code,
            name=name,
            zone=zone,
            location_type=ltype,
            temp_min=tlo,
            temp_max=thi,
            hum_min=hlo,
            hum_max=hhi,
        )
        db.add(loc)
        locs[code] = loc
    db.flush()

    # ---------------- 藏品档案 ----------------
    # (登记号, 名称, 类别, 朝代, 材质, 尺寸, 等级, 来源, 入库日, 库位code, 描述)
    collections_data = [
        ("GY-2018-0042", "青花缠枝莲纹梅瓶", "陶瓷器", "明代·永乐",
         "青花瓷", "高36.5cm 口径5.2cm", "一级文物", "拍卖会征集",
         date(2018, 4, 12), "A-101",
         "器形端庄,胎质细腻,青花发色浓艳,缠枝莲纹布局疏朗,为永乐官窑典型器。"),
        ("GY-2015-0117", "青釉莲瓣纹尊", "陶瓷器", "南朝",
         "青釉瓷", "高21.8cm 口径14.0cm", "二级文物", "考古移交",
         date(2015, 9, 3), "A-101",
         "器身饰仰覆莲瓣纹,釉色青黄莹润,开细密冰裂纹。"),
        ("QT-2009-0008", "饕餮纹青铜鼎", "青铜器", "商代晚期",
         "青铜", "高48.0cm 口径39.5cm", "一级文物", "社会捐赠",
         date(2009, 6, 18), "A-102",
         "立耳方唇,深腹圜底,三柱足;腹部饰饕餮纹,以云雷纹为地,铸造精工。"),
        ("QT-2016-0033", "蟠螭纹青铜壶", "青铜器", "战国",
         "青铜", "高32.0cm 腹径24.0cm", "二级文物", "拍卖会征集",
         date(2016, 11, 20), "A-102",
         "壶身满饰蟠螭交缠纹,肩有铺首衔环,器表有浅绿色铜锈。"),
        ("SH-2012-0066", "《溪山行旅图》(绢本摹本)", "书画", "宋代(清摹)",
         "绢本设色", "纵145.3cm 横57.8cm", "二级文物", "社会捐赠",
         date(2012, 3, 25), "A-201",
         "绢本淡设色,峰峦浑厚,行旅点景,摹写精谨,保存有清人题签。"),
        ("SH-2020-0091", "行书《兰亭序》折扇", "书画", "清代",
         "纸本", "扇面纵18.5cm 横52.0cm", "三级文物", "拍卖会征集",
         date(2020, 7, 8), "A-201",
         "洒金笺本,行书兰亭序文,笔意流畅,扇骨为竹制原骨。"),
        ("SH-2019-0074", "设色花鸟立轴", "书画", "近代",
         "纸本设色", "纵96.0cm 横42.5cm", "一般文物", "社会捐赠",
         date(2019, 10, 16), "A-201",
         "画紫藤双禽,设色明丽,题款钤印俱全。"),
        ("SS-2011-0015", "玉璧(谷纹)", "玉石器", "汉代",
         "和田青玉", "外径14.2cm 内径3.8cm", "二级文物", "考古移交",
         date(2011, 5, 9), "A-301",
         "青玉质,局部有褐色沁,两面饰排列规整的谷纹,边缘犀利。"),
        ("SS-2017-0049", "白玉雕龙纹带钩", "玉石器", "明代",
         "和田白玉", "长11.6cm", "三级文物", "拍卖会征集",
         date(2017, 8, 22), "A-301",
         "白玉温润,钩首作龙首,钩身高浮雕螭龙,雕工流畅。"),
        ("SC-2014-0027", "朱地彩绘云气纹漆奁", "漆木器", "西汉",
         "夹纻胎漆", "高13.5cm 直径21.0cm", "一级文物", "考古移交",
         date(2014, 12, 2), "A-401",
         "夹纻胎,盖面朱绘云气纹与神兽,色彩尚存,口沿有小面积漆层起翘。"),
        ("SC-2013-0058", "木雕彩绘观音坐像", "漆木器", "宋代",
         "楠木彩绘", "高58.0cm", "三级文物", "社会捐赠",
         date(2013, 6, 30), "A-401",
         "观音结跏趺坐,衣纹写实,彩绘大部剥落,木胎有细微裂隙。"),
        ("SZ-2018-0036", "缂丝花卉册页(四开)", "丝织品", "清代·乾隆",
         "缂丝", "每开纵28.0cm 横22.0cm", "二级文物", "拍卖会征集",
         date(2018, 9, 14), "A-202",
         "四开分别缂织梅、兰、竹、菊,以通经断纬法织成,设色典雅。"),
        ("GY-2022-0103", "三彩骆驼载乐俑", "陶瓷器", "唐代",
         "三彩釉陶", "高42.0cm 长38.0cm", "一级文物", "拍卖会征集",
         date(2022, 2, 18), "A-101",
         "骆驼昂首嘶鸣,峰间设乐舞平台,釉色以黄、绿、白为主,生动瑰丽。"),
    ]

    colls: dict[str, models.Collection] = {}
    for (
        acc, name, cat, dyn, mat, dim, grade, src, acquired, loc_code, desc
    ) in collections_data:
        c = models.Collection(
            accession_no=acc,
            name=name,
            category=cat,
            dynasty=dyn,
            material=mat,
            dimension=dim,
            grade=grade,
            source=src,
            acquired_date=acquired,
            status=models.STATUS_IN_STORAGE,
            location_id=locs[loc_code].id,
            description=desc,
        )
        db.add(c)
        colls[acc] = c
    db.flush()

    # ---------------- 初始入库记录 ----------------
    for acc, c in colls.items():
        acq = c.acquired_date or today
        db.add(
            models.Movement(
                collection_id=c.id,
                move_type=models.MOVE_IN,
                to_location_id=c.location_id,
                purpose="征集建档,验收入库",
                operator="保管部·周文澜",
                handler="陈立",
                move_date=_dt(acq, 14, 30),
            )
        )
    db.flush()

    # ---------------- 展览 ----------------
    # 在展:古代陶瓷艺术常设展(第一展厅)
    ex1 = models.Exhibition(
        title="千年窑火——古代陶瓷艺术常设展",
        venue="第一展厅",
        start_date=today - timedelta(days=120),
        end_date=today + timedelta(days=240),
        curator="林知秋",
        description="遴选馆藏陶瓷精品,呈现中国古代制瓷工艺与审美演进。",
    )
    # 在展:青铜文明(第三展厅)
    ex2 = models.Exhibition(
        title="吉金耀世——青铜文明特展",
        venue="第三展厅",
        start_date=today - timedelta(days=45),
        end_date=today + timedelta(days=46),
        curator="赵元朗",
        description="以商周至战国青铜器为主线,展示礼乐文明的发展脉络。",
    )
    # 已结束:书画珍品展(第二展厅)
    ex3 = models.Exhibition(
        title="翰墨千秋——馆藏书画珍品展",
        venue="第二展厅",
        start_date=today - timedelta(days=300),
        end_date=today - timedelta(days=200),
        curator="林知秋",
        description="展出馆藏宋清书画摹本与明清书法精品。",
    )
    # 筹备中:临时大展
    ex4 = models.Exhibition(
        title="丝路华章——唐代三彩艺术特展",
        venue="临时展厅",
        start_date=today + timedelta(days=20),
        end_date=today + timedelta(days=120),
        curator="苏望舒",
        description="聚焦唐三彩器物与丝路文化交流,部分展品借展自兄弟博物馆。",
    )
    db.add_all([ex1, ex2, ex3, ex4])
    db.flush()

    def _mount(ex, acc, display, days_ago):
        c = colls[acc]
        item = models.ExhibitionItem(
            exhibition_id=ex.id,
            collection_id=c.id,
            display_location=display,
            mounted_at=_dt(today - timedelta(days=days_ago)),
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
                move_date=_dt(today - timedelta(days=days_ago), 9),
                remark=display,
            )
        )
        c.status = models.STATUS_EXHIBITION
        c.location_id = None
        return item

    # 当前在展陶瓷 2 件
    _mount(ex1, "GY-2018-0042", "第一展厅独立展柜 C-03", 120)
    _mount(ex1, "GY-2015-0117", "第一展厅通柜 A-12", 120)
    # 当前在展青铜 1 件
    _mount(ex2, "QT-2009-0008", "第三展厅中心展台 01", 45)

    # 已结束书画展:布展后撤展归库
    for acc, disp in [
        ("SH-2012-0066", "第二展厅恒温展柜 B-01"),
        ("SH-2020-0091", "第二展厅通柜 B-08"),
    ]:
        c = colls[acc]
        db.add(
            models.ExhibitionItem(
                exhibition_id=ex3.id,
                collection_id=c.id,
                display_location=disp,
                mounted_at=_dt(today - timedelta(days=300)),
                dismounted_at=_dt(today - timedelta(days=200)),
                status="已撤展",
            )
        )
        db.add(
            models.Movement(
                collection_id=c.id,
                move_type=models.MOVE_EXHIBIT,
                from_location_id=c.location_id,
                purpose=f"布展:{ex3.title}",
                move_date=_dt(today - timedelta(days=300), 9),
            )
        )
        db.add(
            models.Movement(
                collection_id=c.id,
                move_type=models.MOVE_RETURN,
                to_location_id=c.location_id,
                purpose=f"撤展归库:{ex3.title}",
                move_date=_dt(today - timedelta(days=200), 16),
            )
        )
    db.flush()

    # ---------------- 修复(已完成 1 + 进行中 1) ----------------
    c_paint = colls["SC-2014-0027"]  # 漆奁已完成修复并归库
    r1 = models.Restoration(
        collection_id=c_paint.id,
        project_name="漆奁口沿起翘加固修复",
        reason="口沿小面积漆层起翘,胎体有轻微变形风险。",
        plan="先行脱水定型,再以鱼鳔胶回贴起翘漆层,随色作旧。",
        restorer="修复部·何砚农",
        start_date=today - timedelta(days=260),
        end_date=today - timedelta(days=230),
        status="已完成",
        result="漆层回贴牢固,外观与原器协调,建议库房湿度不高于55%。",
        timeline=[
            {"date": str(today - timedelta(days=260)), "stage": "立项",
             "note": "检测胎体含水量,制定脱水与加固方案"},
            {"date": str(today - timedelta(days=252)), "stage": "病害处理",
             "note": "控湿环境下缓慢脱水定型"},
            {"date": str(today - timedelta(days=240)), "stage": "修复实施",
             "note": "鱼鳔胶回贴起翘漆层,夹具固定"},
            {"date": str(today - timedelta(days=232)), "stage": "随色作旧",
             "note": "补色做旧,保持修复可识别性"},
            {"date": str(today - timedelta(days=230)), "stage": "结项",
             "note": "验收合格归库"},
        ],
    )
    db.add(r1)
    db.add(
        models.Movement(
            collection_id=c_paint.id,
            move_type=models.MOVE_REPAIR_OUT,
            from_location_id=c_paint.location_id,
            purpose="修复出库:漆奁口沿起翘加固修复",
            operator="修复部·何砚农",
            move_date=_dt(today - timedelta(days=260)),
        )
    )
    db.add(
        models.Movement(
            collection_id=c_paint.id,
            move_type=models.MOVE_REPAIR_BACK,
            to_location_id=c_paint.location_id,
            purpose="修复完成归库",
            operator="修复部·何砚农",
            move_date=_dt(today - timedelta(days=230)),
        )
    )

    c_buddha = colls["SC-2013-0058"]  # 观音像修复进行中
    r2 = models.Restoration(
        collection_id=c_buddha.id,
        project_name="木雕观音裂隙修复与彩绘加固",
        reason="木胎背部有纵向裂隙,彩绘剥落约三成。",
        plan="裂隙以同质木片加环氧树脂填补,酥解彩绘以 Paraloid B-72 渗透加固。",
        restorer="修复部·何砚农",
        start_date=today - timedelta(days=18),
        status="进行中",
        timeline=[
            {"date": str(today - timedelta(days=18)), "stage": "立项",
             "note": "送修复室,完成现状拍照与病害图绘制"},
            {"date": str(today - timedelta(days=10)), "stage": "清洁除尘",
             "note": "软毛刷配合吸尘器清除表面积尘"},
            {"date": str(today - timedelta(days=4)), "stage": "裂隙处理",
             "note": "裂隙清理完成,准备填补木片"},
        ],
    )
    db.add(r2)
    db.add(
        models.Movement(
            collection_id=c_buddha.id,
            move_type=models.MOVE_REPAIR_OUT,
            from_location_id=c_buddha.location_id,
            purpose="修复出库:木雕观音裂隙修复与彩绘加固",
            operator="修复部·何砚农",
            move_date=_dt(today - timedelta(days=18)),
        )
    )
    c_buddha.status = models.STATUS_RESTORATION
    c_buddha.location_id = None
    db.flush()

    # ---------------- 借展 ----------------
    # 已逾期:三彩骆驼 -> 西安
    c_camel = colls["GY-2022-0103"]
    l1 = models.LoanRecord(
        collection_id=c_camel.id,
        borrowing_institution="西安大唐西市博物馆",
        exhibition_title="盛唐气象——三彩与丝路文明",
        contact_person="马怀远",
        contact_phone="029-8888****",
        loan_date=today - timedelta(days=160),
        due_date=today - timedelta(days=8),
        status="借出",
        purpose="参加馆际交流展,借期6个月。",
        remark="对方来函申请延期,正在报批中。",
    )
    db.add(l1)
    db.add(
        models.Movement(
            collection_id=c_camel.id,
            move_type=models.MOVE_LOAN_OUT,
            from_location_id=c_camel.location_id,
            purpose="借展:西安大唐西市博物馆 / 盛唐气象——三彩与丝路文明",
            handler="马怀远",
            move_date=_dt(today - timedelta(days=160)),
            remark=f"应还 {today - timedelta(days=8)}",
        )
    )
    c_camel.status = models.STATUS_LOAN_OUT
    c_camel.location_id = None

    # 临期(12 天后到期):缂丝册页 -> 苏州
    c_kesi = colls["SZ-2018-0036"]
    l2 = models.LoanRecord(
        collection_id=c_kesi.id,
        borrowing_institution="苏州丝绸博物馆",
        exhibition_title="织绣华章——清代缂丝艺术展",
        contact_person="沈婉清",
        contact_phone="0512-6755****",
        loan_date=today - timedelta(days=80),
        due_date=today + timedelta(days=12),
        status="借出",
        purpose="参加专题展览,运输采用恒温恒湿防震箱。",
    )
    db.add(l2)
    db.add(
        models.Movement(
            collection_id=c_kesi.id,
            move_type=models.MOVE_LOAN_OUT,
            from_location_id=c_kesi.location_id,
            purpose="借展:苏州丝绸博物馆 / 织绣华章——清代缂丝艺术展",
            handler="沈婉清",
            move_date=_dt(today - timedelta(days=80)),
            remark=f"应还 {today + timedelta(days=12)}",
        )
    )
    c_kesi.status = models.STATUS_LOAN_OUT
    c_kesi.location_id = None

    # 未来到期(约2个月):玉璧 -> 上海
    c_jade = colls["SS-2011-0015"]
    l3 = models.LoanRecord(
        collection_id=c_jade.id,
        borrowing_institution="上海博物馆",
        exhibition_title="礼玉之邦——古代玉器文明展",
        contact_person="顾明珩",
        contact_phone="021-6372****",
        loan_date=today - timedelta(days=40),
        due_date=today + timedelta(days=62),
        status="借出",
        purpose="馆际合作展览,借期约4个月。",
    )
    db.add(l3)
    db.add(
        models.Movement(
            collection_id=c_jade.id,
            move_type=models.MOVE_LOAN_OUT,
            from_location_id=c_jade.location_id,
            purpose="借展:上海博物馆 / 礼玉之邦——古代玉器文明展",
            handler="顾明珩",
            move_date=_dt(today - timedelta(days=40)),
            remark=f"应还 {today + timedelta(days=62)}",
        )
    )
    c_jade.status = models.STATUS_LOAN_OUT
    c_jade.location_id = None

    # 已归还的历史借展:蟠螭纹青铜壶 -> 南京
    c_hu = colls["QT-2016-0033"]
    l4 = models.LoanRecord(
        collection_id=c_hu.id,
        borrowing_institution="南京博物院",
        exhibition_title="吴越楚青铜器联展",
        contact_person="钱穆之",
        contact_phone="025-8480****",
        loan_date=today - timedelta(days=420),
        due_date=today - timedelta(days=330),
        return_date=today - timedelta(days=332),
        status="已归还",
        purpose="馆际联展。",
        remark="如期归还,点验无损。",
    )
    db.add(l4)
    db.add(
        models.Movement(
            collection_id=c_hu.id,
            move_type=models.MOVE_LOAN_OUT,
            from_location_id=c_hu.location_id,
            purpose="借展:南京博物院 / 吴越楚青铜器联展",
            handler="钱穆之",
            move_date=_dt(today - timedelta(days=420)),
        )
    )
    db.add(
        models.Movement(
            collection_id=c_hu.id,
            move_type=models.MOVE_LOAN_BACK,
            to_location_id=c_hu.location_id,
            purpose="借展归还",
            move_date=_dt(today - timedelta(days=332)),
        )
    )
    db.flush()

    # 其他日常流转样例:白玉带钩移库(从 A-301 -> A-401 再移回,保持现状在库)
    hook = colls["SS-2017-0049"]
    db.add(
        models.Movement(
            collection_id=hook.id,
            move_type=models.MOVE_TRANSFER,
            from_location_id=hook.location_id,
            to_location_id=locs["A-401"].id,
            purpose="库区盘点临时移位",
            operator="保管部·周文澜",
            handler="陈立",
            move_date=_dt(today - timedelta(days=30)),
        )
    )
    db.add(
        models.Movement(
            collection_id=hook.id,
            move_type=models.MOVE_TRANSFER,
            from_location_id=locs["A-401"].id,
            to_location_id=hook.location_id,
            purpose="盘点完成移回原库位",
            operator="保管部·周文澜",
            handler="陈立",
            move_date=_dt(today - timedelta(days=28)),
        )
    )

    # 花鸟立轴:出库拍照后归库
    flower = colls["SH-2019-0074"]
    db.add(
        models.Movement(
            collection_id=flower.id,
            move_type=models.MOVE_OUT,
            from_location_id=flower.location_id,
            purpose="数字影像采集出库",
            operator="信息部·韩墨",
            move_date=_dt(today - timedelta(days=12)),
        )
    )
    db.add(
        models.Movement(
            collection_id=flower.id,
            move_type=models.MOVE_RETURN,
            to_location_id=flower.location_id,
            purpose="影像采集完成归库",
            operator="信息部·韩墨",
            move_date=_dt(today - timedelta(days=12), 16),
        )
    )
    db.flush()

    # ---------------- 环境历史 + 异常 ----------------
    random.seed(42)
    monitored = ["A-101", "A-102", "A-201", "A-202", "B-101", "B-301"]
    for code in monitored:
        backfill_history(db, locs[code], hours=72, points=48)
    db.flush()

    # 当前异常 1:书画库温度超标(预警)—— 6 小时前
    loc_sh = locs["A-201"]
    r_warn = models.EnvReading(
        location_id=loc_sh.id, temperature=19.8, humidity=54.0,
        recorded_at=datetime.utcnow() - timedelta(hours=6), source="传感器",
    )
    db.add(r_warn)
    db.flush()
    evaluate_reading(db, r_warn, loc_sh)

    # 当前异常 2:陶瓷库湿度严重超标 —— 40 分钟前
    loc_cer = locs["A-101"]
    r_crit = models.EnvReading(
        location_id=loc_cer.id, temperature=19.2, humidity=68.5,
        recorded_at=datetime.utcnow() - timedelta(minutes=40), source="传感器",
    )
    db.add(r_crit)
    db.flush()
    evaluate_reading(db, r_crit, loc_cer)

    # 已处理的历史异常:青铜展厅温度曾超标
    loc_b3 = locs["B-301"]
    r_old = models.EnvReading(
        location_id=loc_b3.id, temperature=24.6, humidity=48.0,
        recorded_at=datetime.utcnow() - timedelta(days=2), source="传感器",
    )
    db.add(r_old)
    db.flush()
    old_alerts = evaluate_reading(db, r_old, loc_b3)
    for a in old_alerts:
        a.acknowledged = True
        a.acknowledged_at = a.created_at + timedelta(hours=2)
        a.acknowledged_by = "设备部·卢工"

    db.flush()

    # ---------------- 馆藏盘点 ----------------
    def _inv_item(task, c, result=models.INV_RESULT_PENDING, **kw):
        loc_name = None
        if c.location_id:
            loc = db.get(models.Location, c.location_id)
            loc_name = f"{loc.code} {loc.name}" if loc else None
        item = models.InventoryItem(
            task_id=task.id,
            collection_id=c.id,
            snapshot_accession_no=c.accession_no,
            snapshot_name=c.name,
            snapshot_location_id=c.location_id,
            snapshot_location_name=loc_name,
            snapshot_status=c.status,
            result=result,
            **kw,
        )
        db.add(item)
        return item

    def _inv_log(task, action, detail, operator, days_ago, item_id=None):
        db.add(
            models.InventoryLog(
                task_id=task.id,
                item_id=item_id,
                action=action,
                detail=detail,
                operator=operator,
                created_at=datetime.utcnow() - timedelta(days=days_ago),
            )
        )

    # 任务 1:玉石器库房专项盘点(进行中,含 1 错位 + 1 损坏差异)
    jade_loc = locs["A-301"]
    t1 = models.InventoryTask(
        title="2026 年度玉石器库房专项盘点",
        scope_type="库房",
        scope_value=jade_loc.name,
        location_id=jade_loc.id,
        librarian="保管部·周文澜",
        checker="陈立",
        start_date=today - timedelta(days=6),
        due_date=today + timedelta(days=3),
        status=models.INV_ADJUSTING,
        remark="重点核对一级、二级文物账实与库位一致情况。",
    )
    db.add(t1)
    db.flush()
    jade_colls = [c for c in colls.values() if c.location_id == jade_loc.id]
    for c in jade_colls:
        if c.id == hook.id:
            continue  # 带钩下方单独登记为错位
        _inv_item(t1, c, models.INV_RESULT_MATCH,
                  checker="陈立", checked_at=_dt(today - timedelta(days=5), 15))
    # 白玉带钩错位:账面 A-301,实物在周转库 A-401
    hook = colls["SS-2017-0049"]
    misplaced_item = models.InventoryItem(
        task_id=t1.id,
        collection_id=hook.id,
        snapshot_accession_no=hook.accession_no,
        snapshot_name=hook.name,
        snapshot_location_id=hook.location_id,
        snapshot_location_name=f"{jade_loc.code} {jade_loc.name}",
        snapshot_status=hook.status,
        result=models.INV_RESULT_MISPLACED,
        actual_location_id=locs["A-401"].id,
        actual_location_name=f"{locs['A-401'].code} {locs['A-401'].name}",
        condition_note="实物在周转库 A-401 第 2 排架发现,与账面库位不符",
        checker="陈立",
        checked_at=_dt(today - timedelta(days=4), 11),
        review_status=models.INV_REVIEW_CONFIRM,
        review_opinion="复核确认实物确在周转库,系前期借展归库时误放,建议移库更正。",
        reviewer="保管部·周文澜",
        reviewed_at=_dt(today - timedelta(days=2), 10),
    )
    db.add(misplaced_item)
    db.flush()
    # 错位已提交移库调整,待审批
    db.add(
        models.InventoryAdjustment(
            task_id=t1.id,
            item_id=misplaced_item.id,
            adjust_type=models.ADJUST_MOVE,
            reason="归库时误放周转库,申请移库更正回玉石器库房",
            payload={"to_location_id": jade_loc.id},
            applicant="陈立",
        )
    )
    _inv_log(t1, "发起盘点", f"范围:库房「{jade_loc.name}」,共 {len(jade_colls)} 件;截止 {today + timedelta(days=3)}",
             "保管部·周文澜", 6)
    _inv_log(t1, "盘点核对", f"{hook.accession_no} {hook.name}:错位",
             "陈立", 4, misplaced_item.id)
    _inv_log(t1, "差异复核", f"{hook.accession_no}:差异属实", "保管部·周文澜", 2, misplaced_item.id)
    _inv_log(t1, "提交调整申请", f"{hook.accession_no}:移库更正", "陈立", 2, misplaced_item.id)

    # 任务 2:一级文物全面盘点(已结案,含盘亏销账历史,全链路留痕)
    t2 = models.InventoryTask(
        title="2025 年度一级文物全面盘点",
        scope_type="等级",
        scope_value="一级文物",
        librarian="馆办·孟昭年",
        checker="盘点小组",
        start_date=today - timedelta(days=200),
        due_date=today - timedelta(days=160),
        finished_at=_dt(today - timedelta(days=155), 17),
        status=models.INV_COMPLETED,
        remark="年度一级文物专项核查,账实相符率良好。",
    )
    db.add(t2)
    db.flush()
    grade_one = [c for c in colls.values() if c.grade == "一级文物"]
    for c in grade_one:
        _inv_item(t2, c, models.INV_RESULT_MATCH,
                  checker="盘点小组",
                  checked_at=_dt(today - timedelta(days=180), 15))
    _inv_log(t2, "发起盘点", f"范围:等级「一级文物」,共 {len(grade_one)} 件", "馆办·孟昭年", 200)
    _inv_log(t2, "结案",
             f"共盘 {len(grade_one)} 件,账实全部相符;批准调整 0 项",
             "馆办·孟昭年", 155)

    db.commit()


def main() -> None:
    reset = "--reset" in sys.argv

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    existing = db.query(models.Collection).count()
    db.close()

    if existing and not reset:
        print(f"数据库已有 {existing} 件藏品,跳过播种。如需重建请使用:python -m app.seed --reset")
        return

    if existing:
        print("重置数据...")
        _reset_all()

    db = SessionLocal()
    try:
        _seed(db)
        n_collections = db.query(models.Collection).count()
        n_locations = db.query(models.Location).count()
        n_alerts = (
            db.query(models.EnvAlert).filter(models.EnvAlert.acknowledged.is_(False)).count()
        )
        print(
            f"播种完成: {n_locations} 个存放位置, {n_collections} 件藏品; "
            f"当前未处理温湿度告警 {n_alerts} 条。"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
