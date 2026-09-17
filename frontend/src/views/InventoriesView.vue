<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { inventoryApi } from '../api'

const router = useRouter()
const rows = ref([])
const loading = ref(false)
const statusFilter = ref('')
const meta = ref({ locations: [], categories: [], grades: [] })

const createDialog = ref(false)
const formRef = ref(null)
const preview = ref(null)
const previewLoading = ref(false)
const form = reactive({
  title: '',
  scope_type: '库房',
  scope_value: '',
  location_id: null,
  librarian: '',
  checker: '',
  start_date: '',
  due_date: '',
  remark: '',
})
const rules = {
  title: [{ required: true, message: '请输入任务名称' }],
  scope_value: [{ required: true, message: '请选择盘点范围' }],
  librarian: [{ required: true, message: '请输入发起馆员' }],
  due_date: [{ required: true, message: '请选择截止日期' }],
}

const STATUS_TABS = [
  { label: '全部', value: '' },
  { label: '进行中', value: '进行中' },
  { label: '待盘点', value: '待盘点' },
  { label: '待复核', value: '待复核' },
  { label: '调整审批中', value: '调整审批中' },
  { label: '已结案', value: '已结案' },
  { label: '已撤销', value: '已撤销' },
]

async function load() {
  loading.value = true
  try {
    rows.value = await inventoryApi.list({ status: statusFilter.value || undefined })
  } finally {
    loading.value = false
  }
}

async function openCreate() {
  Object.assign(form, {
    title: '', scope_type: '库房', scope_value: '', location_id: null,
    librarian: '', checker: '', start_date: '', due_date: '', remark: '',
  })
  preview.value = null
  createDialog.value = true
}

function scopeOptions() {
  if (form.scope_type === '库房') return meta.value.locations.map((l) => l.label)
  if (form.scope_type === '类别') return meta.value.categories
  return meta.value.grades
}

async function loadPreview() {
  if (!form.scope_value) {
    preview.value = null
    return
  }
  previewLoading.value = true
  try {
    const params = { scope_type: form.scope_type, scope_value: form.scope_value }
    if (form.scope_type === '库房' && form.location_id) params.location_id = form.location_id
    preview.value = await inventoryApi.scopePreview(params)
  } finally {
    previewLoading.value = false
  }
}

function onScopeChange() {
  form.scope_value = ''
  form.location_id = null
  preview.value = null
}

function onScopeValueChange(v) {
  if (form.scope_type === '库房') {
    const loc = meta.value.locations.find((l) => l.label === v)
    form.location_id = loc ? loc.id : null
  }
  loadPreview()
}

async function submitCreate() {
  await formRef.value.validate()
  if (preview.value && preview.value.occupied > 0) {
    ElMessage.error(`范围内有 ${preview.value.occupied} 件藏品正被其他盘点任务占用,无法发起`)
    return
  }
  const payload = {
    title: form.title,
    scope_type: form.scope_type,
    scope_value: form.scope_value,
    location_id: form.location_id,
    librarian: form.librarian,
    checker: form.checker || null,
    start_date: form.start_date || null,
    due_date: form.due_date,
    remark: form.remark || null,
  }
  const task = await inventoryApi.create(payload)
  ElMessage.success(`盘点任务已发起,共 ${task.total_count} 件藏品纳入盘点`)
  createDialog.value = false
  load()
}

function statusTag(row) {
  return {
    待盘点: 'info',
    盘点中: 'primary',
    待复核: 'warning',
    调整审批中: 'warning',
    已结案: 'success',
    已撤销: 'info',
  }[row.status] || 'info'
}

function progress(row) {
  if (!row.total_count) return 0
  return Math.round((row.checked_count / row.total_count) * 100)
}

onMounted(async () => {
  meta.value = await inventoryApi.meta()
  load()
})
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">馆藏盘点</h2>
    <p class="page-sub">按库房 / 类别 / 等级发起带截止日期的盘点,逐件核对账实并闭环差异</p>

    <el-card shadow="never">
      <div class="toolbar">
        <el-radio-group v-model="statusFilter" @change="load">
          <el-radio-button v-for="t in STATUS_TABS" :key="t.value" :label="t.value">
            {{ t.label }}
          </el-radio-button>
        </el-radio-group>
        <div class="spacer"></div>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">发起盘点</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="任务" min-width="240">
          <template #default="{ row }">
            <el-link type="primary" @click="router.push(`/inventories/${row.id}`)">
              {{ row.title }}
            </el-link>
            <div style="font-size:12px;color:#909399;margin-top:2px">
              #{{ row.id }} · {{ row.scope_type }}「{{ row.scope_value }}」
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTag(row)" size="small" effect="dark">{{ row.status }}</el-tag>
            <el-tag v-if="row.overdue" type="danger" size="small" effect="plain" style="margin-left:4px">
              已逾期
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="盘点进度" width="190">
          <template #default="{ row }">
            <el-progress :percentage="progress(row)" :stroke-width="14"
              :status="row.pending_count === 0 && row.status !== '已撤销' ? 'success' : ''" />
            <div style="font-size:11px;color:#909399">
              已盘 {{ row.checked_count }} / {{ row.total_count }}
              <template v-if="row.diff_count"> · 差异 {{ row.diff_count }}</template>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="librarian" label="发起人" width="110" />
        <el-table-column prop="checker" label="盘点员" width="100">
          <template #default="{ row }">{{ row.checker || '—' }}</template>
        </el-table-column>
        <el-table-column label="截止日期" width="130">
          <template #default="{ row }">
            <span :class="{ overdue: row.overdue, soon: row.days_remaining != null && row.days_remaining >= 0 && row.days_remaining <= 5 }">
              {{ row.due_date }}
            </span>
            <div v-if="row.status !== '已结案' && row.status !== '已撤销'" style="font-size:11px;color:#909399">
              {{ row.overdue ? `已超 ${-row.days_remaining} 天` : `剩 ${row.days_remaining} 天` }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="待办" width="150">
          <template #default="{ row }">
            <el-tag v-if="row.pending_adjustments" type="danger" size="small" effect="plain">
              待审批调整 {{ row.pending_adjustments }}
            </el-tag>
            <el-tag v-else-if="row.diff_count > row.reviewed_count && row.status !== '已结案' && row.status !== '已撤销'"
              type="warning" size="small" effect="plain">
              差异待复核
            </el-tag>
            <span v-else style="color:#c2c7cc">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="finished_at" label="结案时间" width="160">
          <template #default="{ row }">
            {{ row.finished_at ? row.finished_at.replace('T', ' ').slice(0, 16) : '—' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createDialog" title="发起馆藏盘点" width="620px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="任务名称" prop="title">
          <el-input v-model="form.title" placeholder="如:2026 年度陶瓷库房专项盘点" />
        </el-form-item>
        <el-row :gutter="10">
          <el-col :span="9">
            <el-form-item label="盘点范围" prop="scope_type">
              <el-select v-model="form.scope_type" style="width:100%" @change="onScopeChange">
                <el-option label="按库房" value="库房" />
                <el-option label="按类别" value="类别" />
                <el-option label="按等级" value="等级" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="15">
            <el-form-item label="范围对象" prop="scope_value">
              <el-select
                v-model="form.scope_value"
                filterable
                style="width:100%"
                placeholder="选择具体库房 / 类别 / 等级"
                @change="onScopeValueChange"
              >
                <el-option v-for="o in scopeOptions()" :key="o" :label="o" :value="o" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-alert
          v-if="preview"
          :title="`范围内共 ${preview.count} 件在账藏品`"
          :type="preview.occupied ? 'error' : 'success'"
          :closable="false"
          show-icon
          style="margin-bottom:12px"
        >
          <template #default>
            <div v-if="preview.occupied">
              {{ preview.occupied }} 件正被其他进行中的盘点任务占用,需等其结案/撤销后才能发起:
              <div v-for="cf in preview.conflicts.slice(0, 3)" :key="cf.collection_id" style="font-size:12px">
                · {{ cf.accession_no }} {{ cf.name }} → 任务 #{{ cf.task_id }}
              </div>
            </div>
            <div v-else>范围内藏品均未被占用,可以发起盘点。</div>
          </template>
        </el-alert>
        <el-row :gutter="10">
          <el-col :span="12">
            <el-form-item label="发起馆员" prop="librarian">
              <el-input v-model="form.librarian" placeholder="如:保管部·周文澜" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="盘点员">
              <el-input v-model="form.checker" placeholder="可指定,核对时也可临时填写" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="开始日期">
              <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD"
                style="width:100%" placeholder="默认今天" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="截止日期" prop="due_date">
              <el-date-picker v-model="form.due_date" type="date" value-format="YYYY-MM-DD"
                style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="任务说明">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="previewLoading" @click="submitCreate">发起并建账</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.overdue {
  color: #c0392b;
  font-weight: 700;
}
.soon {
  color: #e6a23c;
  font-weight: 600;
}
</style>
