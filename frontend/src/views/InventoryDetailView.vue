<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { inventoryApi, locationApi } from '../api'

const route = useRoute()
const router = useRouter()
const taskId = route.params.id
const task = ref(null)
const loading = ref(false)
const locations = ref([])

const RESULT_TYPES = [
  { value: '相符', type: 'success' },
  { value: '盘盈', type: 'warning' },
  { value: '盘亏', type: 'danger' },
  { value: '错位', type: 'warning' },
  { value: '损坏', type: 'danger' },
]
const resultTag = (r) => ({ 相符: 'success', 盘盈: 'warning', 盘亏: 'danger', 错位: 'warning', 损坏: 'danger', 未盘: 'info' }[r] || 'info')

const itemFilter = ref('all')
const filteredItems = computed(() => {
  if (!task.value) return []
  const items = task.value.items
  if (itemFilter.value === 'pending') return items.filter((i) => i.result === '未盘')
  if (itemFilter.value === 'diff') return items.filter((i) => ['盘盈', '盘亏', '错位', '损坏'].includes(i.result))
  if (itemFilter.value === 'review')
    return items.filter(
      (i) => ['盘盈', '盘亏', '错位', '损坏'].includes(i.result) && i.review_status === '待复核'
    )
  return items
})

const editable = computed(() => task.value && ['待盘点', '盘点中', '待复核', '调整审批中'].includes(task.value.status))

async function load() {
  loading.value = true
  try {
    task.value = await inventoryApi.get(taskId)
  } finally {
    loading.value = false
  }
}

// ---------- 盘点核对 ----------
const checkDialog = ref(false)
const checkTarget = ref(null)
const checkForm = reactive({
  result: '相符', actual_location_id: null, condition_note: '', checker: '',
})

function locLabel(id) {
  const l = locations.value.find((x) => x.id === id)
  return l ? `${l.code} ${l.name}` : '—'
}

function openCheck(row) {
  checkTarget.value = row
  Object.assign(checkForm, {
    result: row.result === '未盘' ? '相符' : row.result,
    actual_location_id: row.actual_location_id || null,
    condition_note: row.condition_note || '',
    checker: row.checker || task.value.checker || '',
  })
  checkDialog.value = true
}

async function submitCheck() {
  const payload = {
    result: checkForm.result,
    actual_location_id: checkForm.actual_location_id,
    condition_note: checkForm.condition_note || null,
    checker: checkForm.checker || null,
  }
  await inventoryApi.check(taskId, checkTarget.value.id, payload)
  ElMessage.success('核对结果已保存')
  checkDialog.value = false
  load()
}

// ---------- 账外盘盈 ----------
const surplusDialog = ref(false)
const surplusForm = reactive({ name: '', actual_location_id: null, checker: '' })
function openSurplus() {
  Object.assign(surplusForm, {
    name: '', actual_location_id: task.value.location_id, checker: task.value.checker || '',
  })
  surplusDialog.value = true
}
async function submitSurplus() {
  await inventoryApi.surplus(taskId, {
    result: '盘盈',
    condition_note: surplusForm.name || null,
    actual_location_id: surplusForm.actual_location_id,
    checker: surplusForm.checker || null,
  })
  ElMessage.success('账外实物已登记为盘盈,待复核与建档审批')
  surplusDialog.value = false
  load()
}

// ---------- 复核 ----------
async function review(row, confirm) {
  let opinion = ''
  try {
    const r = await ElMessageBox.prompt(
      confirm ? '确认该差异属实?请填写复核意见(将进入差异处理)' : '复核后判定账实相符?请说明',
      confirm ? '复核:差异属实' : '复核:判定无误',
      { inputType: 'textarea', confirmButtonText: '提交复核', cancelButtonText: '取消' }
    )
    opinion = r.value
  } catch (e) {
    return
  }
  await inventoryApi.review(taskId, row.id, { confirm, opinion, reviewer: '复核人' })
  ElMessage.success(confirm ? '已确认差异,可发起调整申请' : '差异解除,回归账实相符')
  load()
}

// ---------- 调整申请 ----------
const adjustDialog = ref(false)
const adjustTarget = ref(null)
const adjustForm = reactive({ adjust_type: '', reason: '', payload: {}, applicant: '' })

function canApply(row) {
  return row.review_status === '差异属实' && editable.value
}
function applyOptions(row) {
  const opts = []
  if (row.result === '错位') opts.push({ value: '移库更正', label: '移库更正(按实物位置改账)' })
  if (row.result === '损坏') opts.push({ value: '送修登记', label: '送修登记(立项修复)' })
  if (row.result === '盘亏') opts.push({ value: '状态处理', label: '盘亏销账' })
  if (row.result === '盘盈') opts.push({ value: '状态处理', label: '盘盈建档' })
  opts.push({ value: '档案更正', label: '档案更正(保管信息)' })
  return opts
}

function openAdjust(row) {
  adjustTarget.value = row
  const first = applyOptions(row)[0].value
  Object.assign(adjustForm, {
    adjust_type: first, reason: '', payload: defaultPayload(first, row), applicant: row.checker || '',
  })
  adjustDialog.value = true
}

function defaultPayload(type, row) {
  if (type === '移库更正') return { to_location_id: row.actual_location_id }
  if (type === '送修登记') return { project_name: '', restorer: '', plan: '' }
  if (type === '档案更正')
    return { fields: { name: '', dynasty: '', material: '', dimension: '', grade: '', description: '' } }
  if (type === '状态处理') {
    return row.result === '盘盈'
      ? { action: 'gain', accession_no: '', name: row.snapshot_name, category: '', grade: '', location_id: row.actual_location_id }
      : { action: 'loss' }
  }
  return {}
}

function onAdjustTypeChange(v) {
  adjustForm.payload = defaultPayload(v, adjustTarget.value)
}

async function submitAdjust() {
  const payload = JSON.parse(JSON.stringify(adjustForm.payload))
  // 档案更正:只提交非空字段
  if (adjustForm.adjust_type === '档案更正') {
    payload.fields = Object.fromEntries(Object.entries(payload.fields || {}).filter(([, v]) => v !== ''))
    if (!Object.keys(payload.fields).length) {
      ElMessage.warning('请至少填写一项要更正的档案内容')
      return
    }
  }
  await inventoryApi.applyAdjustment(taskId, {
    item_id: adjustTarget.value.id,
    adjust_type: adjustForm.adjust_type,
    reason: adjustForm.reason || null,
    payload,
    applicant: adjustForm.applicant || null,
  })
  ElMessage.success('调整申请已提交,等待审批(批准前正式档案不变)')
  adjustDialog.value = false
  load()
}

// ---------- 审批 ----------
async function decide(adj, approve) {
  let r
  try {
    r = await ElMessageBox.prompt(
      approve ? `批准「${adj.adjust_type}」并落账?请填写审批意见` : `驳回「${adj.adjust_type}」?请说明原因`,
      approve ? '批准调整' : '驳回调整',
      { inputType: 'textarea', confirmButtonText: approve ? '批准并落账' : '确认驳回', cancelButtonText: '取消' }
    )
  } catch (e) {
    return
  }
  await inventoryApi.decideAdjustment(taskId, adj.id, {
    approve, opinion: r.value, approver: '审批人',
  })
  ElMessage[approve ? 'success' : 'warning'](approve ? '已批准并更新正式档案/台账' : '已驳回')
  load()
}

const pendingAdjustments = computed(() =>
  (task.value?.adjustments || []).filter((a) => a.status === '待审批')
)
const allAdjustments = computed(() => task.value?.adjustments || [])

// ---------- 结案 / 撤销 ----------
const completeDialog = ref(false)
const completeForm = reactive({ summary: '' })
function openComplete() {
  completeForm.summary = ''
  completeDialog.value = true
}
async function submitComplete() {
  await inventoryApi.complete(taskId, { operator: task.value.librarian, summary: completeForm.summary || null })
  ElMessage.success('盘点任务已结案')
  completeDialog.value = false
  load()
}
async function cancelTask() {
  try {
    await ElMessageBox.confirm('撤销后释放全部藏品占用,且不可再盘点。确认撤销?', '撤销盘点任务', {
      type: 'warning',
    })
  } catch (e) {
    return
  }
  await inventoryApi.cancel(taskId, { operator: task.value.librarian, summary: '手动撤销' })
  ElMessage.success('任务已撤销')
  load()
}

const blockers = computed(() => {
  if (!task.value) return []
  const b = []
  if (task.value.pending_count) b.push(`还有 ${task.value.pending_count} 件未盘点`)
  const diffs = task.value.items.filter((i) => ['盘盈', '盘亏', '错位', '损坏'].includes(i.result))
  const ur = diffs.filter((i) => i.review_status === '待复核').length
  if (ur) b.push(`${ur} 条差异未复核`)
  if (task.value.pending_adjustments) b.push(`${task.value.pending_adjustments} 条调整申请待审批`)
  return b
})

function fmt(t) {
  return t ? t.replace('T', ' ').slice(0, 16) : '—'
}

onMounted(async () => {
  locations.value = await locationApi.list()
  load()
})
</script>

<template>
  <div class="page-container" v-loading="loading">
    <div v-if="task">
      <div class="head">
        <el-button link :icon="'ArrowLeft'" @click="router.push('/inventories')">返回盘点列表</el-button>
        <h2 class="page-title" style="margin-top:6px">
          {{ task.title }}
          <el-tag
            :type="{ 待盘点: 'info', 盘点中: 'primary', 待复核: 'warning', 调整审批中: 'warning', 已结案: 'success', 已撤销: 'info' }[task.status]"
            effect="dark"
            style="margin-left:10px"
          >{{ task.status }}</el-tag>
          <el-tag v-if="task.overdue" type="danger" effect="plain">已逾期 {{ -task.days_remaining }} 天</el-tag>
        </h2>
        <p class="page-sub">
          {{ task.scope_type }}「{{ task.scope_value }}」 · 发起 {{ task.librarian }} ·
          盘点员 {{ task.checker || '未指定' }} ·
          {{ task.start_date }} 至 <b :class="{ overdue: task.overdue }">{{ task.due_date }}</b>
        </p>
      </div>

      <!-- 统计 -->
      <el-row :gutter="12" class="stats">
        <el-col :span="4"><el-card shadow="never"><el-statistic title="应盘(件)" :value="task.total_count" /></el-card></el-col>
        <el-col :span="4"><el-card shadow="never"><el-statistic title="已盘(件)" :value="task.checked_count" /></el-card></el-col>
        <el-col :span="4"><el-card shadow="never"><el-statistic title="未盘(件)" :value="task.pending_count" /></el-card></el-col>
        <el-col :span="4"><el-card shadow="never"><el-statistic title="差异(条)" :value="task.diff_count" /></el-card></el-col>
        <el-col :span="4"><el-card shadow="never"><el-statistic title="待审批调整" :value="task.pending_adjustments" /></el-card></el-col>
        <el-col :span="4">
          <el-card shadow="never">
            <div class="progress-card">
              <div class="mini-title">盘点进度</div>
              <el-progress :percentage="task.total_count ? Math.round(task.checked_count / task.total_count * 100) : 0" />
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 操作条 -->
      <el-card shadow="never" style="margin-top:14px">
        <div class="toolbar">
          <el-radio-group v-model="itemFilter">
            <el-radio-button label="all">全部({{ task.total_count }})</el-radio-button>
            <el-radio-button label="pending">未盘({{ task.pending_count }})</el-radio-button>
            <el-radio-button label="diff">差异({{ task.diff_count }})</el-radio-button>
            <el-radio-button label="review">待复核</el-radio-button>
          </el-radio-group>
          <div class="spacer"></div>
          <template v-if="editable">
            <el-button :icon="'CirclePlus'" @click="openSurplus">登记账外盘盈</el-button>
            <el-button type="success" :icon="'CircleCheck'" :disabled="blockers.length > 0" @click="openComplete">
              结案
            </el-button>
            <el-button type="danger" plain :icon="'Close'" @click="cancelTask">撤销</el-button>
          </template>
        </div>
        <el-alert
          v-if="editable && blockers.length"
          type="warning"
          :closable="false"
          style="margin-bottom:10px"
          :title="'结案前还需完成:' + blockers.join('、')"
        />

        <el-table :data="filteredItems" stripe row-key="id" :default-sort="{ prop: 'result' }">
          <el-table-column label="结果" width="90">
            <template #default="{ row }">
              <el-tag :type="resultTag(row.result)" size="small" effect="dark">{{ row.result }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="藏品(账面快照)" min-width="220">
            <template #default="{ row }">
              <el-link v-if="row.collection_id" type="primary" @click="router.push(`/collections/${row.collection_id}`)">
                {{ row.snapshot_accession_no }}
              </el-link>
              <el-tag v-else size="small" type="warning">账外</el-tag>
              {{ row.snapshot_name }}
              <div style="font-size:11px;color:#909399">建账状态:{{ row.snapshot_status }}</div>
            </template>
          </el-table-column>
          <el-table-column label="账面位置" min-width="160">
            <template #default="{ row }">{{ row.snapshot_location_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="实物核对" min-width="200">
            <template #default="{ row }">
              <div v-if="row.checked_at">
                <div v-if="row.actual_location_name">实物位置:{{ row.actual_location_name }}</div>
                <div v-if="row.condition_note" style="color:#c05645">状况:{{ row.condition_note }}</div>
                <div style="font-size:11px;color:#909399">
                  {{ row.checker }} · {{ fmt(row.checked_at) }}
                </div>
              </div>
              <span v-else style="color:#c2c7cc">未核对</span>
            </template>
          </el-table-column>
          <el-table-column label="复核" width="150">
            <template #default="{ row }">
              <el-tag v-if="row.review_status === '差异属实'" type="danger" size="small">差异属实</el-tag>
              <el-tag v-else-if="row.review_status === '复核无误'" type="success" size="small">复核无误</el-tag>
              <el-tag v-else-if="['盘盈', '盘亏', '错位', '损坏'].includes(row.result)" type="warning" size="small">
                待复核
              </el-tag>
              <span v-else style="color:#c2c7cc">—</span>
              <div v-if="row.reviewer" style="font-size:11px;color:#909399">{{ row.reviewer }}</div>
            </template>
          </el-table-column>
          <el-table-column label="调整" min-width="150">
            <template #default="{ row }">
              <template v-for="a in row.adjustments" :key="a.id">
                <el-tag :type="a.status === '已批准' ? 'success' : a.status === '已驳回' ? 'info' : 'danger'"
                  size="small" effect="plain" style="margin:2px">
                  {{ a.adjust_type }}·{{ a.status }}
                </el-tag>
              </template>
              <span v-if="!row.adjustments.length" style="color:#c2c7cc">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="230" fixed="right">
            <template #default="{ row }">
              <template v-if="editable">
                <el-button link type="primary" size="small"
                  :disabled="['待复核', '调整审批中'].includes(task.status)"
                  @click="openCheck(row)">
                  {{ row.result === '未盘' ? '核对' : '重核' }}
                </el-button>
                <el-button v-if="['盘盈', '盘亏', '错位', '损坏'].includes(row.result) && row.review_status === '待复核'"
                  link type="warning" size="small" @click="review(row, true)">属实</el-button>
                <el-button v-if="['盘盈', '盘亏', '错位', '损坏'].includes(row.result) && row.review_status === '待复核'"
                  link type="success" size="small" @click="review(row, false)">无误</el-button>
                <el-button v-if="canApply(row)" link type="danger" size="small" @click="openAdjust(row)">
                  调整申请
                </el-button>
              </template>
              <span v-else style="color:#c2c7cc">已闭环</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 调整审批 -->
      <el-card v-if="allAdjustments.length" shadow="never" style="margin-top:14px" header="差异调整申请与审批">
        <el-table :data="allAdjustments" stripe>
          <el-table-column prop="id" label="编号" width="70">
            <template #default="{ row }">#{{ row.id }}</template>
          </el-table-column>
          <el-table-column prop="adjust_type" label="调整类型" width="120" />
          <el-table-column label="关联藏品" min-width="180">
            <template #default="{ row }">
              <span v-if="row.accession_no">{{ row.accession_no }} {{ row.collection_name }}</span>
              <span v-else style="color:#909399">账外实物</span>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="申请理由" min-width="180" show-overflow-tooltip />
          <el-table-column label="申请人/审批人" width="150">
            <template #default="{ row }">
              {{ row.applicant || '—' }}
              <div style="font-size:11px;color:#909399">{{ row.approver || '' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="状态/时间" width="170">
            <template #default="{ row }">
              <el-tag :type="row.status === '已批准' ? 'success' : row.status === '已驳回' ? 'info' : 'danger'" size="small">
                {{ row.status }}
              </el-tag>
              <div style="font-size:11px;color:#909399">
                {{ row.approved_at ? fmt(row.approved_at) : fmt(row.applied_at) }}
              </div>
            </template>
          </el-table-column>
          <el-table-column label="审批" width="130" fixed="right">
            <template #default="{ row }">
              <template v-if="row.status === '待审批' && editable">
                <el-button link type="success" size="small" @click="decide(row, true)">批准</el-button>
                <el-button link type="danger" size="small" @click="decide(row, false)">驳回</el-button>
              </template>
              <span v-else style="color:#c2c7cc">—</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 处理留痕 -->
      <el-card shadow="never" style="margin-top:14px" header="处理留痕(盘点 / 复核 / 调整 / 结案 全链路可回溯)">
        <el-timeline>
          <el-timeline-item
            v-for="log in [...task.logs].reverse()"
            :key="log.id"
            :timestamp="fmt(log.created_at)"
            :type="log.action.includes('结案') ? 'success' : log.action.includes('驳回') ? 'danger' : 'primary'"
          >
            <el-tag size="small" effect="plain">{{ log.action }}</el-tag>
            <span style="margin-left:8px">{{ log.detail }}</span>
            <span style="color:#909399;font-size:12px;margin-left:8px">— {{ log.operator || '系统' }}</span>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </div>

    <!-- 核对对话框 -->
    <el-dialog v-model="checkDialog" title="逐件核对" width="560px">
      <div v-if="checkTarget" style="margin-bottom:10px">
        <b>{{ checkTarget.snapshot_accession_no }} {{ checkTarget.snapshot_name }}</b>
        <div style="font-size:12px;color:#909399">账面位置:{{ checkTarget.snapshot_location_name || '—' }}</div>
      </div>
      <el-form :model="checkForm" label-width="96px">
        <el-form-item label="盘点结果">
          <el-radio-group v-model="checkForm.result">
            <el-radio-button v-for="r in RESULT_TYPES" :key="r.value" :value="r.value" :label="r.value">
              {{ r.value }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="checkForm.result === '错位'" label="实物位置">
          <el-select v-model="checkForm.actual_location_id" filterable style="width:100%" placeholder="选择实物实际所在库位">
            <el-option v-for="l in locations" :key="l.id" :label="`${l.code} ${l.name}`" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="checkForm.result === '损坏'" label="损坏/病害">
          <el-input v-model="checkForm.condition_note" type="textarea" :rows="2" placeholder="描述残损部位、程度" />
        </el-form-item>
        <el-form-item v-if="checkForm.result === '盘亏'" label="备注">
          <el-input v-model="checkForm.condition_note" type="textarea" :rows="2" placeholder="查找经过、可能原因" />
        </el-form-item>
        <el-form-item label="盘点人">
          <el-input v-model="checkForm.checker" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="checkDialog = false">取消</el-button>
        <el-button type="primary" @click="submitCheck">保存核对</el-button>
      </template>
    </el-dialog>

    <!-- 账外盘盈 -->
    <el-dialog v-model="surplusDialog" title="登记账外实物(盘盈)" width="520px">
      <el-form :model="surplusForm" label-width="96px">
        <el-form-item label="实物名称" required>
          <el-input v-model="surplusForm.name" placeholder="对账外实物的描述,建档审批时补全正式信息" />
        </el-form-item>
        <el-form-item label="发现位置">
          <el-select v-model="surplusForm.actual_location_id" filterable style="width:100%">
            <el-option v-for="l in locations" :key="l.id" :label="`${l.code} ${l.name}`" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="盘点人">
          <el-input v-model="surplusForm.checker" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="surplusDialog = false">取消</el-button>
        <el-button type="primary" @click="submitSurplus">登记盘盈</el-button>
      </template>
    </el-dialog>

    <!-- 调整申请 -->
    <el-dialog v-model="adjustDialog" title="差异调整申请(批准前不改动正式档案)" width="600px">
      <el-form :model="adjustForm" label-width="100px">
        <el-form-item label="调整类型">
          <el-select v-model="adjustForm.adjust_type" style="width:100%" @change="onAdjustTypeChange">
            <el-option v-for="o in applyOptions(adjustTarget)" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>

        <template v-if="adjustForm.adjust_type === '移库更正'">
          <el-form-item label="目标库位">
            <el-select v-model="adjustForm.payload.to_location_id" filterable style="width:100%">
              <el-option v-for="l in locations" :key="l.id" :label="`${l.code} ${l.name}`" :value="l.id" />
            </el-select>
          </el-form-item>
        </template>

        <template v-else-if="adjustForm.adjust_type === '送修登记'">
          <el-form-item label="修复项目">
            <el-input v-model="adjustForm.payload.project_name" placeholder="修复项目名称" />
          </el-form-item>
          <el-form-item label="修复师">
            <el-input v-model="adjustForm.payload.restorer" />
          </el-form-item>
          <el-form-item label="修复方案">
            <el-input v-model="adjustForm.payload.plan" type="textarea" :rows="2" />
          </el-form-item>
        </template>

        <template v-else-if="adjustForm.adjust_type === '档案更正'">
          <el-form-item v-for="f in ['name', 'dynasty', 'material', 'dimension', 'grade', 'description']"
            :key="f" :label="({ name: '名称', dynasty: '年代', material: '材质', dimension: '尺寸', grade: '等级', description: '描述' })[f]">
            <el-input v-model="adjustForm.payload.fields[f]" :placeholder="`留空表示不修改 ${f}`" />
          </el-form-item>
        </template>

        <template v-else-if="adjustForm.adjust_type === '状态处理' && adjustForm.payload.action === 'gain'">
          <el-alert type="info" :closable="false" style="margin-bottom:10px"
            title="批准后将自动建立藏品档案、登记盘盈入库台账并纳入总账" />
          <el-form-item label="总登记号" required>
            <el-input v-model="adjustForm.payload.accession_no" />
          </el-form-item>
          <el-form-item label="名称">
            <el-input v-model="adjustForm.payload.name" />
          </el-form-item>
          <el-row :gutter="10">
            <el-col :span="12">
              <el-form-item label="类别"><el-input v-model="adjustForm.payload.category" /></el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="等级"><el-input v-model="adjustForm.payload.grade" /></el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="入库位置">
            <el-select v-model="adjustForm.payload.location_id" filterable style="width:100%">
              <el-option v-for="l in locations" :key="l.id" :label="`${l.code} ${l.name}`" :value="l.id" />
            </el-select>
          </el-form-item>
        </template>
        <el-alert v-else-if="adjustForm.adjust_type === '状态处理' && adjustForm.payload.action === 'loss'"
          type="warning" :closable="false" style="margin-bottom:10px"
          title="批准后将登记盘亏销账台账,藏品转为出库中(账销案存),禁止常规流转" />

        <el-form-item label="申请理由">
          <el-input v-model="adjustForm.reason" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="申请人">
          <el-input v-model="adjustForm.applicant" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="adjustDialog = false">取消</el-button>
        <el-button type="primary" @click="submitAdjust">提交申请</el-button>
      </template>
    </el-dialog>

    <!-- 结案 -->
    <el-dialog v-model="completeDialog" title="盘点结案" width="520px">
      <el-alert type="success" :closable="false" style="margin-bottom:12px"
        :title="`共 ${task.total_count} 件,差异 ${task.diff_count} 条,待审批调整 ${task.pending_adjustments} 项`" />
      <el-input v-model="completeForm.summary" type="textarea" :rows="3"
        :placeholder="blockers.length === 0 && task.diff_count ? '请注明差异处置结论(无已批准调整的差异必填)' : '结案总结(可选)'" />
      <template #footer>
        <el-button @click="completeDialog = false">取消</el-button>
        <el-button type="success" @click="submitComplete">确认结案</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.head .el-button {
  padding-left: 0;
}
.stats .mini-title {
  font-size: 13px;
  color: #909399;
  margin-bottom: 6px;
}
.overdue {
  color: #c0392b;
}
</style>
