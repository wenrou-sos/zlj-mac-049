<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { envApi, locationApi } from '../api'

const emit = defineEmits(['env-changed'])
const rows = ref([])
const loading = ref(false)
const typeFilter = ref('')

const dialog = ref(false)
const editing = ref(null)
const formRef = ref(null)
const form = reactive({
  code: '',
  name: '',
  zone: '',
  location_type: '库房',
  temp_min: 15,
  temp_max: 22,
  hum_min: 45,
  hum_max: 60,
  description: '',
})
const rules = {
  code: [{ required: true, message: '请输入位置编号' }],
  name: [{ required: true, message: '请输入位置名称' }],
  zone: [{ required: true, message: '请输入所属库区/楼层' }],
}

// 人工录入读数
const readingDialog = ref(false)
const readingTarget = ref(null)
const readingForm = reactive({ temperature: 20, humidity: 50, source: '人工' })

async function load() {
  loading.value = true
  try {
    rows.value = await locationApi.list(
      typeFilter.value ? { location_type: typeFilter.value } : {}
    )
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, {
    code: '',
    name: '',
    zone: '',
    location_type: '库房',
    temp_min: 15,
    temp_max: 22,
    hum_min: 45,
    hum_max: 60,
    description: '',
  })
  dialog.value = true
}

function openEdit(row) {
  editing.value = row.id
  Object.assign(form, row)
  dialog.value = true
}

async function submit() {
  await formRef.value.validate()
  if (form.temp_min >= form.temp_max || form.hum_min >= form.hum_max) {
    ElMessage.warning('阈值下限必须小于上限')
    return
  }
  if (editing.value) {
    await locationApi.update(editing.value, { ...form })
    ElMessage.success('位置已更新')
  } else {
    await locationApi.create({ ...form })
    ElMessage.success('位置已创建')
  }
  dialog.value = false
  load()
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除位置「${row.name}」?`, '删除确认', { type: 'warning' })
  await locationApi.remove(row.id)
  ElMessage.success('已删除')
  load()
}

function openReading(row) {
  readingTarget.value = row
  readingForm.temperature = row.latest_temp ?? (row.temp_min + row.temp_max) / 2
  readingForm.humidity = row.latest_hum ?? (row.hum_min + row.hum_max) / 2
  readingForm.source = '人工'
  readingDialog.value = true
}

async function submitReading() {
  await locationApi.addReading(readingTarget.value.id, { ...readingForm })
  ElMessage.success('环境数据已录入,若越界将自动生成告警')
  readingDialog.value = false
  emit('env-changed')
  load()
}

async function simulateAll() {
  const res = await envApi.simulate({ inject_anomaly: false })
  ElMessage.success(`已生成 ${res.readings.length} 个位置的模拟采集数据`)
  load()
}

onMounted(load)
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">存放位置</h2>
    <p class="page-sub">管理库房、展厅、修复室等位置档案,以及每个位置的温湿度控制阈值</p>

    <el-card shadow="never">
      <div class="toolbar">
        <el-radio-group v-model="typeFilter" @change="load">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="库房">库房</el-radio-button>
          <el-radio-button label="展厅">展厅</el-radio-button>
          <el-radio-button label="修复室">修复室</el-radio-button>
          <el-radio-button label="其他">其他</el-radio-button>
        </el-radio-group>
        <div class="spacer"></div>
        <el-button :icon="'Refresh'" @click="simulateAll">模拟采集一轮</el-button>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">新增位置</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="code" label="编号" width="90" />
        <el-table-column prop="name" label="名称" min-width="170" />
        <el-table-column prop="zone" label="区域" width="110" />
        <el-table-column prop="location_type" label="类型" width="80" />
        <el-table-column label="在藏数量" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.collection_count }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="温度阈值(℃)" width="130">
          <template #default="{ row }">{{ row.temp_min }} ~ {{ row.temp_max }}</template>
        </el-table-column>
        <el-table-column label="湿度阈值(%)" width="120">
          <template #default="{ row }">{{ row.hum_min }} ~ {{ row.hum_max }}</template>
        </el-table-column>
        <el-table-column label="最新温度" width="90">
          <template #default="{ row }">
            <span v-if="row.latest_temp != null" :class="{ abnormal: row.latest_temp < row.temp_min || row.latest_temp > row.temp_max }">
              {{ row.latest_temp.toFixed(1) }}℃
            </span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="最新湿度" width="90">
          <template #default="{ row }">
            <span v-if="row.latest_hum != null" :class="{ abnormal: row.latest_hum < row.hum_min || row.latest_hum > row.hum_max }">
              {{ row.latest_hum.toFixed(1) }}%
            </span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="未处理告警" width="100" align="center">
          <template #default="{ row }">
            <el-badge v-if="row.active_alert_count" :value="row.active_alert_count" type="danger" />
            <el-tag v-else type="success" size="small" effect="plain">正常</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openReading(row)">录入读数</el-button>
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialog" :title="editing ? '编辑存放位置' : '新增存放位置'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-row :gutter="10">
          <el-col :span="12">
            <el-form-item label="位置编号" prop="code">
              <el-input v-model="form.code" placeholder="如 A-101" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="位置名称" prop="name">
              <el-input v-model="form.name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属区域" prop="zone">
              <el-input v-model="form.zone" placeholder="如 一层库区" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="位置类型">
              <el-select v-model="form.location_type" style="width:100%">
                <el-option label="库房" value="库房" />
                <el-option label="展厅" value="展厅" />
                <el-option label="修复室" value="修复室" />
                <el-option label="其他" value="其他" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="温度下限℃">
              <el-input-number v-model="form.temp_min" :precision="1" :step="0.5" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="温度上限℃">
              <el-input-number v-model="form.temp_max" :precision="1" :step="0.5" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="湿度下限%">
              <el-input-number v-model="form.hum_min" :precision="1" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="湿度上限%">
              <el-input-number v-model="form.hum_max" :precision="1" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="描述">
              <el-input v-model="form.description" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="readingDialog" :title="`录入环境读数 · ${readingTarget?.name || ''}`" width="420px">
      <el-form :model="readingForm" label-width="80px">
        <el-form-item label="温度℃">
          <el-input-number v-model="readingForm.temperature" :precision="1" :step="0.5" :min="-20" :max="60" />
          <span style="margin-left:10px;color:#909399;font-size:12px">
            阈值 {{ readingTarget?.temp_min }}~{{ readingTarget?.temp_max }}
          </span>
        </el-form-item>
        <el-form-item label="湿度%">
          <el-input-number v-model="readingForm.humidity" :precision="1" :min="0" :max="100" />
          <span style="margin-left:10px;color:#909399;font-size:12px">
            阈值 {{ readingTarget?.hum_min }}~{{ readingTarget?.hum_max }}
          </span>
        </el-form-item>
        <el-form-item label="数据来源">
          <el-radio-group v-model="readingForm.source">
            <el-radio value="人工">人工读数</el-radio>
            <el-radio value="传感器">传感器</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="readingDialog = false">取消</el-button>
        <el-button type="primary" @click="submitReading">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.abnormal {
  color: #c0392b;
  font-weight: 600;
}
</style>
