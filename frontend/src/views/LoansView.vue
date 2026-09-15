<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { collectionApi, loanApi, locationApi } from '../api'

const rows = ref([])
const loading = ref(false)
const statusFilter = ref('借出')
const quickFilter = ref('')
const locations = ref([])

const createDialog = ref(false)
const formRef = ref(null)
const collections = ref([])
const form = reactive({
  collection_id: null,
  borrowing_institution: '',
  exhibition_title: '',
  contact_person: '',
  contact_phone: '',
  loan_date: '',
  due_date: '',
  purpose: '',
  remark: '',
})
const rules = {
  collection_id: [{ required: true, message: '请选择藏品' }],
  borrowing_institution: [{ required: true, message: '请输入借入机构' }],
  due_date: [{ required: true, message: '请选择应还日期' }],
}

const returnDialog = ref(false)
const returnTarget = ref(null)
const returnForm = reactive({ return_date: '', to_location_id: null })

async function load() {
  loading.value = true
  try {
    const params = { status: statusFilter.value || undefined }
    if (quickFilter.value === 'overdue') params.overdue_only = true
    if (quickFilter.value === 'soon') params.due_within_days = 30
    rows.value = await loanApi.list(params)
  } finally {
    loading.value = false
  }
}

async function openCreate() {
  Object.assign(form, {
    collection_id: null,
    borrowing_institution: '',
    exhibition_title: '',
    contact_person: '',
    contact_phone: '',
    loan_date: '',
    due_date: '',
    purpose: '',
    remark: '',
  })
  collections.value = await collectionApi.list()
  createDialog.value = true
}

async function submitCreate() {
  await formRef.value.validate()
  await loanApi.create({ ...form, loan_date: form.loan_date || null })
  ElMessage.success('借展已登记,藏品状态更新为「借展中」')
  createDialog.value = false
  load()
}

function openReturn(row) {
  returnTarget.value = row
  returnForm.return_date = ''
  returnForm.to_location_id = null
  returnDialog.value = true
}

async function submitReturn() {
  await loanApi.return(returnTarget.value.id, {
    return_date: returnForm.return_date || null,
    to_location_id: returnForm.to_location_id,
  })
  ElMessage.success('归还已登记')
  returnDialog.value = false
  load()
}

function rowType(row) {
  if (row.status === '已逾期') return 'danger'
  if (row.status === '已归还') return 'info'
  if (row.days_remaining != null && row.days_remaining <= 30) return 'warning'
  return 'primary'
}

onMounted(async () => {
  locations.value = await locationApi.list({ location_type: '库房' })
  load()
})
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">借展跟踪</h2>
    <p class="page-sub">跟踪外借展品的借入机构、应还日期,自动标记逾期与 30 天内到期</p>

    <el-card shadow="never">
      <div class="toolbar">
        <el-radio-group v-model="statusFilter" @change="load">
          <el-radio-button label="借出">未归还</el-radio-button>
          <el-radio-button label="">全部记录</el-radio-button>
          <el-radio-button label="已归还">已归还</el-radio-button>
        </el-radio-group>
        <el-select
          v-model="quickFilter"
          placeholder="快捷视图"
          clearable
          style="width:160px"
          @change="load"
        >
          <el-option label="仅看已逾期" value="overdue" />
          <el-option label="30天内到期" value="soon" />
        </el-select>
        <div class="spacer"></div>
        <el-button type="primary" :icon="'Promotion'" @click="openCreate">登记借展</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="rowType(row)" size="small" effect="dark">{{ row.status }}</el-tag>
            <div v-if="row.status === '借出'" style="font-size:11px;color:#909399;margin-top:2px">
              剩余 {{ row.days_remaining }} 天
            </div>
            <div v-else-if="row.status === '已逾期'" style="font-size:11px;color:#c0392b;margin-top:2px">
              已超期 {{ row.days_remaining }} 天
            </div>
          </template>
        </el-table-column>
        <el-table-column label="藏品" min-width="190">
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/collections/${row.collection_id}`)">
              {{ row.accession_no }} {{ row.collection_name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="borrowing_institution" label="借入机构" min-width="180" />
        <el-table-column prop="exhibition_title" label="展览名称" min-width="170" />
        <el-table-column label="联系人" width="150">
          <template #default="{ row }">
            {{ row.contact_person || '—' }}
            <span v-if="row.contact_phone" style="color:#909399;font-size:12px">{{ row.contact_phone }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="loan_date" label="借出日期" width="110" />
        <el-table-column label="应还日期" width="120">
          <template #default="{ row }">
            <span :class="{ overdue: row.status === '已逾期', soon: row.status === '借出' && row.days_remaining <= 30 }">
              {{ row.due_date }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="return_date" label="实际归还" width="110" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status !== '已归还'"
              link
              type="success"
              size="small"
              @click="openReturn(row)"
            >
              归还
            </el-button>
            <span v-else style="color:#c2c7cc">—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createDialog" title="登记借展" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
        <el-form-item label="藏品" prop="collection_id">
          <el-select v-model="form.collection_id" filterable style="width:100%" placeholder="仅在库藏品可借展">
            <el-option
              v-for="c in collections.filter((x) => x.status === '在库')"
              :key="c.id"
              :label="`${c.accession_no} ${c.name}`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="借入机构" prop="borrowing_institution">
          <el-input v-model="form.borrowing_institution" />
        </el-form-item>
        <el-form-item label="展览名称">
          <el-input v-model="form.exhibition_title" />
        </el-form-item>
        <el-row :gutter="10">
          <el-col :span="12">
            <el-form-item label="联系人">
              <el-input v-model="form.contact_person" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系电话">
              <el-input v-model="form.contact_phone" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="借出日期">
              <el-date-picker v-model="form.loan_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="应还日期" prop="due_date">
              <el-date-picker v-model="form.due_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="借展用途">
          <el-input v-model="form.purpose" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">确认借出</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="returnDialog" title="借展归还" width="460px">
      <p>「{{ returnTarget?.collection_name }}」归还入库。</p>
      <el-form :model="returnForm" label-width="92px">
        <el-form-item label="归还日期">
          <el-date-picker v-model="returnForm.return_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="归库位置">
          <el-select v-model="returnForm.to_location_id" clearable filterable style="width:100%"
            placeholder="不选则登记为出库中">
            <el-option v-for="l in locations" :key="l.id" :label="`${l.code} ${l.name}`" :value="l.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="returnDialog = false">取消</el-button>
        <el-button type="success" @click="submitReturn">确认归还</el-button>
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
