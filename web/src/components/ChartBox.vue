<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { useTheme } from '../lib/theme'

const props = defineProps({
  option: { type: Object, default: () => ({}) },
  height: { type: String, default: '280px' },
  label: { type: String, default: '图表' },
})

const host = ref(null)
const { theme } = useTheme()
let chart = null
let observer = null

function apply() {
  if (!chart) return
  const base = props.option || {}
  // tooltip 是 ECharts 自己画的，不读 CSS 变量；色值仍从 token 取，保持一处来源
  const css = getComputedStyle(document.documentElement)
  const token = (name, fallback) => css.getPropertyValue(name).trim() || fallback
  const option = base.tooltip
    ? {
        ...base,
        tooltip: {
          backgroundColor: token('--md-surface-container-high', '#1e1e1e'),
          borderColor: token('--md-outline-variant', '#3a3a3a'),
          borderWidth: 1,
          padding: [8, 12],
          confine: true,
          textStyle: { fontSize: 12, color: token('--md-on-surface', '#eaeaea'), lineHeight: 20 },
          extraCssText: 'border-radius: 10px; box-shadow: 0 6px 16px rgba(0, 0, 0, 0.18);',
          ...base.tooltip,
        },
      }
    : base
  chart.setOption({ backgroundColor: 'transparent', ...option }, { notMerge: true })
}

onMounted(() => {
  chart = echarts.init(host.value, null, { renderer: 'canvas' })
  apply()
  observer = new ResizeObserver(() => chart && chart.resize())
  observer.observe(host.value)
})

watch(() => props.option, apply, { deep: true })
watch(theme, apply)

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="host" :style="{ height, width: '100%' }" role="img" :aria-label="label"></div>
</template>
