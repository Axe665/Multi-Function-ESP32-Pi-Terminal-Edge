import { ref } from 'vue'

const saved = localStorage.getItem('mt-theme')
export const theme = ref(saved === 'dark' ? 'dark' : 'light')

function apply() {
  document.documentElement.dataset.theme = theme.value
  localStorage.setItem('mt-theme', theme.value)
}

// 模块加载时就应用，避免刷新后先闪一下亮色
apply()

export function useTheme() {
  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    apply()
  }
  return { theme, toggleTheme }
}

/** 图表配色：ECharts 不认 CSS 变量，按主题给两套。 */
export function chartTokens(mode) {
  const dark = mode === 'dark'
  return dark
    ? {
        axis: '#8d9286', split: '#33362f', text: '#e3e3dc',
        line: '#9cd67e', area: 'rgba(156,214,126,0.14)',
        heat: ['#2a2d26', '#4f7a3a', '#b7f397'],
        heatZ: ['#4d86a6', '#7fb3d1', '#3f5b66', '#2a2d26', '#5c4a22', '#b8862f', '#e0b05a'],
        border: '#1e201b',
        word: { sat: [35, 50], light: [62, 80] },
        palette: ['#9cd67e', '#7fd3d8', '#e0b05a', '#e39ab0', '#9aa8e8', '#b8c78a'],
      }
    : {
        axis: '#74796d', split: '#eef1ec', text: '#1a1c18',
        line: '#386a20', area: 'rgba(56,106,32,0.10)',
        heat: ['#eef1ec', '#9cd67e', '#386a20'],
        heatZ: ['#3f7ea0', '#8fc0d6', '#dce9ef', '#f4f4f0', '#f0dcb6', '#ddab55', '#b57a05'],
        border: '#ffffff',
        word: { sat: [38, 56], light: [24, 36] },
        palette: ['#386a20', '#38656a', '#7a5900', '#8c4a5f', '#4a5b8c', '#5d6b3a'],
      }
}
