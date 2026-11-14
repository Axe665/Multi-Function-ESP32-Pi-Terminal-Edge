import { createRouter, createWebHashHistory } from 'vue-router'

// meta.title 是顶栏标题，meta.icon 是导航 rail 的 Material Symbols 图标
export const routes = [
  { path: '/', component: () => import('./views/Overview.vue'), meta: { title: '总览', nav: '总览', icon: 'dashboard' } },
  { path: '/devices', component: () => import('./views/Devices.vue'), meta: { title: '设备', nav: '设备', icon: 'devices' } },
  { path: '/devices/:id', component: () => import('./views/DeviceDetail.vue'), meta: { title: '设备详情', nav: '设备', icon: 'devices' } },
  { path: '/analysis', component: () => import('./views/Analysis.vue'), meta: { title: '分析', nav: '分析', icon: 'insights' } },
  { path: '/access', component: () => import('./views/Access.vue'), meta: { title: '接入', nav: '接入', icon: 'cable' } },
  { path: '/settings', component: () => import('./views/Settings.vue'), meta: { title: '设置', nav: '设置', icon: 'settings' } },
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})
