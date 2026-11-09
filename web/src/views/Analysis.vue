<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, fmtTime } from '../api'
import PageHeader from '../components/PageHeader.vue'
import ChartBox from '../components/ChartBox.vue'
import { chartTokens, useTheme } from '../lib/theme'
import 'echarts-wordcloud'

const devices = ref([])
const device = ref('')
const metrics = ref([])
const metric = ref('')
const heat = ref(null)
const words = ref([])
const anomalies = ref([])
const error = ref('')
const { theme } = useTheme()
const tk = computed(() => chartTokens(theme.value))

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
    ;[words.value, anomalies.value, allAdvice.value] = await Promise.all([
      api('/wordcloud?days=7').then((r) => r.words || []),
      api('/anomalies?days=7').catch(() => []),
      api('/advice?limit=100').catch(() => []),
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

const anomalyOption = computed(() => {
  const rows = anomalies.value.filter((a) => a.device_id === device.value)
  const devs = [...new Set(rows.map((a) => a.device_id))]
  return {
    grid: { left: 8, right: 16, top: 16, bottom: 24, containLabel: true },
    tooltip: {
      formatter: (p) => `${p.value[3]}<br/>${fmtTime(p.value[0])}，z ${p.value[2]}`,
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: tk.value.split } },
      axisLabel: {
        fontSize: 10, color: tk.value.axis,
        formatter: (v) => { const d = new Date(v); return `${d.getMonth() + 1}/${d.getDate()}` },
      },
    },
    yAxis: { type: 'category', data: devs, axisLabel: { fontSize: 11, color: tk.value.axis } },
    series: [{
      type: 'scatter',
      symbolSize: (v) => 8 + Math.min(18, Math.abs(v[2]) * 4),
      itemStyle: { color: tk.value.line, opacity: 0.8 },
      data: rows.map((a, i) => [a.ts_from, devs.indexOf(a.device_id), a.z, a.label]),
    }],
  }
})

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
    xAxis: { type: 'category', data: hours, splitArea: { show: false },
             axisLine: { lineStyle: { color: tk.value.split } },
             axisLabel: { fontSize: 10, color: tk.value.axis } },
    yAxis: { type: 'category', data: days, splitArea: { show: false },
             axisLabel: { color: tk.value.axis } },
    visualMap: {
      min: lo, max: hi, calculable: false, orient: 'horizontal', left: 'center', bottom: 0,
      inRange: { color: tk.value.heat },
      textStyle: { fontSize: 10, color: tk.value.axis },
    },
    series: [{ type: 'heatmap', data, itemStyle: { borderColor: tk.value.border, borderWidth: 1 } }],
  }
})

const picked = ref('')
const pickedAdvice = ref([])
const allAdvice = ref([])

function drillWord(p) {
  picked.value = p.name
  pickedAdvice.value = allAdvice.value.filter((a) => (a.text || '').includes(p.name)).slice(0, 8)
}

const wordOption = computed(() => {
  // 在 computed 里取一次 token：color 回调执行时 Vue 已经不再追踪依赖
  const word = tk.value.word
  return {
    tooltip: {
      formatter: (p) => {
        const w = words.value.find((x) => x.word === p.name)
        return `${p.name}<br/>出现 ${w?.count ?? p.value} 次，覆盖 ${w?.df ?? '—'} 天<br/>点击查看原文`
      },
    },
    series: [
      {
        type: 'wordCloud',
        shape: 'square',
        left: 0, top: 0, right: 0, bottom: 0,
        sizeRange: [15, 36],
        gridSize: 11,
        rotationRange: [0, 0],
        textStyle: {
          fontFamily: 'Roboto, Noto Sans SC, sans-serif',
          fontWeight: 500,
          color: () => {
            const [s0, s1] = word.sat
            const [l0, l1] = word.light
            return `hsl(${112 + Math.random() * 34}, ${s0 + Math.random() * (s1 - s0)}%, ${l0 + Math.random() * (l1 - l0)}%)`
          },
        },
        data: words.value.slice(0, 40).map((w) => ({ name: w.word, value: w.score ?? w.count })),
      },
    ],
  }
})
</script>

<template>
  <PageHeader title="分析" sub="24 h × 7 天时段矩阵、建议词云和异常窗口。数字按聚合表重算。">
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
      <span class="md-muted">{{ heat?.label }}（{{ heat?.unit }}），色深 = 该时段均值</span>
    </div>
    <ChartBox :option="heatOption" height="300px" />
  </section>

  <section class="md-card timeline">
    <div class="section-head">
      <h2>异常时间轴</h2>
      <span class="md-muted">连续 2 个窗口 |z| ≥ 2.5，点越大越偏</span>
    </div>
    <ChartBox :option="anomalyOption" height="220px" />
  </section>

  <div class="duo">
    <section class="md-card">
      <div class="section-head">
        <h2>词云</h2>
        <span class="md-muted">最近 7 天建议文本，词典分词</span>
      </div>
      <ChartBox :option="wordOption" height="300px" :on-click="drillWord" />
      <div v-if="picked" class="drill">
        <div class="section-head">
          <h3>「{{ picked }}」相关的建议</h3>
          <button class="md-btn md-btn--text" @click="picked = ''">收起</button>
        </div>
        <div class="md-list">
          <div v-for="a in pickedAdvice" :key="a.id" class="md-list-row">
            <span class="md-chip" :class="a.risk === 'alert' ? 'md-chip--alert' : 'md-chip--warn'">{{ a.risk }}</span>
            <div class="md-grow">
              <div>{{ a.text }}</div>
              <div class="md-muted small">{{ a.device_id }}，{{ fmtTime(a.created_at) }}</div>
            </div>
          </div>
          <p v-if="!pickedAdvice.length" class="md-muted">没有包含这个词的建议。</p>
        </div>
      </div>
      <p class="md-muted small">
        词云只统计建议文本的用词频次，不表示严重程度；严重程度见右侧异常窗口。
      </p>
    </section>

    <section class="md-card">
      <div class="section-head">
        <h2>异常窗口</h2>
        <span class="md-muted">连续 2 个窗口 |z| ≥ 2.5，最近 {{ anomalies.length }} 条</span>
      </div>
      <div class="md-list">
        <div v-for="(a, i) in anomalies.slice(0, 6)" :key="i" class="md-list-row">
          <div class="md-grow">
            <div>{{ a.label }}</div>
            <div class="md-muted small">{{ a.device_id }}，z {{ a.z }}，均值 {{ a.mean }}</div>
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
.timeline { margin-top: var(--space-4); }
.drill { margin-top: var(--space-3); border-top: 1px solid var(--md-surface-container-highest); padding-top: var(--space-3); }
.small { font: var(--md-body-small); }
@media (max-width: 900px) {
  .duo { grid-template-columns: minmax(0, 1fr); }
}
</style>
