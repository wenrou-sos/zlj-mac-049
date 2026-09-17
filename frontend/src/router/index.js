import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('../components/Layout.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      {
        path: 'dashboard',
        name: '总览',
        component: () => import('../views/DashboardView.vue'),
      },
      {
        path: 'collections',
        name: '藏品档案',
        component: () => import('../views/CollectionsView.vue'),
      },
      {
        path: 'collections/:id',
        name: '藏品详情',
        component: () => import('../views/CollectionDetailView.vue'),
      },
      {
        path: 'movements',
        name: '出入库记录',
        component: () => import('../views/MovementsView.vue'),
      },
      {
        path: 'locations',
        name: '存放位置',
        component: () => import('../views/LocationsView.vue'),
      },
      {
        path: 'exhibitions',
        name: '展陈管理',
        component: () => import('../views/ExhibitionsView.vue'),
      },
      {
        path: 'restorations',
        name: '修复管理',
        component: () => import('../views/RestorationsView.vue'),
      },
      {
        path: 'loans',
        name: '借展跟踪',
        component: () => import('../views/LoansView.vue'),
      },
      {
        path: 'environment',
        name: '环境监测',
        component: () => import('../views/EnvironmentView.vue'),
      },
      {
        path: 'inventories',
        name: '馆藏盘点',
        component: () => import('../views/InventoriesView.vue'),
      },
      {
        path: 'inventories/:id',
        name: '盘点任务详情',
        component: () => import('../views/InventoryDetailView.vue'),
      },
    ],
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
