<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, fmtTime } from '../api'
import PageHeader from '../components/PageHeader.vue'
import ChartBox from '../components/ChartBox.vue'
import 'echarts-wordcloud'

const devices = ref([])
const device = ref('')
const metrics = ref([])
const metric = ref('')
const heat = ref(null)
const words = ref([])
const anomalies = ref([])
const error = ref('')

const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))

async function loadDevices() {
  devices.value = await api('/devices')
  device.value = devices.value[0]?.device_id || ''
  metrics.value = devices.value[0]?.metrics || []
  metric.value = metrics.value[0]?.metric || ''
}

async function loadHeat() {
  if (!device.value || !metric.value) return
  heat.value = await api(`/heatmap?device=${encodeURIComponent(device.value)}&metric=${encodeURIComponent(metric.value)}&days=7`)
}

onMounted(async () => {
  try {
    await loadDevices()
    ;[words.value, anomalies.value] = await Promise.all([
      api('/wordcloud?days=7').then((r) => r.words || []),
      api('/anomalies?days=7').catch(() => []),
    ])
    await loadHeat()
  } catch (e) {
    error.value = e.message
  }
})

watch(device, (v) => {
  const d = devices.value.find((x) => x.device_id === v)
  metrics.value = d?.metrics || []
  metric.value = metrics.value[0]?.metric || ''
})
watch([device, metric], loadHeat)

const heatOption = computed(() => {
  const cells = heat.value?.cells || []
  const m = metrics.value.find((x) => x.metric === metric.value)
  const data = cells.map((c) => [c.hour, c.dow, c.mean === null ? '-' : Number(c.mean.toFixed(m?.decimals ?? 1))])
  const values = cells.filter((c) => c.mean !== null).map((c) => c.mean)
  // 没有数据时也要给 visualMap 一对合法数字，否则 ECharts 拿 NaN 去构造渐变会报错
  const lo = values.length ? Math.min(...values) : 0
  const hi = values.length ? Math.max(...values) : 1
  return {
    grid: { left: 8, right: 8, top: 8, bottom: 40, containLabel: true },
    tooltip: {
      position: 'top',
      formatter: (p) => `${days[p.value[1]]} ${hours[p.value[0]]}:00<br/>${p.value[2]} ${heat.value?.unit || ''}`,
    },
    xAxis: { type: 'category', data: hours, splitArea: { show: false }, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'category', data: days, splitArea: { show: false } },
    visualMap: {
      min: lo, max: hi, calculable: false, orient: 'horizontal', left: 'center', bottom: 0,
      inRange: { color: ['#e3e6dc', '#9cd67e', '#386a20'] },
      textStyle: { fontSize: 10 },
    },
    series: [{ type: 'heatmap', data, itemStyle: { borderColor: '#fbfdf6', borderWidth: 1 } }],
  }
})

const wordOption = computed(() => ({
  tooltip: { formatter: (p) => `${p.name}：${p.value}` },
  series: [
    {
      type: 'wordCloud',
      shape: 'square',
      left: 0, top: 0, right: 0, bottom: 0,
      sizeRange: [13, 30],
      rotationRange: [0, 0],
      textStyle: {
        fontFamily: 'Roboto, Noto Sans SC, sans-serif',
        color: () => `hsl(${105 + Math.random() * 40}, ${25 + Math.random() * 20}%, ${28 + Math.random() * 22}%)`,
      },
      data: words.value.slice(0, 40).map((w) => ({ name: w.word, value: w.count })),
    },
  ],
}))
</script>

<template>
  <PageHeader title="分析" sub="24 h × 7 天的时段矩阵、建议词云和异常窗口。全部数字来自聚合表重算。">
    <select v-model="device" class="md-field" aria-label="设备">
      <option v-for="d in devices" :key="d.device_id" :value="d.device_id">{{ d.name }}</option>
    </select>
    <select v-model="metric" class="md-field" aria-label="指标">
      <option v-for="m in metrics" :key="m.metric" :value="m.metric">{{ m.label }}</option>
    </select>
  </PageHeader>

  <p v-if="error" class="error">{{ error }}</p>

  <section class="md-card">
    <div class="section-head">
      <h2>时段热力图</h2>
      <span class="md-muted">{{ heat?.label }}（{{ heat?.unit }}） · 色深 = 该时段均值</span>
    </div>
    <ChartBox :option="heatOption" height="300px" />
  </section>

  <div class="duo">
    <section class="md-card">
      <div class="section-head">
        <h2>词云</h2>
        <span class="md-muted">最近 7 天建议文本 · 词典分词</span>
      </div>
      <ChartBox :option="wordOption" height="260px" />
      <p class="md-muted small">
        词云只反映建议文本的用词频次，不代表严重程度；严重程度看右侧的异常窗口。
      </p>
    </section>

    <section class="md-card">
      <div class="section-head">
        <h2>异常窗口</h2>
        <span class="md-muted">|z| ≥ 2.5 · 最近 {{ anomalies.length }} 条</span>
      </div>
      <div class="md-list">
        <div v-for="(a, i) in anomalies.slice(0, 6)" :key="i" class="md-list-row">
          <div class="md-grow">
            <div>{{ a.label }}</div>
            <div class="md-muted small">{{ a.device_id }} · z {{ a.z }} · 均值 {{ a.mean }}</div>
          </div>
          <span class="md-mono md-muted">{{ fmtTime(a.ts_from) }}</span>
        </div>
        <p v-if="!anomalies.length" class="md-muted">最近 7 天没有超过 2.5σ 的窗口。</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.error { color: var(--md-error); margin-bottom: var(--space-3); }
.section-head {
  display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-3);
  margin-bottom: var(--space-3); flex-wrap: wrap;
}
.duo {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-4);
  margin-top: var(--space-4); align-items: start;
}
.small { font: var(--md-body-small); }
@media (max-width: 900px) {
  .duo { grid-template-columns: minmax(0, 1fr); }
}
</style>
