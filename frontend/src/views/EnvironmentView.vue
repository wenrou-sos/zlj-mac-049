<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { envApi, locationApi } from '../api'

const emit = defineEmits(['env-changed'])

const locations = ref([])
const selectedId = ref(null)
const readings = ref([])
const alerts = ref([])
const alertFilter = ref(false) // false = 未处理
const hours = ref(72)
const hourOptions = [
  { label: '近 24 小时', value: 24 },
  { label: '近 72 小时', value: 72 },
  { label: '近 7 天', value: 168 },
  { label: '近 30 天', value: 720 },
]
const chartEl = ref(null)
let chart = null

async function loadLocations() {
  locations.value = await locationApi.list()
  if (locations.value.length) {
    const firstAbnormal = locations.value.find((l) => l.active_alert_count)
    selectedId.value = firstAbnormal?.id || locations.value[0].id
    await loadReadings()
  }
}

async function loadReadings() {
  readings.value = await envApi.readings(selectedId.value, hours.value)
  await nextTick()
  renderChart()
}

function renderChart() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  const loc = locations.value.find((l) => l.id === selectedId.value)
  const rows = [...readings.value].reverse()
  const times = rows.map((r) => r.recorded_at.replace('T', ' ').slice(5, 16))

  chart.setOption(
    {
      tooltip: { trigger: 'axis' },
      legend: { data: ['温度℃', '湿度%'], top: 0 },
      grid: { left: 50, right: 55, top: 38, bottom: 40 },
      xAxis: { type: 'category', data: times, boundaryGap: false },
      yAxis: [
        { type: 'value', name: '℃', position: 'left' },
        { type: 'value', name: '%', position: 'right' },
      ],
      series: [
        {
          name: '温度℃',
          type: 'line',
          smooth: true,
          symbol: 'none',
          data: rows.map((r) => r.temperature),
          lineStyle: { width: 2, color: '#c05645' },
          itemStyle: { color: '#c05645' },
          markArea: {
            silent: true,
            itemStyle: { color: 'rgba(192,86,69,0.08)' },
            data: loc ? [[{ yAxis: loc.temp_max }, { yAxis: loc.temp_max + 20 }]] : [],
          },
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { type: 'dashed', color: '#c05645' },
            data: loc
              ? [{ yAxis: loc.temp_min }, { yAxis: loc.temp_max }]
              : [],
            label: { formatter: '温度阈值', color: '#c05645' },
          },
        },
        {
          name: '湿度%',
          type: 'line',
          yAxisIndex: 1,
          smooth: true,
          symbol: 'none',
          data: rows.map((r) => r.humidity),
          lineStyle: { width: 2, color: '#4a7c8f' },
          itemStyle: { color: '#4a7c8f' },
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { type: 'dashed', color: '#4a7c8f' },
            data: loc
              ? [{ yAxis: loc.hum_min }, { yAxis: loc.hum_max }]
              : [],
            label: { formatter: '湿度阈值', color: '#4a7c8f' },
          },
        },
      ],
    },
    true
  )
  chart.resize()
}

async function loadAlerts() {
  alerts.value = await envApi.alerts({ acknowledged: alertFilter.value })
}

async function ack(id) {
  await envApi.ack(id)
  ElMessage.success('告警已确认处理')
  emit('env-changed')
  await Promise.all([loadAlerts(), loadLocations()])
}

async function simulate(anomaly) {
  const res = await envApi.simulate({
    inject_anomaly: anomaly,
    anomaly_location_id: anomaly ? selectedId.value : null,
  })
  if (anomaly) {
    ElMessage.warning(`已在当前位置注入异常读数,生成 ${res.alerts.length} 条告警`)
  } else {
    ElMessage.success('已为所有位置生成一轮正常模拟读数')
  }
  emit('env-changed')
  await Promise.all([loadAlerts(), loadLocations()])
}

watch([selectedId, hours], loadReadings)
window.addEventListener('resize', () => chart?.resize())

onMounted(async () => {
  await loadLocations()
  await loadAlerts()
})
</script>

<template>
  <div class="page-container">
    <h2 class="page-title">环境监测</h2>
    <p class="page-sub">实时监测库房与展厅温湿度,超过位置阈值自动触发预警/严重告警</p>

    <el-row :gutter="14">
      <el-col :span="15">
        <el-card shadow="never">
          <div class="toolbar">
            <el-select v-model="selectedId" style="width:230px" placeholder="选择位置">
              <el-option
                v-for="l in locations"
                :key="l.id"
                :label="`${l.code} ${l.name}`"
                :value="l.id"
              >
                <span>{{ l.code }} {{ l.name }}</span>
                <el-tag v-if="l.active_alert_count" size="small" type="danger" style="margin-left:8px">
                  {{ l.active_alert_count }} 告警
                </el-tag>
              </el-option>
            </el-select>
            <el-select v-model="hours" style="width:130px">
              <el-option v-for="o in hourOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span style="font-size:12px;color:#909399">共 {{ readings.length }} 条读数</span>
            <div class="spacer"></div>
            <el-button :icon="'Refresh'" @click="simulate(false)">模拟正常采集</el-button>
            <el-button type="danger" plain :icon="'Warning'" @click="simulate(true)">
              注入异常读数
            </el-button>
          </div>
          <div ref="chartEl" style="height:360px"></div>
          <el-alert
            v-if="selectedId"
            type="info"
            :closable="false"
            style="margin-top:8px"
            :title="`阈值规则:温度 ${locations.find((l) => l.id === selectedId)?.temp_min}~${locations.find((l) => l.id === selectedId)?.temp_max}℃,湿度 ${locations.find((l) => l.id === selectedId)?.hum_min}~${locations.find((l) => l.id === selectedId)?.hum_max}%;越界触发预警,温度越界≥3℃或湿度越界≥10% 触发严重告警`"
          />
        </el-card>
      </el-col>

      <el-col :span="9">
        <el-card shadow="never">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>异常提醒</span>
              <el-radio-group v-model="alertFilter" size="small" @change="loadAlerts">
                <el-radio-button :value="false">未处理</el-radio-button>
                <el-radio-button :value="true">已处理</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <el-empty v-if="!alerts.length" :description="alertFilter ? '暂无已处理记录' : '无未处理告警 🎉'" :image-size="70" />
          <div v-else class="alert-list">
            <div v-for="a in alerts" :key="a.id" class="alert-item">
              <div class="alert-item-head">
                <el-tag size="small" :type="a.level === '严重' ? 'danger' : 'warning'">
                  {{ a.level }}
                </el-tag>
                <span class="alert-loc">{{ a.location_code }} {{ a.location_name }}</span>
                <span class="alert-time">{{ a.created_at.replace('T', ' ').slice(0, 16) }}</span>
              </div>
              <div class="alert-msg">{{ a.message }}</div>
              <div v-if="a.acknowledged" class="alert-ack">
                已由 {{ a.acknowledged_by }} 于 {{ a.acknowledged_at?.replace('T', ' ').slice(0, 16) }} 处理
              </div>
              <el-button
                v-else
                link
                type="primary"
                size="small"
                style="margin-top:4px"
                @click="ack(a.id)"
              >
                确认处理
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.alert-list {
  max-height: 380px;
  overflow-y: auto;
}
.alert-item {
  padding: 10px 4px;
  border-bottom: 1px dashed #ebeef5;
}
.alert-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.alert-loc {
  font-weight: 600;
  font-size: 13px;
}
.alert-time {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
}
.alert-msg {
  margin: 6px 0;
  font-size: 13px;
  color: #455063;
}
.alert-ack {
  font-size: 12px;
  color: #91b46a;
}
</style>
