<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { collectionApi, exhibitionApi, locationApi } from '../api'

const rows = ref([])
const loading = ref(false)
const statusFilter = ref('')

const createDialog = ref(false)
const formRef = ref(null)
const form = reactive({
  title: '',
  venue: '',
  start_date: '',
  end_date: '',
  curator: '',
  description: '',
})
const rules = {
  title: [{ required: true, message: '请输入展览名称' }],
  venue: [{ required: true, message: '请输入展厅' }],
  start_date: [{ required: true, message: '请选择开始日期' }],
  end_date: [{ required: true, message: '请选择结束日期' }],
}

const itemDialog = ref(false)
const currentEx = ref(null)
const candidates = ref([])
const itemForm = reactive({ collection_id: null, display_location: '' })

const dismountDialog = ref(false)
const dismountTarget = ref({ ex: null, item: null })
const returnLocation = ref(null)
const locations = ref([])

async function load() {
  loading.value = true
  try {
    rows.value = await exhibitionApi.list(statusFilter.value || undefined)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { title: '', venue: '', start_date: '', end_date: '', curator: '', description: '' })
  createDialog.value = true
}

async function submitCreate() {
  await formRef.value.validate()
  if (form.end_date <= form.start_date) {
    ElMessage.warning('结束日期必须晚于开始日期')
    return
  }
  await exhibitionApi.create({ ...form })
  ElMessage.success('展览已创建')
  createDialog.value = false
  load()
}

async function openItem(ex) {
  currentEx.value = ex
  itemForm.collection_id = null
  itemForm.display_location = ''
  candidates.value = await collectionApi.list({ status: '在库' })
  itemDialog.value = true
}

async function submitItem() {
  if (!itemForm.collection_id) {
    ElMessage.warning('请选择藏品')
    return
  }
  await exhibitionApi.addItem(currentEx.value.id, { ...itemForm })
  ElMessage.success('已布展,藏品状态更新为「展陈中」')
  itemDialog.value = false
  load()
}

function openDismount(ex, item) {
  dismountTarget.value = { ex, item }
  returnLocation.value = null
  dismountDialog.value = true
}

async function submitDismount() {
  await exhibitionApi.dismount(
    dismountTarget.value.ex.id,
    dismountTarget.value.item.id,
    returnLocation.value
  )
  ElMessage.success('撤展完成')
  dismountDialog.value = false
  load()
}

const statusType = { 筹备中: 'info', 开展中: 'primary', 已结束: 'success' }

onMounted(async () => {
  locations.value = await locationApi.list({ location_type: '库房' })
  load()
})
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">展陈管理</h2>
    <p class="page-sub">管理馆内展览的生命周期与展品布展/撤展过程</p>

    <el-card shadow="never">
      <div class="toolbar">
        <el-radio-group v-model="statusFilter" @change="load">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="筹备中">筹备中</el-radio-button>
          <el-radio-button label="开展中">开展中</el-radio-button>
          <el-radio-button label="已结束">已结束</el-radio-button>
        </el-radio-group>
        <div class="spacer"></div>
        <el-button type="primary" :icon="'Plus'" @click="openCreate">策划新展</el-button>
      </div>

      <el-row :gutter="14" v-loading="loading">
        <el-col v-for="ex in rows" :key="ex.id" :span="8" style="margin-bottom:14px">
          <el-card class="ex-card" shadow="hover">
            <div class="ex-head">
              <el-tag size="small" :type="statusType[ex.status]">{{ ex.status }}</el-tag>
              <el-button
                link
                type="primary"
                size="small"
                :disabled="ex.status === '已结束'"
                @click="openItem(ex)"
              >
                + 布展藏品
              </el-button>
            </div>
            <h3 class="ex-title">{{ ex.title }}</h3>
            <div class="ex-meta">
              <el-icon><Location /></el-icon>{{ ex.venue }}
            </div>
            <div class="ex-meta">
              <el-icon><Calendar /></el-icon>{{ ex.start_date }} 至 {{ ex.end_date }}
            </div>
            <div class="ex-meta" v-if="ex.curator">策展人:{{ ex.curator }}</div>
            <el-divider style="margin:10px 0" />
            <div class="items">
              <el-empty v-if="!ex.items.length" description="暂无展品" :image-size="40" />
              <div v-for="it in ex.items" :key="it.id" class="item-row">
                <el-tag size="small" :type="it.status === '已布展' ? 'primary' : 'info'" effect="plain">
                  {{ it.status }}
                </el-tag>
                <span class="item-name">{{ it.accession_no }} {{ it.collection_name }}</span>
                <el-button
                  v-if="it.status === '已布展' && ex.status !== '已结束'"
                  link
                  type="warning"
                  size="small"
                  @click="openDismount(ex, it)"
                >
                  撤展
                </el-button>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <el-dialog v-model="createDialog" title="策划新展" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="92px">
        <el-form-item label="展览名称" prop="title">
          <el-input v-model="form.title" />
        </el-form-item>
        <el-form-item label="展厅" prop="venue">
          <el-input v-model="form.venue" placeholder="如 第一展厅 / 临时展厅" />
        </el-form-item>
        <el-form-item label="展期">
          <el-date-picker
            v-model="form.range"
            type="daterange"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DD"
            style="width:100%"
            @change="(v) => { form.start_date = v?.[0]; form.end_date = v?.[1] }"
          />
        </el-form-item>
        <el-form-item label="策展人">
          <el-input v-model="form.curator" />
        </el-form-item>
        <el-form-item label="展览简介">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="itemDialog" :title="`布展藏品 · ${currentEx?.title || ''}`" width="520px">
      <el-form :model="itemForm" label-width="80px">
        <el-form-item label="选择藏品">
          <el-select v-model="itemForm.collection_id" filterable style="width:100%" placeholder="仅显示在库藏品">
            <el-option
              v-for="c in candidates"
              :key="c.id"
              :label="`${c.accession_no} ${c.name}`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="展位">
          <el-input v-model="itemForm.display_location" placeholder="如 独立展柜 C-01" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="itemDialog = false">取消</el-button>
        <el-button type="primary" @click="submitItem">确认布展</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dismountDialog" title="撤展归库" width="440px">
      <p>将「{{ dismountTarget.item?.collection_name }}」从「{{ dismountTarget.ex?.title }}」撤展。</p>
      <el-form label-width="92px">
        <el-form-item label="归库位置">
          <el-select v-model="returnLocation" clearable filterable style="width:100%" placeholder="不选则登记为出库中">
            <el-option
              v-for="l in locations"
              :key="l.id"
              :label="`${l.code} ${l.name}`"
              :value="l.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dismountDialog = false">取消</el-button>
        <el-button type="warning" @click="submitDismount">确认撤展</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.ex-card {
  min-height: 250px;
}
.ex-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ex-title {
  font-size: 16px;
  margin: 10px 0 6px;
  color: #263445;
}
.ex-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 13px;
  color: #606266;
  margin-top: 4px;
}
.item-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}
.item-name {
  flex: 1;
}
</style>
