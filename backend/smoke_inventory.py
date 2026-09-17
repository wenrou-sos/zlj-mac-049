"""盘点模块端到端冒烟:启动 -> 占用互斥 -> 核对/差异 -> 复核保护 -> 调整审批 -> 结案 -> 回溯。"""
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)
ok = 0
fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail += 1
        print(f"  FAIL  {name}  {extra}")


# 1. 列表 + 播种数据
tasks = c.get("/api/inventories").json()
check("列表含 2 个播种任务", len(tasks) == 2, tasks)
seeded = next(t for t in tasks if "玉石器" in t["title"])
check("播种任务调整审批中", seeded["status"] == "调整审批中", seeded["status"])
check("有 1 条差异", seeded["diff_count"] == 1, seeded)
check("有 1 条待审批调整", seeded["pending_adjustments"] == 1, seeded)

# 2. 占用互斥:玉石库范围再建任务应被 409 拒绝
meta = c.get("/api/inventories/meta").json()
check("meta 含库房/类别/等级", len(meta["locations"]) >= 5 and meta["categories"], meta)
pv = c.get(
    "/api/inventories/scope-preview",
    params={"scope_type": "库房", "scope_value": "玉石器库房"},
).json()
check("范围预览占用数=1", pv["occupied"] == 1 and pv["count"] >= 1, pv)
r = c.post(
    "/api/inventories",
    json={
        "title": "重复占用测试",
        "scope_type": "库房",
        "scope_value": "玉石器库房",
        "location_id": pv["location_id"],
        "librarian": "测试员",
        "due_date": "2026-12-31",
    },
)
check("重复占用 409", r.status_code == 409, r.status_code)

# 被占用藏品档案冻结
hook_id = pv["conflicts"][0]["collection_id"]
r = c.put(f"/api/collections/{hook_id}", json={"name": "篡改测试"})
check("盘点期间档案冻结", r.status_code == 409, r.status_code)

# 3. 新建书画类别任务(无占用),走完整流程
r = c.post(
    "/api/inventories",
    json={
        "title": "书画类抽查盘点",
        "scope_type": "类别",
        "scope_value": "书画",
        "librarian": "馆员甲",
        "checker": "盘点员乙",
        "due_date": "2026-12-20",
    },
)
check("创建书画盘点", r.status_code == 200, r.text)
task = r.json()
tid = task["id"]
check("书画范围 3 件", task["total_count"] == 3, task["total_count"])
items = task["items"]
by_name = {i["snapshot_name"]: i for i in items}

# 4. 盘点:相符
fan = next(i for i in items if "折扇" in i["snapshot_name"])
r = c.post(f"/api/inventories/{tid}/items/{fan['id']}/check",
           json={"result": "相符", "checker": "盘点员乙"})
check("核对相符", r.status_code == 200 and r.json()["checked_count"] == 1, r.text)
check("状态推进为盘点中", r.json()["status"] == "盘点中", r.json()["status"])

# 溪山行旅图:损坏
painting = next(i for i in items if "溪山行旅" in i["snapshot_name"])
r = c.post(f"/api/inventories/{tid}/items/{painting['id']}/check",
           json={"result": "损坏", "condition_note": "画心右下角发现新水渍约2cm",
                 "checker": "盘点员乙"})
check("核对损坏", r.status_code == 200 and r.json()["diff_count"] == 1, r.text)

# 花鸟立轴:错位到丝织品库
flower = next(i for i in items if "花鸟" in i["snapshot_name"])
silk = next(l for l in meta["locations"] if "丝织" in l["label"])
r = c.post(f"/api/inventories/{tid}/items/{flower['id']}/check",
           json={"result": "错位", "actual_location_id": silk["id"], "checker": "盘点员乙"})
check("核对错位", r.status_code == 200 and r.json()["diff_count"] == 2, r.text)

# 错位校验:实物位置=账面时拒绝
r = c.post(f"/api/inventories/{tid}/items/{flower['id']}/check",
           json={"result": "错位", "actual_location_id": flower["snapshot_location_id"]})
check("同位置错位被拒", r.status_code == 400, r.status_code)

# 5. 差异未复核前直接调整 -> 400
r = c.post(f"/api/inventories/{tid}/adjustments",
           json={"item_id": flower["id"], "adjust_type": "移库更正",
                 "payload": {"to_location_id": flower["snapshot_location_id"]}})
check("未复核禁调整", r.status_code == 400, r.text)

# 盘盈登记(账外)
r = c.post(f"/api/inventories/{tid}/surplus",
           json={"result": "盘盈", "condition_note": "无账册册页一件(花卉)",
                 "actual_location_id": silk["id"], "checker": "盘点员乙"})
check("盘盈登记", r.status_code == 200, r.text)
surplus = next(i for i in r.json()["items"] if i["collection_id"] is None)

# 6. 复核
r = c.post(f"/api/inventories/{tid}/items/{painting['id']}/review",
           json={"confirm": True, "opinion": "水渍属实,需送修", "reviewer": "复核员丙"})
check("损坏复核确认", r.status_code == 200 and r.json()["status"] == "待复核", r.text[:200])
r = c.post(f"/api/inventories/{tid}/items/{flower['id']}/review",
           json={"confirm": False, "opinion": "再次核对位置无误", "reviewer": "复核员丙"})
check("错位复核无误->相符", r.status_code == 200, r.text)
detail = r.json()
flower_after = next(i for i in detail["items"] if i["id"] == flower["id"])
check("复核无误结果回正", flower_after["result"] == "相符", flower_after)
# 盘盈复核(直接对盘盈条目复核属实)
r = c.post(f"/api/inventories/{tid}/items/{surplus['id']}/review",
           json={"confirm": True, "opinion": "确为账外实物", "reviewer": "复核员丙"})
check("盘盈复核", r.status_code == 200, r.text)

# 7. 全部复核后、调整未处理:结案应被拒(差异必须有处置)
r = c.post(f"/api/inventories/{tid}/complete", json={"operator": "馆员甲"})
check("差异未处置禁止结案", r.status_code == 400, r.text)

# 8. 调整申请:损坏送修 + 盘盈建档
r = c.post(f"/api/inventories/{tid}/adjustments",
           json={"item_id": painting["id"], "adjust_type": "送修登记",
                 "reason": "水渍需揭裱修复",
                 "payload": {"project_name": "溪山行旅图水渍修复", "restorer": "修复部·何砚农"},
                 "applicant": "盘点员乙"})
check("送修申请", r.status_code == 200 and r.json()["pending_adjustments"] >= 1, r.text)
all_adjs = [a for it in r.json()["items"] for a in it["adjustments"]]
repair_adj = next(a for a in all_adjs if a["adjust_type"] == "送修登记")

r = c.post(f"/api/inventories/{tid}/adjustments",
           json={"item_id": surplus["id"], "adjust_type": "状态处理",
                 "reason": "账外实物,申请建档",
                 "payload": {"action": "gain", "accession_no": "SH-2026-0001",
                             "name": "无款花卉册页(盘盈)", "category": "书画",
                             "grade": "一般文物", "location_id": silk["id"]}})
check("盘盈建档申请", r.status_code == 200, r.text)
all_adjs = [a for it in r.json()["items"] for a in it["adjustments"]]
gain_adj = next(a for a in all_adjs if a["adjust_type"] == "状态处理")

# 盘盈重号建档应被拒(用已存在登记号)
r = c.post(f"/api/inventories/{tid}/adjustments",
           json={"item_id": surplus["id"], "adjust_type": "状态处理",
                 "payload": {"action": "gain", "accession_no": "SH-2012-0066", "name": "x"}})
check("盘盈重号被拒", r.status_code == 400, r.status_code)

# 9. 审批落账
r = c.post(f"/api/inventories/{tid}/adjustments/{repair_adj['id']}/decide",
           json={"approve": True, "opinion": "同意送修", "approver": "馆领导丁"})
check("批准送修", r.status_code == 200, r.text[:200])
pc = c.get(f"/api/collections/{painting['collection_id']}").json()
check("藏品已转修复中", pc["status"] == "修复中", pc["status"])

r = c.post(f"/api/inventories/{tid}/adjustments/{gain_adj['id']}/decide",
           json={"approve": False, "opinion": "来源待查,暂不建档", "approver": "馆领导丁"})
check("驳回盘盈", r.status_code == 200 and r.json()["pending_adjustments"] == 0, r.text[:200])
# 驳回后盘盈差异仍在(未结案会提示差异属实但未处理)—— 允许结案(差异已复核,无待审批)

# 10. 结案
r = c.post(f"/api/inventories/{tid}/complete", json={"operator": "馆员甲", "summary": "年度抽查完成"})
check("结案成功", r.status_code == 200, r.text)
final = r.json()
check("状态已结案", final["status"] == "已结案", final["status"])
check("结案时间有值", final["finished_at"] is not None, final)
actions = [l["action"] for l in final["logs"]]
check("留痕含发起/核对/复核/申请/批准/结案",
      {"发起盘点", "盘点核对", "差异复核", "提交调整申请", "批准调整并落账", "结案"} <= set(actions),
      actions)
# 回溯:损坏条目的盘点人/复核人/调整链
pitem = next(i for i in final["items"] if i["id"] == painting["id"])
check("回溯盘点人", pitem["checker"] == "盘点员乙", pitem["checker"])
check("回溯复核人", pitem["reviewer"] == "复核员丙", pitem["reviewer"])
approved = pitem["adjustments"][0]
check("回溯审批人", approved["approver"] == "馆领导丁", approved)

# 结案后再操作被拒
r = c.post(f"/api/inventories/{tid}/items/{fan['id']}/check", json={"result": "相符"})
check("结案后冻结", r.status_code == 400, r.status_code)

# 结案后藏品被释放,可再次纳入新盘点
r = c.post("/api/inventories",
           json={"title": "书画二次盘点", "scope_type": "类别", "scope_value": "书画",
                 "librarian": "甲", "due_date": "2026-12-31"})
check("结案后释放占用", r.status_code == 200, r.status_code)
# 清理该任务,避免影响 dashboard 计数断言
tid2 = r.json()["id"]
c.post(f"/api/inventories/{tid2}/cancel", json={"operator": "甲"})

# 11. 播种待复核任务:批准移库 -> 结案
tid_s = seeded["id"]
detail_s = c.get(f"/api/inventories/{tid_s}").json()
move_adj = next(a for it in detail_s["items"] for a in it["adjustments"])
r = c.post(f"/api/inventories/{tid_s}/adjustments/{move_adj['id']}/decide",
           json={"approve": True, "approver": "馆领导丁"})
check("播种任务移库批准", r.status_code == 200, r.text[:200])
hc = c.get(f"/api/collections/{hook_id}").json()
check("带钩库位已更正", hc["location_id"] == pv["location_id"], hc["location_id"])
moves = c.get("/api/movements", params={"collection_id": hook_id, "move_type": "移库"}).json()
check("移库台账留痕", any("盘点错位更正" in (m["purpose"] or "") for m in moves), "无台账")
r = c.post(f"/api/inventories/{tid_s}/complete", json={"operator": "保管部·周文澜"})
check("播种任务结案", r.status_code == 200 and r.json()["status"] == "已结案", r.text[:200])

# 12. dashboard
d = c.get("/api/dashboard").json()
check("dashboard 盘点字段", "inventory_active" in d and "inventory_overdue" in d, d)
check("无进行中任务(均结案/撤销)", d["inventory_active"] == 0, d["inventory_active"])

print(f"\n==== {ok} passed, {fail} failed ====")
raise SystemExit(1 if fail else 0)
