<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { inventoryApi, locationApi } from '../api'

const route = useRoute()
const router = useRouter()
const taskId = Number(route.params.id)

const task = ref(null)
const loading = ref(false)
const locations = ref([])
const activeTab = ref('全部')

const isActive = computed(() => task.value?.status === '进行中')

const resultTag = {
  未盘: 'info',
  正常: 'success',
  错位: 'warning',
  损坏: 'danger',
  盘亏: 'danger',
  盘盈: 'warning',
}
const reviewTag = { 无需复核: 'info', 待复核: 'warning', 已复核: 'success' }
const adjustTag = { 待审批: 'warning', 已执行: 'success', 已驳回: 'info' }

const filteredItems = computed(() => {
  const items = task.value?.items || []
  if (activeTab.value === '未盘') return items.filter((i) => i.result === '未盘')
  if (activeTab.value === '差异') return items.filter((i) => i.result !== '未盘' && i.result !== '正常')
  if (activeTab.value === '待复核') return items.filter((i) => i.review_status === '待复核')
  return items
})

const allAdjustments = computed(() => {
  const list = []
  for (const it of task.value?.items || []) {
    for (const a of it.adjustments || []) {
      list.push({ ...a, accession_no: it.accession_no, collection_name: it.collection_name })
    }
  }
  return list.sort((a, b) => (a.status === '待审批' ? -1 : 1) - (b.status === '待审批' ? -1 : 1) || b.id - a.id)
})

async function load() {
  loading.value = true
  try {
    task.value = await inventoryApi.getTask(taskId)
  } finally {
    loading.value = false
  }
}

// ---------- 扫描 / 人工登记 ----------
const scanForm = reactive({
  accession_no: '',
  actual_location_id: null,
  damaged: false,
  condition_note: '',
  checker: localStorage.getItem('inv_checker') || '',
})
const scanResult = ref(null)

async function submitScan() {
  if (!scanForm.accession_no.trim()) return ElMessage.warning('请扫描或输入总登记号')
  if (!scanForm.checker.trim()) return ElMessage.warning('请填写盘点人')
  localStorage.setItem('inv_checker', scanForm.checker)
  const item = await inventoryApi.scan(taskId, {
    accession_no: scanForm.accession_no,
    actual_location_id: scanForm.actual_location_id,
    damaged: scanForm.damaged,
    condition_note: scanForm.condition_note || null,
    checker: scanForm.checker,
  })
  scanResult.value = item
  if (item.result === '正常') ElMessage.success(`${item.accession_no} 核对正常`)
  else ElMessage.warning(`${item.accession_no} 登记为「${item.result}」,待复核`)
  scanForm.accession_no = ''
  scanForm.condition_note = ''
  scanForm.damaged = false
  load()
}

const checkDialog = ref(false)
const checkTarget = ref(null)
const checkForm = reactive({ result: '盘亏', actual_location_id: null, condition_note: '', checker: '' })

function openCheck(row) {
  checkTarget.value = row
  Object.assign(checkForm, {
    result: '盘亏',
    actual_location_id: null,
    condition_note: '',
    checker: scanForm.checker,
  })
  checkDialog.value = true
}

async function submitCheck() {
  if (!checkForm.checker.trim()) return ElMessage.warning('请填写盘点人')
  localStorage.setItem('inv_checker', checkForm.checker)
  await inventoryApi.checkItem(checkTarget.value.id, {
    result: checkForm.result,
    actual_location_id: checkForm.actual_location_id,
    condition_note: checkForm.condition_note || null,
    checker: checkForm.checker,
  })
  ElMessage.success('盘点结果已登记')
  checkDialog.value = false
  load()
}

// ---------- 复核 ----------
const reviewDialog = ref(false)
const reviewTarget = ref(null)
const reviewForm = reactive({ approve: true, reviewer: '', note: '' })

function openReview(row) {
  reviewTarget.value = row
  Object.assign(reviewForm, { approve: true, reviewer: '', note: '' })
  reviewDialog.value = true
}

async function submitReview() {
  if (!reviewForm.reviewer.trim()) return ElMessage.warning('请填写复核人')
  await inventoryApi.reviewItem(reviewTarget.value.id, {
    approve: reviewForm.approve,
    reviewer: reviewForm.reviewer,
    note: reviewForm.note || null,
  })
  ElMessage.success(reviewForm.approve ? '复核已通过' : '已退回重盘')
  reviewDialog.value = false
  load()
}

// ---------- 调整申请 ----------
const adjustDialog = ref(false)
const adjustTarget = ref(null)
const adjustForm = reactive({ adjust_type: '', to_location_id: null, to_status: '', reason: '', applicant: '' })

const suggestedAdjust = {
  错位: '变更位置',
  盘盈: '变更位置',
  盘亏: '状态变更',
  损坏: '损坏登记',
}

function openAdjust(row) {
  adjustTarget.value = row
  Object.assign(adjustForm, {
    adjust_type: suggestedAdjust[row.result] || '变更位置',
    to_location_id: row.actual_location_id,
    to_status: row.result === '盘亏' ? '盘亏' : '',
    reason: '',
    applicant: scanForm.checker,
  })
  adjustDialog.value = true
}

async function submitAdjust() {
  if (!adjustForm.applicant.trim()) return ElMessage.warning('请填写申请人')
  await inventoryApi.createAdjustment(adjustTarget.value.id, {
    adjust_type: adjustForm.adjust_type,
    to_location_id: adjustForm.adjust_type === '变更位置' ? adjustForm.to_location_id : null,
    to_status: adjustForm.adjust_type === '状态变更' ? adjustForm.to_status : null,
    reason: adjustForm.reason || null,
    applicant: adjustForm.applicant,
  })
  ElMessage.success('调整申请已提交,待审批执行后才会改写正式档案')
  adjustDialog.value = false
  load()
}

// ---------- 调整审批 ----------
const processDialog = ref(false)
const processTarget = ref(null)
const processForm = reactive({ action: 'approve', processor: '', note: '' })

function openProcess(row, action) {
  processTarget.value = row
  Object.assign(processForm, { action, processor: '', note: '' })
  processDialog.value = true
}

async function submitProcess() {
  if (!processForm.processor.trim()) return ElMessage.warning('请填写审批人')
  const api = processForm.action === 'approve' ? inventoryApi.approveAdjustment : inventoryApi.rejectAdjustment
  await api(processTarget.value.id, {
    processor: processForm.processor,
    note: processForm.note || null,
  })
  ElMessage.success(processForm.action === 'approve' ? '调整已执行,正式档案已更新' : '申请已驳回')
  processDialog.value = false
  load()
}

// ---------- 痕迹 ----------
const traceDrawer = ref(false)
const traceTarget = ref(null)
function openTrace(row) {
  traceTarget.value = row
  traceDrawer.value = true
}

// ---------- 结案 / 取消 ----------
async function closeTask() {
  try {
    const { value } = await ElMessageBox.prompt(
      '结案前请确认:全部藏品已盘点、差异已复核、调整申请已处理。结案后任务归档,不可再登记。',
      `结案 ${task.value.code}`,
      {
        confirmButtonText: '确认结案',
        cancelButtonText: '再想想',
        inputPlaceholder: '结案人姓名',
        inputValidator: (v) => (v && v.trim() ? true : '请填写结案人'),
      }
    )
    await inventoryApi.closeTask(taskId, { closed_by: value.trim() })
    ElMessage.success('任务已结案,盘点结果归档可溯')
    load()
  } catch (e) {
    /* 用户取消 */
  }
}

async function cancelTask() {
  try {
    await ElMessageBox.confirm(
      '取消后任务不再占用藏品,已登记数据保留备查。确定取消该盘点任务?',
      '取消任务',
      { type: 'warning', confirmButtonText: '确定取消', cancelButtonText: '返回' }
    )
    await inventoryApi.cancelTask(taskId)
    ElMessage.success('任务已取消')
    load()
  } catch (e) {
    /* 用户取消 */
  }
}

function fmtTime(t) {
  return t ? t.replace('T', ' ').slice(0, 16) : '—'
}

onMounted(async () => {
  locations.value = await locationApi.list()
  await load()
  if (task.value?.scope_type === '库房') scanForm.actual_location_id = task.value.scope_location_id
})
</script>

<template>
  <div class="page-container" v-loading="loading">
    <template v-if="task">
      <h2 class="page-title">
        <el-link :underline="false" @click="router.push('/inventories')" style="font-size:20px">
          <el-icon style="vertical-align:-2px"><Back /></el-icon>
        </el-link>
        {{ task.code }} {{ task.title }}
        <el-tag
          :type="{ 进行中: 'primary', 已结案: 'success', 已取消: 'info' }[task.status]"
          effect="dark"
          size="small"
          style="vertical-align: 3px"
        >
          {{ task.status }}
        </el-tag>
      </h2>
      <p class="page-sub">
        范围:{{ task.scope_label }} · 发起人:{{ task.initiator }} · 截止:{{ task.deadline }}
        <template v-if="task.status === '进行中'">
          ·
          <span :style="{ color: task.days_remaining < 0 ? '#c0392b' : '#606266' }">
            {{ task.days_remaining < 0 ? `已逾期 ${-task.days_remaining} 天` : `剩余 ${task.days_remaining} 天` }}
          </span>
        </template>
        <template v-if="task.closed_by"> · 结案人:{{ task.closed_by }}({{ fmtTime(task.closed_at) }})</template>
      </p>

      <!-- 进度统计 -->
      <el-row :gutter="12" class="stat-row">
        <el-col :span="4"><el-card shadow="never" class="mini-stat"><div class="num">{{ task.checked }}/{{ task.total }}</div><div class="lbl">已盘 / 总数</div></el-card></el-col>
        <el-col :span="4"><el-card shadow="never" class="mini-stat"><div class="num ok">{{ task.result_counts['正常'] || 0 }}</div><div class="lbl">正常</div></el-card></el-col>
        <el-col :span="4"><el-card shadow="never" class="mini-stat"><div class="num warn">{{ task.result_counts['错位'] || 0 }}</div><div class="lbl">错位</div></el-card></el-col>
        <el-col :span="4"><el-card shadow="never" class="mini-stat"><div class="num bad">{{ task.result_counts['损坏'] || 0 }}</div><div class="lbl">损坏</div></el-card></el-col>
        <el-col :span="4"><el-card shadow="never" class="mini-stat"><div class="num bad">{{ (task.result_counts['盘亏'] || 0) }}</div><div class="lbl">盘亏</div></el-card></el-col>
        <el-col :span="4"><el-card shadow="never" class="mini-stat"><div class="num warn">{{ task.result_counts['盘盈'] || 0 }}</div><div class="lbl">盘盈</div></el-card></el-col>
      </el-row>

      <!-- 结案汇总 -->
      <el-card v-if="task.status === '已结案' && task.summary" shadow="never" style="margin-bottom:12px">
        <el-descriptions :column="3" border size="small" title="结案汇总">
          <el-descriptions-item label="盘点人员">{{ (task.summary['盘点人员'] || []).join('、') || '—' }}</el-descriptions-item>
          <el-descriptions-item label="调整已执行">{{ task.summary['调整已执行'] }} 笔</el-descriptions-item>
          <el-descriptions-item label="调整已驳回">{{ task.summary['调整已驳回'] }} 笔</el-descriptions-item>
          <el-descriptions-item label="结案人">{{ task.closed_by }}</el-descriptions-item>
          <el-descriptions-item label="结案时间">{{ fmtTime(task.closed_at) }}</el-descriptions-item>
          <el-descriptions-item label="任务备注">{{ task.remark || '—' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 扫描登记 -->
      <el-card v-if="isActive" shadow="never" style="margin-bottom:12px">
        <div class="scan-bar">
          <el-input
            v-model="scanForm.accession_no"
            placeholder="扫描或输入总登记号,回车登记"
            style="width: 260px"
            clearable
            @keyup.enter="submitScan"
          >
            <template #prefix><el-icon><Aim /></el-icon></template>
          </el-input>
          <el-select
            v-model="scanForm.actual_location_id"
            placeholder="实物位置(默认账面位置)"
            clearable
            filterable
            style="width: 220px"
          >
            <el-option v-for="l in locations" :key="l.id" :label="`${l.code} ${l.name}`" :value="l.id" />
          </el-select>
          <el-radio-group v-model="scanForm.damaged">
            <el-radio-button :label="false">外观完好</el-radio-button>
            <el-radio-button :label="true">发现损坏</el-radio-button>
          </el-radio-group>
          <el-input v-model="scanForm.condition_note" placeholder="保管/完残情况说明" style="width: 220px" />
          <el-input v-model="scanForm.checker" placeholder="盘点人" style="width: 130px" />
          <el-button type="primary" @click="submitScan">登记</el-button>
        </div>
        <div v-if="scanResult" class="scan-result">
          上一笔:{{ scanResult.accession_no }} {{ scanResult.collection_name }} →
          <el-tag :type="resultTag[scanResult.result]" size="small" effect="dark">{{ scanResult.result }}</el-tag>
          <span v-if="scanResult.result !== '正常'" style="color:#e6a23c"> 已生成差异,等待复核</span>
        </div>
      </el-card>

      <!-- 明细 -->
      <el-card shadow="never">
        <div class="toolbar">
          <el-radio-group v-model="activeTab">
            <el-radio-button label="全部">全部 {{ task.total }}</el-radio-button>
            <el-radio-button label="未盘">未盘 {{ task.total - task.checked }}</el-radio-button>
            <el-radio-button label="差异">差异 {{ task.diff_count }}</el-radio-button>
            <el-radio-button label="待复核">待复核 {{ task.pending_review }}</el-radio-button>
          </el-radio-group>
          <div class="spacer"></div>
          <template v-if="isActive">
            <el-button type="warning" plain :icon="'CircleClose'" @click="cancelTask">取消任务</el-button>
            <el-button type="success" :icon="'CircleCheck'" @click="closeTask">结案归档</el-button>
          </template>
        </div>

        <el-table :data="filteredItems" stripe>
          <el-table-column label="藏品" min-width="200">
            <template #default="{ row }">
              <el-link type="primary" @click="router.push(`/collections/${row.collection_id}`)">
                {{ row.accession_no }} {{ row.collection_name }}
              </el-link>
              <div style="font-size:12px;color:#909399">{{ row.category }}<span v-if="row.grade"> · {{ row.grade }}</span></div>
            </template>
          </el-table-column>
          <el-table-column label="账面" width="150">
            <template #default="{ row }">
              <div>{{ row.book_location_name || '库外' }}</div>
              <div style="font-size:12px;color:#909399">{{ row.book_status }}</div>
            </template>
          </el-table-column>
          <el-table-column label="实物位置" width="140">
            <template #default="{ row }">
              <span v-if="row.result === '盘亏'" style="color:#c0392b">未见实物</span>
              <span v-else>{{ row.actual_location_name || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="结果" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="resultTag[row.result]" size="small" :effect="row.result === '未盘' ? 'plain' : 'dark'">
                {{ row.result }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="condition_note" label="保管/完残情况" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.condition_note || '—' }}</template>
          </el-table-column>
          <el-table-column label="盘点人" width="140">
            <template #default="{ row }">
              <div>{{ row.checked_by || '—' }}</div>
              <div style="font-size:12px;color:#909399">{{ fmtTime(row.checked_at) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="复核" width="130">
            <template #default="{ row }">
              <el-tag :type="reviewTag[row.review_status]" size="small" effect="plain">
                {{ row.review_status }}
              </el-tag>
              <div v-if="row.reviewed_by && row.review_status === '已复核'" style="font-size:12px;color:#909399">
                {{ row.reviewed_by }}
              </div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <template v-if="isActive">
                <el-button v-if="row.result === '未盘'" link type="primary" size="small" @click="openCheck(row)">
                  人工登记
                </el-button>
                <el-button v-if="row.review_status === '待复核'" link type="warning" size="small" @click="openReview(row)">
                  复核
                </el-button>
                <el-button
                  v-if="row.review_status === '已复核' && !row.adjustments.some((a) => a.status === '待审批')"
                  link type="danger" size="small" @click="openAdjust(row)"
                >
                  提请调整
                </el-button>
              </template>
              <el-button link size="small" @click="openTrace(row)">痕迹</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 调整审批 -->
      <el-card v-if="allAdjustments.length" shadow="never" style="margin-top:12px">
        <div class="toolbar"><b>调整申请</b><span class="page-sub" style="margin:0">审批通过后才会改写正式藏品档案,并登记流转台账</span></div>
        <el-table :data="allAdjustments" stripe>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="adjustTag[row.status]" size="small" effect="dark">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="藏品" min-width="180">
            <template #default="{ row }">{{ row.accession_no }} {{ row.collection_name }}</template>
          </el-table-column>
          <el-table-column prop="adjust_type" label="调整类型" width="100" />
          <el-table-column label="调整内容" min-width="170">
            <template #default="{ row }">
              <span v-if="row.adjust_type === '变更位置'">→ {{ row.to_location_name }}</span>
              <span v-else-if="row.adjust_type === '状态变更'">→ {{ row.to_status }}</span>
              <span v-else>损坏情况登记入台账</span>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="申请理由" min-width="180" show-overflow-tooltip />
          <el-table-column label="申请人" width="150">
            <template #default="{ row }">
              <div>{{ row.applicant }}</div>
              <div style="font-size:12px;color:#909399">{{ fmtTime(row.created_at) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="审批" width="150">
            <template #default="{ row }">
              <template v-if="row.processed_by">
                <div>{{ row.processed_by }}</div>
                <div style="font-size:12px;color:#909399">{{ fmtTime(row.processed_at) }}</div>
              </template>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isActive" label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <template v-if="row.status === '待审批'">
                <el-button link type="success" size="small" @click="openProcess(row, 'approve')">批准执行</el-button>
                <el-button link type="danger" size="small" @click="openProcess(row, 'reject')">驳回</el-button>
              </template>
              <span v-else style="color:#c2c7cc">—</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <!-- 人工登记 -->
    <el-dialog v-model="checkDialog" title="人工登记盘点结果" width="480px">
      <p v-if="checkTarget" style="margin-top:0">
        「{{ checkTarget.accession_no }} {{ checkTarget.collection_name }}」账面位置:{{ checkTarget.book_location_name || '库外' }}
      </p>
      <el-form label-width="92px">
        <el-form-item label="盘点结果">
          <el-radio-group v-model="checkForm.result">
            <el-radio-button label="正常">正常</el-radio-button>
            <el-radio-button label="错位">错位</el-radio-button>
            <el-radio-button label="损坏">损坏</el-radio-button>
            <el-radio-button label="盘亏">盘亏</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="checkForm.result === '错位' || checkForm.result === '损坏'" label="实物位置">
          <el-select v-model="checkForm.actual_location_id" filterable style="width:100%" placeholder="错位时必选">
            <el-option v-for="l in locations" :key="l.id" :label="`${l.code} ${l.name}`" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="情况说明">
          <el-input v-model="checkForm.condition_note" type="textarea" :rows="2" placeholder="完残状况、保管信息等" />
        </el-form-item>
        <el-form-item label="盘点人">
          <el-input v-model="checkForm.checker" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="checkDialog = false">取消</el-button>
        <el-button type="primary" @click="submitCheck">登记</el-button>
      </template>
    </el-dialog>

    <!-- 复核 -->
    <el-dialog v-model="reviewDialog" title="差异复核" width="480px">
      <template v-if="reviewTarget">
        <el-alert type="warning" :closable="false" style="margin-bottom:12px">
          <p style="margin:0">
            {{ reviewTarget.accession_no }} {{ reviewTarget.collection_name }} 登记为「{{ reviewTarget.result }}」
          </p>
          <p style="margin:4px 0 0;font-size:12px">
            盘点人:{{ reviewTarget.checked_by }} · {{ reviewTarget.condition_note || '无情况说明' }}
          </p>
        </el-alert>
        <el-form label-width="92px">
          <el-form-item label="复核结论">
            <el-radio-group v-model="reviewForm.approve">
              <el-radio-button :label="true">复核通过</el-radio-button>
              <el-radio-button :label="false">退回重盘</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="复核意见">
            <el-input v-model="reviewForm.note" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="复核人">
            <el-input v-model="reviewForm.reviewer" />
          </el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="reviewDialog = false">取消</el-button>
        <el-button :type="reviewForm.approve ? 'success' : 'warning'" @click="submitReview">
          {{ reviewForm.approve ? '确认通过' : '确认退回' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 提请调整 -->
    <el-dialog v-model="adjustDialog" title="提请档案调整" width="500px">
      <template v-if="adjustTarget">
        <p style="margin-top:0">
          「{{ adjustTarget.accession_no }} {{ adjustTarget.collection_name }}」差异:{{ adjustTarget.result }}
        </p>
        <el-form label-width="92px">
          <el-form-item label="调整类型">
            <el-radio-group v-model="adjustForm.adjust_type">
              <el-radio-button label="变更位置">变更位置</el-radio-button>
              <el-radio-button label="状态变更">状态变更</el-radio-button>
              <el-radio-button label="损坏登记">损坏登记</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="adjustForm.adjust_type === '变更位置'" label="目标位置">
            <el-select v-model="adjustForm.to_location_id" filterable style="width:100%">
              <el-option v-for="l in locations" :key="l.id" :label="`${l.code} ${l.name}`" :value="l.id" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="adjustForm.adjust_type === '状态变更'" label="目标状态">
            <el-select v-model="adjustForm.to_status" style="width:100%">
              <el-option label="盘亏" value="盘亏" />
              <el-option label="在库" value="在库" />
              <el-option label="出库中" value="出库中" />
            </el-select>
          </el-form-item>
          <el-form-item label="申请理由">
            <el-input v-model="adjustForm.reason" type="textarea" :rows="2" placeholder="说明差异原因与调整依据" />
          </el-form-item>
          <el-form-item label="申请人">
            <el-input v-model="adjustForm.applicant" />
          </el-form-item>
        </el-form>
        <el-alert type="info" :closable="false" show-icon title="申请经审批通过后才会改写正式藏品档案,并自动登记流转台账。" />
      </template>
      <template #footer>
        <el-button @click="adjustDialog = false">取消</el-button>
        <el-button type="primary" @click="submitAdjust">提交申请</el-button>
      </template>
    </el-dialog>

    <!-- 调整审批 -->
    <el-dialog v-model="processDialog" :title="processForm.action === 'approve' ? '批准并执行调整' : '驳回调整申请'" width="440px">
      <template v-if="processTarget">
        <p style="margin-top:0">
          {{ processTarget.accession_no }} {{ processTarget.collection_name }} · {{ processTarget.adjust_type }}
        </p>
        <el-alert
          v-if="processForm.action === 'approve'"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom:12px"
          title="批准后系统将立即改写正式藏品档案并登记流转台账。"
        />
        <el-form label-width="92px">
          <el-form-item label="审批意见">
            <el-input v-model="processForm.note" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="审批人">
            <el-input v-model="processForm.processor" />
          </el-form-item>
        </el-form>
      </template>
      <template #footer>
        <el-button @click="processDialog = false">取消</el-button>
        <el-button :type="processForm.action === 'approve' ? 'success' : 'danger'" @click="submitProcess">
          {{ processForm.action === 'approve' ? '批准执行' : '确认驳回' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 处理痕迹 -->
    <el-drawer v-model="traceDrawer" title="处理痕迹" size="420px">
      <template v-if="traceTarget">
        <h4 style="margin:0 0 4px">{{ traceTarget.accession_no }} {{ traceTarget.collection_name }}</h4>
        <p style="margin:0 0 16px;color:#909399;font-size:13px">
          账面:{{ traceTarget.book_location_name || '库外' }} / {{ traceTarget.book_status }} · 当前结果:{{ traceTarget.result }}
        </p>
        <el-timeline v-if="traceTarget.logs?.length">
          <el-timeline-item
            v-for="(log, i) in traceTarget.logs"
            :key="i"
            :timestamp="`${log.time} · ${log.actor}`"
            :type="log.action.includes('退回') || log.action.includes('驳回') ? 'danger' : log.action.includes('调整') ? 'warning' : 'primary'"
          >
            <b>{{ log.action }}</b>
            <div v-if="log.note" style="color:#606266;font-size:13px;margin-top:2px">{{ log.note }}</div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="尚未盘点,暂无处理痕迹" :image-size="80" />
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.stat-row {
  margin-bottom: 12px;
}
.mini-stat :deep(.el-card__body) {
  padding: 12px;
  text-align: center;
}
.mini-stat .num {
  font-size: 22px;
  font-weight: 700;
  color: #1f2d3d;
}
.mini-stat .num.ok {
  color: #529b2e;
}
.mini-stat .num.warn {
  color: #b88230;
}
.mini-stat .num.bad {
  color: #c45656;
}
.mini-stat .lbl {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}
.scan-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.scan-result {
  margin-top: 10px;
  font-size: 13px;
  color: #606266;
}
</style>
