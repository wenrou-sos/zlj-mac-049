<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { collectionApi, inventoryApi, locationApi } from '../api'

const router = useRouter()
const rows = ref([])
const loading = ref(false)
const statusFilter = ref('进行中')

const createDialog = ref(false)
const formRef = ref(null)
const locations = ref([])
const categories = ref([])
const grades = ['一级文物', '二级文物', '三级文物', '一般文物']
const form = reactive({
  title: '',
  scope_type: '库房',
  scope_location_id: null,
  scope_value: '',
  initiator: '',
  deadline: '',
  remark: '',
})
const rules = {
  title: [{ required: true, message: '请输入任务名称' }],
  scope_location_id: [{ required: true, message: '请选择库房' }],
  scope_value: [{ required: true, message: '请选择范围值' }],
  initiator: [{ required: true, message: '请输入发起人' }],
  deadline: [{ required: true, message: '请选择截止日期' }],
}

const warehouses = computed(() =>
  locations.value.filter((l) => l.location_type === '库房')
)

async function load() {
  loading.value = true
  try {
    rows.value = await inventoryApi.tasks({
      status: statusFilter.value || undefined,
    })
  } finally {
    loading.value = false
  }
}

async function openCreate() {
  Object.assign(form, {
    title: '',
    scope_type: '库房',
    scope_location_id: null,
    scope_value: '',
    initiator: '',
    deadline: '',
    remark: '',
  })
  if (!locations.value.length) locations.value = await locationApi.list()
  if (!categories.value.length) {
    const meta = await collectionApi.meta()
    categories.value = meta.categories
  }
  createDialog.value = true
}

async function submitCreate() {
  await formRef.value.validate()
  const payload = {
    title: form.title,
    scope_type: form.scope_type,
    initiator: form.initiator,
    deadline: form.deadline,
    remark: form.remark || null,
  }
  if (form.scope_type === '库房') payload.scope_location_id = form.scope_location_id
  else payload.scope_value = form.scope_value
  const task = await inventoryApi.createTask(payload)
  ElMessage.success(`盘点任务 ${task.code} 已发起,共 ${task.total} 件藏品`)
  createDialog.value = false
  load()
}

function statusTag(s) {
  return { 进行中: 'primary', 已结案: 'success', 已取消: 'info' }[s] || 'info'
}

function deadlineText(row) {
  if (row.status !== '进行中') return row.deadline
  if (row.days_remaining < 0) return `${row.deadline}(已逾期 ${-row.days_remaining} 天)`
  return `${row.deadline}(剩 ${row.days_remaining} 天)`
}

onMounted(load)
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">馆藏盘点</h2>
    <p class="page-sub">
      按库房 / 类别 / 等级发起盘点任务,逐件核对实物;差异经复核与调整审批后方可结案归档
    </p>

    <el-card shadow="never">
      <div class="toolbar">
        <el-radio-group v-model="statusFilter" @change="load">
          <el-radio-button label="进行中">进行中</el-radio-button>
          <el-radio-button label="已结案">已结案</el-radio-button>
          <el-radio-button label="已取消">已取消</el-radio-button>
          <el-radio-button label="">全部</el-radio-button>
        </el-radio-group>
        <div class="spacer"></div>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">发起盘点</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small" effect="dark">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="任务" min-width="220">
          <template #default="{ row }">
            <el-link type="primary" @click="router.push(`/inventories/${row.id}`)">
              {{ row.code }} {{ row.title }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="scope_label" label="盘点范围" min-width="170" />
        <el-table-column prop="initiator" label="发起人" width="130" />
        <el-table-column label="截止日期" width="190">
          <template #default="{ row }">
            <span
              :class="{
                overdue: row.status === '进行中' && row.days_remaining < 0,
                soon: row.status === '进行中' && row.days_remaining >= 0 && row.days_remaining <= 3,
              }"
            >
              {{ deadlineText(row) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="盘点进度" width="180">
          <template #default="{ row }">
            <el-progress
              :percentage="row.total ? Math.round((row.checked / row.total) * 100) : 0"
              :status="row.status === '已结案' ? 'success' : undefined"
            />
            <span style="font-size:12px;color:#909399">{{ row.checked }} / {{ row.total }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.diff_count" type="danger" size="small">{{ row.diff_count }}</el-tag>
            <span v-else style="color:#c2c7cc">0</span>
          </template>
        </el-table-column>
        <el-table-column label="待复核" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.pending_review" type="warning" size="small">
              {{ row.pending_review }}
            </el-tag>
            <span v-else style="color:#c2c7cc">0</span>
          </template>
        </el-table-column>
        <el-table-column label="待审批" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.pending_adjust" type="danger" size="small" effect="plain">
              {{ row.pending_adjust }}
            </el-tag>
            <span v-else style="color:#c2c7cc">0</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="router.push(`/inventories/${row.id}`)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createDialog" title="发起盘点任务" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
        <el-form-item label="任务名称" prop="title">
          <el-input v-model="form.title" placeholder="如:陶瓷珍品库季度盘点" />
        </el-form-item>
        <el-form-item label="盘点范围" prop="scope_type">
          <el-radio-group v-model="form.scope_type">
            <el-radio-button label="库房">按库房</el-radio-button>
            <el-radio-button label="类别">按类别</el-radio-button>
            <el-radio-button label="等级">按等级</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.scope_type === '库房'" label="选择库房" prop="scope_location_id">
          <el-select v-model="form.scope_location_id" filterable style="width:100%" placeholder="按账面位置圈定藏品">
            <el-option
              v-for="l in warehouses"
              :key="l.id"
              :label="`${l.code} ${l.name}(在库 ${l.collection_count} 件)`"
              :value="l.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-else-if="form.scope_type === '类别'" label="选择类别" prop="scope_value">
          <el-select v-model="form.scope_value" filterable style="width:100%">
            <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="选择等级" prop="scope_value">
          <el-select v-model="form.scope_value" style="width:100%">
            <el-option v-for="g in grades" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-row :gutter="10">
          <el-col :span="12">
            <el-form-item label="发起人" prop="initiator">
              <el-input v-model="form.initiator" placeholder="如:保管部·周文澜" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="截止日期" prop="deadline">
              <el-date-picker
                v-model="form.deadline"
                type="date"
                value-format="YYYY-MM-DD"
                :disabled-date="(d) => d.getTime() < Date.now() - 86400000"
                style="width:100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="盘点要求、重点核对事项等" />
        </el-form-item>
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="同一藏品同一时间只能被一个进行中的盘点任务占用;范围内藏品被占用时任务将无法发起。"
        />
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">发起任务</el-button>
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
