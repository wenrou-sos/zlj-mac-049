<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { collectionApi, locationApi } from '../api'

const router = useRouter()
const rows = ref([])
const locations = ref([])
const meta = ref({ categories: [], statuses: [] })
const loading = ref(false)

const query = reactive({ keyword: '', category: '', status: '', location_id: null })

const statusTagType = {
  在库: 'success',
  出库中: 'info',
  展陈中: 'primary',
  修复中: 'warning',
  借展中: 'danger',
}

const gradeColor = {
  一级文物: 'danger',
  二级文物: 'warning',
  三级文物: 'success',
  一般文物: 'info',
}

async function load() {
  loading.value = true
  try {
    rows.value = await collectionApi.list({
      keyword: query.keyword || undefined,
      category: query.category || undefined,
      status: query.status || undefined,
      location_id: query.location_id || undefined,
    })
  } finally {
    loading.value = false
  }
}

function reset() {
  query.keyword = ''
  query.category = ''
  query.status = ''
  query.location_id = null
  load()
}

// ---------- 新建/编辑 ----------
const dialogVisible = ref(false)
const editing = ref(null)
const submitting = ref(false)
const formRef = ref(null)
const form = reactive({
  accession_no: '',
  name: '',
  category: '',
  dynasty: '',
  material: '',
  dimension: '',
  weight: '',
  grade: '',
  source: '',
  acquired_date: '',
  location_id: null,
  description: '',
})

const rules = {
  accession_no: [{ required: true, message: '请输入总登记号', trigger: 'blur' }],
  name: [{ required: true, message: '请输入藏品名称', trigger: 'blur' }],
  category: [{ required: true, message: '请选择类别', trigger: 'change' }],
}

function openCreate() {
  editing.value = null
  Object.assign(form, {
    accession_no: '',
    name: '',
    category: '',
    dynasty: '',
    material: '',
    dimension: '',
    weight: '',
    grade: '',
    source: '',
    acquired_date: '',
    location_id: null,
    description: '',
  })
  dialogVisible.value = true
}

async function openEdit(row) {
  editing.value = row.id
  const detail = await collectionApi.get(row.id)
  Object.assign(form, {
    ...detail,
    acquired_date: detail.acquired_date || '',
    location_id: detail.location_id || null,
  })
  dialogVisible.value = true
}

async function submit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    const payload = { ...form, acquired_date: form.acquired_date || null }
    if (editing.value) {
      await collectionApi.update(editing.value, payload)
      ElMessage.success('藏品档案已更新')
    } else {
      await collectionApi.create(payload)
      ElMessage.success('藏品登记成功,已记录入库')
    }
    dialogVisible.value = false
    meta.value = await collectionApi.meta()
    load()
  } finally {
    submitting.value = false
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除藏品「${row.name}」?相关流转记录将一并删除。`, '删除确认', {
    type: 'warning',
  })
  await collectionApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

function locName(id) {
  return locations.value.find((l) => l.id === id)?.name || '—'
}

onMounted(async () => {
  locations.value = await locationApi.list()
  meta.value = await collectionApi.meta()
  load()
})
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">藏品档案</h2>
    <p class="page-sub">登记馆藏文物的总登记号、名称、年代、材质等级与存放位置</p>

    <el-card shadow="never">
      <div class="toolbar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索名称 / 登记号 / 年代"
          clearable
          style="width: 240px"
          :prefix-icon="'Search'"
          @keyup.enter="load"
          @clear="load"
        />
        <el-select v-model="query.category" placeholder="类别" clearable style="width: 130px" @change="load">
          <el-option v-for="c in meta.categories" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 120px" @change="load">
          <el-option v-for="s in meta.statuses" :key="s" :label="s" :value="s" />
        </el-select>
        <el-select
          v-model="query.location_id"
          placeholder="存放位置"
          clearable
          style="width: 180px"
          @change="load"
        >
          <el-option v-for="l in locations" :key="l.id" :label="l.name" :value="l.id" />
        </el-select>
        <el-button @click="reset">重置</el-button>
        <div class="spacer"></div>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">登记藏品</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe @row-click="(r) => router.push(`/collections/${r.id}`)"
        style="cursor:pointer">
        <el-table-column prop="accession_no" label="总登记号" width="140" />
        <el-table-column prop="name" label="藏品名称" min-width="200" />
        <el-table-column prop="category" label="类别" width="100" />
        <el-table-column prop="dynasty" label="年代" width="120" />
        <el-table-column label="等级" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.grade" :type="gradeColor[row.grade] || 'info'" size="small" effect="plain">
              {{ row.grade }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="当前状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType[row.status] || 'info'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="存放位置" min-width="160">
          <template #default="{ row }">{{ locName(row.location_id) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click.stop="openEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click.stop="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑藏品档案' : '登记新藏品'" width="680px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="总登记号" prop="accession_no">
              <el-input v-model="form.accession_no" placeholder="如 GY-2026-0001" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="藏品名称" prop="name">
              <el-input v-model="form.name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="类别" prop="category">
              <el-select v-model="form.category" allow-create filterable style="width:100%">
                <el-option v-for="c in meta.categories" :key="c" :label="c" :value="c" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="年代">
              <el-input v-model="form.dynasty" placeholder="如 明代·永乐" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="材质">
              <el-input v-model="form.material" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="文物等级">
              <el-select v-model="form.grade" clearable style="width:100%">
                <el-option label="一级文物" value="一级文物" />
                <el-option label="二级文物" value="二级文物" />
                <el-option label="三级文物" value="三级文物" />
                <el-option label="一般文物" value="一般文物" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="尺寸">
              <el-input v-model="form.dimension" placeholder="如 高36.5cm" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="重量">
              <el-input v-model="form.weight" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="来源方式">
              <el-input v-model="form.source" placeholder="征集 / 捐赠 / 考古移交" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="入藏日期">
              <el-date-picker v-model="form.acquired_date" type="date" value-format="YYYY-MM-DD"
                style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="存放位置">
              <el-select v-model="form.location_id" clearable filterable style="width:100%">
                <el-option
                  v-for="l in locations.filter((x) => x.location_type === '库房' || x.id === form.location_id)"
                  :key="l.id"
                  :label="`${l.code} ${l.name}`"
                  :value="l.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="档案描述">
              <el-input v-model="form.description" type="textarea" :rows="3" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
