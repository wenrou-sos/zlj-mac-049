<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { envApi } from '../api'

const route = useRoute()
const router = useRouter()
const activeAlerts = ref(0)
let timer = null

async function refreshBadge() {
  try {
    const alerts = await envApi.alerts({ acknowledged: false })
    activeAlerts.value = alerts.length
  } catch (e) {
    /* 忽略轮询错误 */
  }
}

onMounted(() => {
  refreshBadge()
  timer = setInterval(refreshBadge, 60000)
})
onBeforeUnmount(() => timer && clearInterval(timer))

function go(path) {
  router.push(path)
}
</script>

<template>
  <el-container style="height: 100vh">
    <el-aside width="224px" class="aside">
      <div class="logo">
        <el-icon :size="22" color="#d4a84b"><Schoolbag /></el-icon>
        <span>博物馆藏品管理系统</span>
      </div>
      <el-menu
        :default-active="'/' + (route.path.split('/')[1] || 'dashboard')"
        class="menu"
        background-color="#1f2733"
        text-color="#c0c6cf"
        active-text-color="#e6b450"
        @select="go"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon><span>运行总览</span>
        </el-menu-item>
        <el-menu-item index="/collections">
          <el-icon><Collection /></el-icon><span>藏品档案</span>
        </el-menu-item>
        <el-menu-item index="/movements">
          <el-icon><Switch /></el-icon><span>出入库记录</span>
        </el-menu-item>
        <el-menu-item index="/locations">
          <el-icon><Files /></el-icon><span>存放位置</span>
        </el-menu-item>
        <el-menu-item index="/exhibitions">
          <el-icon><PictureFilled /></el-icon><span>展陈管理</span>
        </el-menu-item>
        <el-menu-item index="/restorations">
          <el-icon><Tools /></el-icon><span>修复管理</span>
        </el-menu-item>
        <el-menu-item index="/loans">
          <el-icon><Promotion /></el-icon><span>借展跟踪</span>
        </el-menu-item>
        <el-menu-item index="/inventories">
          <el-icon><Checked /></el-icon><span>馆藏盘点</span>
        </el-menu-item>
        <el-menu-item index="/environment">
          <el-icon><Odometer /></el-icon>
          <span>环境监测</span>
          <el-badge
            v-if="activeAlerts"
            :value="activeAlerts"
            class="alert-badge"
            type="danger"
          />
        </el-menu-item>
      </el-menu>
      <div class="aside-footer">样例数据 · 演示环境</div>
    </el-aside>

    <el-container>
      <el-main class="main">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" @env-changed="refreshBadge" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.aside {
  background: #1f2733;
  display: flex;
  flex-direction: column;
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 14px;
  color: #f0d68a;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 1px;
}
.menu {
  border-right: none;
  flex: 1;
}
.menu :deep(.el-menu-item.is-active) {
  background: #2a3342;
  border-left: 3px solid #e6b450;
}
.alert-badge {
  margin-left: 8px;
}
.aside-footer {
  color: #5d6775;
  font-size: 12px;
  padding: 14px 16px;
  text-align: center;
}
.main {
  background: #f4f5f7;
  padding: 0;
  overflow-y: auto;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
