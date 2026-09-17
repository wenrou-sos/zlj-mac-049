<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { collectionApi, movementApi } from '../api'

const router = useRouter()
const rows = ref([])
const loading = ref(false)
const collections = ref([])
const filters = ref({ collection_id: null, move_type: '' })

const moveTypes = ['入库', '出库', '移库', '布展', '撤展归库', '修复出库', '修复归库', '借展出库', '借展归还', '盘点调整']
const moveTypeTag = {
  入库: 'success',
  出库: 'info',
  移库: 'primary',
  布展: 'primary',
  撤展归库: 'success',
  修复出库: 'warning',
  修复归库: 'success',
  借展出库: 'danger',
  借展归还: 'success',
  盘点调整: 'warning',
}

async function load() {
  loading.value = true
  try {
    rows.value = await movementApi.list({
      collection_id: filters.value.collection_id || undefined,
      move_type: filters.value.move_type || undefined,
      limit: 500,
    })
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  collections.value = await collectionApi.list()
  load()
})
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">出入库记录</h2>
    <p class="page-sub">全馆藏品每一次出入库、移库、布展、修复、借展流转的完整台账</p>

    <el-card shadow="never">
      <div class="toolbar">
        <el-select
          v-model="filters.collection_id"
          placeholder="按藏品筛选"
          filterable
          clearable
          style="width: 280px"
          @change="load"
        >
          <el-option
            v-for="c in collections"
            :key="c.id"
            :label="`${c.accession_no} ${c.name}`"
            :value="c.id"
          />
        </el-select>
        <el-select v-model="filters.move_type" placeholder="流转类型" clearable style="width:150px" @change="load">
          <el-option v-for="t in moveTypes" :key="t" :label="t" :value="t" />
        </el-select>
      </div>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ row.move_date.replace('T', ' ').slice(0, 16) }}</template>
        </el-table-column>
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="moveTypeTag[row.move_type] || 'info'">{{ row.move_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="藏品" min-width="200">
          <template #default="{ row }">
            <el-link type="primary" @click="router.push(`/collections/${row.collection_id}`)">
              {{ row.accession_no }} {{ row.collection_name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column label="从" min-width="140">
          <template #default="{ row }">{{ row.from_location?.name || '库外' }}</template>
        </el-table-column>
        <el-table-column label="到" min-width="140">
          <template #default="{ row }">{{ row.to_location?.name || '库外' }}</template>
        </el-table-column>
        <el-table-column prop="purpose" label="事由" min-width="180" />
        <el-table-column prop="operator" label="操作员" width="110" />
        <el-table-column prop="handler" label="经手" width="90" />
        <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>
