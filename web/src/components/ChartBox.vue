<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, default: () => ({}) },
  height: { type: String, default: '280px' },
})

const host = ref(null)
let chart = null
let observer = null

function apply() {
  if (!chart) return
  chart.setOption(props.option, { notMerge: true })
}

onMounted(() => {
  chart = echarts.init(host.value, null, { renderer: 'canvas' })
  apply()
  observer = new ResizeObserver(() => chart && chart.resize())
  observer.observe(host.value)
})

watch(() => props.option, apply, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="host" :style="{ height, width: '100%' }" role="img" aria-label="图表"></div>
</template>
