<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { dashboardApi, envApi } from '../api'

const emit = defineEmits(['env-changed'])
const router = useRouter()
const data = ref(null)
const alerts = ref([])
const categoryChart = ref(null)
const statusChart = ref(null)
const gradeChart = ref(null)
let chartInsts = []

const palette = ['#c05645', '#d4a84b', '#4a7c8f', '#6b8f5e', '#8c6fa0', '#b0784f', '#7d8fa6']

async function load() {
  data.value = await dashboardApi.get()
  alerts.value = await envApi.alerts({ acknowledged: false })
  await nextTick()
  renderCharts()
}

function renderCharts() {
  chartInsts.forEach((c) => c.dispose())
  chartInsts = []
  if (!data.value) return

  const c1 = echarts.init(categoryChart.value)
  c1.setOption({
    title: { text: '藏品类别分布', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'item', formatter: '{b}: {c} 件 ({d}%)' },
    legend: { bottom: 0, type: 'scroll', textStyle: { fontSize: 11 } },
    color: palette,
    series: [
      {
        type: 'pie',
        radius: ['38%', '62%'],
        center: ['50%', '46%'],
        label: { formatter: '{b}\n{c}件' },
        data: data.value.by_category,
      },
    ],
  })

  const statusEntries = Object.entries(data.value.by_status)
  const c2 = echarts.init(statusChart.value)
  c2.setOption({
    title: { text: '藏品状态分布', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 44, right: 20, top: 46, bottom: 30 },
    xAxis: { type: 'category', data: statusEntries.map((e) => e[0]) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        type: 'bar',
        barWidth: 26,
        data: statusEntries.map((e, i) => ({
          value: e[1],
          itemStyle: { color: ['#6b8f5e', '#b0784f', '#4a7c8f', '#8c6fa0', '#c05645'][i] },
        })),
        label: { show: true, position: 'top' },
      },
    ],
  })

  const c3 = echarts.init(gradeChart.value)
  c3.setOption({
    title: { text: '文物等级构成', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'item', formatter: '{b}: {c} 件' },
    color: ['#b03a2e', '#d4a84b', '#6b8f5e', '#7d8fa6'],
    series: [
      {
        type: 'pie',
        radius: '62%',
        center: ['50%', '48%'],
        label: { formatter: '{b}: {c}' },
        data: data.value.grade_stats,
      },
    ],
  })
  chartInsts = [c1, c2, c3]
}

window.addEventListener('resize', () => chartInsts.forEach((c) => c.resize()))

async function ackAlert(id) {
  await envApi.ack(id)
  emit('env-changed')
  load()
}

onMounted(load)
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">运行总览</h2>
    <p class="page-sub">馆藏资产、借展、展陈、修复与库房环境一屏掌握</p>

    <template v-if="data">
      <el-row :gutter="14">
        <el-col :span="6">
          <el-card class="stat-card" @click="router.push('/collections')">
            <el-statistic title="藏品总数(件)" :value="data.total_collections">
              <template #suffix><span style="font-size:13px;color:#909399">件</span></template>
            </el-statistic>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card class="stat-card" @click="router.push('/environment')">
            <el-statistic
              title="未处理环境告警"
              :value="data.active_alerts"
              :value-style="{ color: data.critical_alerts ? '#c0392b' : '#e6a23c' }"
            />
            <div style="font-size:12px;color:#909399;margin-top:4px">
              其中严重 {{ data.critical_alerts }} 条
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card class="stat-card" @click="router.push('/loans')">
            <el-statistic title="在外借展(件)" :value="data.loans_active" />
            <div style="font-size:12px;margin-top:4px">
              <el-tag type="danger" size="small" effect="plain">逾期 {{ data.loans_overdue }}</el-tag>
              <el-tag type="warning" size="small" effect="plain" style="margin-left:6px">
                30天内到期 {{ data.loans_due_soon }}
              </el-tag>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card class="stat-card" @click="router.push('/exhibitions')">
            <el-statistic title="开展中展览(个)" :value="data.exhibitions_active" />
            <div style="font-size:12px;color:#909399;margin-top:4px">
              修复中项目 {{ data.restorations_active }} 个
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="14" style="margin-top:14px">
        <el-col :span="24">
          <el-card class="stat-card" body-style="padding:16px 20px" @click="router.push('/inventories')">
            <div class="inv-banner">
              <el-icon :size="26" color="#d4a84b"><Finished /></el-icon>
              <div class="inv-banner-main">
                <div class="inv-banner-title">馆藏盘点</div>
                <div style="font-size:12px;color:#909399">
                  进行中任务 {{ data.inventory_active }} 个
                  <el-tag v-if="data.inventory_overdue" type="danger" size="small" effect="plain" style="margin-left:8px">
                    已逾期 {{ data.inventory_overdue }}
                  </el-tag>
                  <el-tag v-if="data.inventory_pending_review" type="warning" size="small" effect="plain" style="margin-left:6px">
                    {{ data.inventory_pending_review }} 个任务有差异待复核
                  </el-tag>
                  <span v-if="!data.inventory_active" style="margin-left:8px">暂无进行中盘点</span>
                </div>
              </div>
              <el-button type="primary" plain size="small">进入盘点</el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="14" style="margin-top:14px">
        <el-col :span="8"><el-card><div ref="categoryChart" style="height:280px"></div></el-card></el-col>
        <el-col :span="8"><el-card><div ref="statusChart" style="height:280px"></div></el-card></el-col>
        <el-col :span="8"><el-card><div ref="gradeChart" style="height:280px"></div></el-card></el-col>
      </el-row>

      <el-row :gutter="14" style="margin-top:14px">
        <el-col :span="14">
          <el-card header="⚠️ 温湿度异常提醒(未处理)">
            <el-empty v-if="!alerts.length" description="暂无未处理告警" :image-size="60" />
            <el-timeline v-else>
              <el-timeline-item
                v-for="a in alerts"
                :key="a.id"
                :type="a.level === '严重' ? 'danger' : 'warning'"
                :timestamp="a.created_at.replace('T', ' ').slice(0, 16)"
              >
                <div class="alert-line">
                  <el-tag :type="a.level === '严重' ? 'danger' : 'warning'" size="small">
                    {{ a.level }}
                  </el-tag>
                  <span style="margin:0 8px">{{ a.message }}</span>
                  <el-button link type="primary" size="small" @click="ackAlert(a.id)">
                    确认处理
                  </el-button>
                </div>
              </el-timeline-item>
            </el-timeline>
          </el-card>
        </el-col>
        <el-col :span="10">
          <el-card header="🌡️ 各位置最新环境">
            <el-table :data="data.env_status" size="small" :max-height="320">
              <el-table-column prop="location_name" label="位置" min-width="120" />
              <el-table-column label="温度℃" width="78">
                <template #default="{ row }">
                  <span :style="{ color: row.temp_status === '异常' ? '#c0392b' : '' }">
                    {{ row.temperature?.toFixed(1) ?? '—' }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="湿度%" width="78">
                <template #default="{ row }">
                  <span :style="{ color: row.hum_status === '异常' ? '#c0392b' : '' }">
                    {{ row.humidity?.toFixed(1) ?? '—' }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="告警" width="60">
                <template #default="{ row }">
                  <el-badge v-if="row.active_alerts" :value="row.active_alerts" type="danger" />
                  <span v-else style="color:#91b46a">正常</span>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<style scoped>
.alert-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  font-size: 13px;
}
.inv-banner {
  display: flex;
  align-items: center;
  gap: 14px;
}
.inv-banner-main {
  flex: 1;
}
.inv-banner-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2d3d;
  margin-bottom: 2px;
}
</style>
