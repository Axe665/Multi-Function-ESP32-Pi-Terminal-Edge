import { createApp } from 'vue'
import '@fontsource/roboto/400.css'
import '@fontsource/roboto/500.css'
import '@fontsource/roboto-mono/400.css'
import '@fontsource/noto-sans-sc/400.css'
import '@fontsource/noto-sans-sc/500.css'
import './styles/m3.css'
import App from './App.vue'
import { router } from './router'

// 主题：默认亮色，选择记在 localStorage
const saved = localStorage.getItem('mt-theme')
document.documentElement.dataset.theme = saved === 'dark' ? 'dark' : 'light'

createApp(App).use(router).mount('#app')
