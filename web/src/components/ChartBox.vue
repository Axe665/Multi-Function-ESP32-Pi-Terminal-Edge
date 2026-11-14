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
          backgroundColor: token('--md-surface-container-high', '#282b25'),
          borderColor: token('--md-outline-variant', '#43483e'),
          borderWidth: 1,
          textStyle: { fontSize: 13, color: token('--md-on-surface', '#e3e3dc') },
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
