import { ref } from 'vue'

const KEY = 'mt-theme'

// index.html 里的内联脚本已经在首帧前写好 data-theme，这里只接管状态
export const theme = ref(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')

function apply() {
  document.documentElement.dataset.theme = theme.value
}

export function useTheme() {
  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    localStorage.setItem(KEY, theme.value)
    apply()
  }
  return { theme, toggleTheme }
}

// 没手动选过就跟随系统，选过之后手动优先
if (!localStorage.getItem(KEY)) {
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    theme.value = e.matches ? 'dark' : 'light'
    apply()
  })
}

const root = document.documentElement
const read = (name) => getComputedStyle(root).getPropertyValue(name).trim()

function hexToRgb(hex) {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.replace(/./g, (c) => c + c) : h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

const rgb = (hex, a = 1) => `rgba(${hexToRgb(hex).join(',')},${a})`

/** 两个颜色按 t 线性混合，用来从 token 派生热力/面积色。 */
function mix(a, b, t) {
  const [r1, g1, b1] = hexToRgb(a)
  const [r2, g2, b2] = hexToRgb(b)
  const at = (x, y) => Math.round(x + (y - x) * t)
  return `#${[at(r1, r2), at(g1, g2), at(b1, b2)]
    .map((v) => v.toString(16).padStart(2, '0'))
    .join('')}`
}

/**
 * 图表配色：ECharts 不认 CSS 变量，运行时从 token 读，
 * 所以亮暗两套只有 m3.css 一处来源。mode 只用于让调用方显式重算。
 */
export function chartTokens(mode) {
  void mode
  const surface = read('--md-surface-container-low') || '#ffffff'
  const line = read('--md-chart-1') || '#386a20'
  const cool = read('--md-chart-cool') || line
  const warm = read('--md-chart-warm') || '#8a5a00'
  return {
    axis: read('--md-on-surface-variant') || '#43483e',
    split: read('--md-outline-variant') || '#c3c8bb',
    text: read('--md-on-surface') || '#1a1c18',
    line,
    critical: read('--md-critical') || '#b3261e',
    notice: read('--md-notice') || '#8a5a00',
    area: rgb(line, theme.value === 'dark' ? 0.18 : 0.12),
    heat: [mix(surface, line, 0.12), mix(surface, line, 0.5), line],
    heatZ: [0, 1, 2, 3, 4, 5, 6].map((i) =>
      i <= 3 ? mix(cool, surface, i / 3) : mix(surface, warm, (i - 3) / 3),
    ),
    border: surface,
    // 次要序列（“前 24 小时”这类对比柱）：暗色下 outline-variant 太黑，按面与字混一点
    muted: mix(surface, read('--md-on-surface') || '#1a1c18', theme.value === 'dark' ? 0.3 : 0.16),
    palette: [1, 2, 3, 4, 5, 6].map((i) => read(`--md-chart-${i}`) || line),
    word: { sat: [38, 56], light: theme.value === 'dark' ? [62, 80] : [24, 36] },
  }
}
