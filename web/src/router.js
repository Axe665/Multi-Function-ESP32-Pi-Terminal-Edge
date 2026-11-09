import { createRouter, createWebHashHistory } from 'vue-router'

export const routes = [
  { path: '/', component: () => import('./views/Overview.vue'), meta: { nav: '总览' } },
  { path: '/devices', component: () => import('./views/Devices.vue'), meta: { nav: '设备' } },
  { path: '/devices/:id', component: () => import('./views/DeviceDetail.vue'), meta: { nav: '设备' } },
  { path: '/analysis', component: () => import('./views/Analysis.vue'), meta: { nav: '分析' } },
  { path: '/access', component: () => import('./views/Access.vue'), meta: { nav: '接入' } },
  { path: '/settings', component: () => import('./views/Settings.vue'), meta: { nav: '设置' } },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
})
