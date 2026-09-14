<template>
  <router-view />
</template>

<style>
html,
body,
#app {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
}
.page-container {
  padding: 18px 20px;
}
.page-title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 600;
  color: #1f2d3d;
}
.page-sub {
  margin: 0 0 16px;
  font-size: 13px;
  color: #909399;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
}
.toolbar .spacer {
  flex: 1;
}
.stat-card {
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
}
.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
}
</style>
