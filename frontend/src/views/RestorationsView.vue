<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { collectionApi, locationApi, restorationApi } from '../api'

const rows = ref([])
const loading = ref(false)
const statusFilter = ref('')
const locations = ref([])

const createDialog = ref(false)
const formRef = ref(null)
const collections = ref([])
const form = reactive({
  collection_id: null,
  project_name: '',
  reason: '',
  plan: '',
  restorer: '',
  start_date: '',
})
const rules = {
  collection_id: [{ required: true, message: '请选择藏品' }],
  project_name: [{ required: true, message: '请输入修复项目名称' }],
}

const timelineDialog = ref(false)
const current = ref(null)
const timelineForm = reactive({ date: '', stage: '', note: '' })

const completeDialog = ref(false)
const completeTarget = ref(null)
const completeForm = reactive({ result: '', end_date: '', return_location_id: null })

async function load() {
  loading.value = true
  try {
    rows.value = await restorationApi.list(statusFilter.value || undefined)
  } finally {
    loading.value = false
  }
}

async function openCreate() {
  Object.assign(form, {
    collection_id: null,
    project_name: '',
    reason: '',
    plan: '',
    restorer: '',
    start_date: '',
  })
  collections.value = await collectionApi.list()
  createDialog.value = true
}

async function submitCreate() {
  await formRef.value.validate()
  await restorationApi.create({
    ...form,
    start_date: form.start_date || null,
  })
  ElMessage.success('修复项目已立项,藏品状态更新为「修复中」')
  createDialog.value = false
  load()
}

function openTimeline(row) {
  current.value = row
  Object.assign(timelineForm, { date: '', stage: '', note: '' })
  timelineDialog.value = true
}

async function submitTimeline() {
  if (!timelineForm.date || !timelineForm.stage) {
    ElMessage.warning('请填写日期与阶段')
    return
  }
  await restorationApi.addTimeline(current.value.id, { ...timelineForm })
  ElMessage.success('过程节点已追加')
  timelineDialog.value = false
  load()
}

function openComplete(row) {
  completeTarget.value = row
  Object.assign(completeForm, { result: '', end_date: '', return_location_id: null })
  completeDialog.value = true
}

async function submitComplete() {
  await restorationApi.complete(
    completeTarget.value.id,
    { result: completeForm.result, end_date: completeForm.end_date || null },
    completeForm.return_location_id
  )
  ElMessage.success('修复项目已结项,藏品归库')
  completeDialog.value = false
  load()
}

onMounted(async () => {
  locations.value = await locationApi.list({ location_type: '库房' })
  load()
})
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">修复管理</h2>
    <p class="page-title-sub page-sub">记录藏品送修、病害诊断、修复方案、过程节点与结项验收</p>

    <el-card shadow="never">
      <div class="toolbar">
        <el-radio-group v-model="statusFilter" @change="load">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="进行中">进行中</el-radio-button>
          <el-radio-button label="已完成">已完成</el-radio-button>
        </el-radio-group>
        <div class="spacer"></div>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">立项修复</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === '进行中' ? 'warning' : 'success'">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="藏品" min-width="190">
          <template #default="{ row }">
            <el-link type="primary" @click="$router.push(`/collections/${row.collection_id}`)">
              {{ row.accession_no }} {{ row.collection_name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="project_name" label="修复项目" min-width="180" />
        <el-table-column prop="restorer" label="修复师" width="120" />
        <el-table-column label="周期" width="210">
          <template #default="{ row }">{{ row.start_date }} ~ {{ row.end_date || '至今' }}</template>
        </el-table-column>
        <el-table-column label="过程节点" width="90" align="center">
          <template #default="{ row }">{{ row.timeline?.length || 0 }} 条</template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openTimeline(row)">追加节点</el-button>
            <el-button
              v-if="row.status === '进行中'"
              link
              type="success"
              size="small"
              @click="openComplete(row)"
            >
              结项
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="createDialog" title="修复立项" width="600px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
        <el-form-item label="藏品" prop="collection_id">
          <el-select v-model="form.collection_id" filterable style="width:100%" placeholder="仅在库藏品可送修">
            <el-option
              v-for="c in collections.filter((x) => x.status === '在库')"
              :key="c.id"
              :label="`${c.accession_no} ${c.name}`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="项目名称" prop="project_name">
          <el-input v-model="form.project_name" />
        </el-form-item>
        <el-form-item label="病害状况">
          <el-input v-model="form.reason" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="修复方案">
          <el-input v-model="form.plan" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="修复师">
          <el-input v-model="form.restorer" />
        </el-form-item>
        <el-form-item label="开始日期">
          <el-date-picker v-model="form.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">立项并出库</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="timelineDialog" :title="`修复过程 · ${current?.project_name || ''}`" width="560px">
      <el-timeline style="margin-bottom:16px;max-height:240px;overflow-y:auto">
        <el-timeline-item
          v-for="(t, i) in current?.timeline || []"
          :key="i"
          :timestamp="t.date"
          placement="top"
        >
          <b>{{ t.stage }}</b>
          <div style="font-size:13px;color:#606266">{{ t.note }}</div>
        </el-timeline-item>
      </el-timeline>
      <el-divider style="margin:6px 0 14px">追加节点</el-divider>
      <el-form :model="timelineForm" label-width="72px">
        <el-form-item label="日期">
          <el-date-picker v-model="timelineForm.date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="阶段">
          <el-input v-model="timelineForm.stage" placeholder="如 病害处理 / 修复实施" />
        </el-form-item>
        <el-form-item label="记录">
          <el-input v-model="timelineForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="timelineDialog = false">关闭</el-button>
        <el-button type="primary" @click="submitTimeline">追加</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="completeDialog" title="修复结项验收" width="520px">
      <el-form :model="completeForm" label-width="92px">
        <el-form-item label="完成日期">
          <el-date-picker v-model="completeForm.end_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="修复结果">
          <el-input v-model="completeForm.result" type="textarea" :rows="3" placeholder="验收结论与后续保护建议" />
        </el-form-item>
        <el-form-item label="归库位置">
          <el-select v-model="completeForm.return_location_id" clearable filterable style="width:100%"
            placeholder="不选则登记为出库中">
            <el-option v-for="l in locations" :key="l.id" :label="`${l.code} ${l.name}`" :value="l.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="completeDialog = false">取消</el-button>
        <el-button type="success" @click="submitComplete">结项并归库</el-button>
      </template>
    </el-dialog>
  </div>
</template>
