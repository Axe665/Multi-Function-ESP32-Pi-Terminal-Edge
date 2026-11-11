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
const wordsOff = ref(false)
const anomalies = ref([])
const allAdvice = ref([])
const error = ref('')
const { theme } = useTheme()
const tk = computed(() => chartTokens(theme.value))

const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
const Z_MAX = 2.5

async function loadDevices() {
  devices.value = await api('/devices')
  device.value = devices.value[0]?.device_id || ''
  metrics.value = devices.value[0]?.metrics || []
  metric.value = metrics.value[0]?.metric || ''
}

async function loadHeat() {
  if (!device.value || !metric.value) return
  heat.value = await api(
    `/heatmap?device=${encodeURIComponent(device.value)}&metric=${encodeURIComponent(metric.value)}&days=7`,
  )
}

onMounted(async () => {
  try {
    await loadDevices()
    ;[words.value, anomalies.value, allAdvice.value] = await Promise.all([
      api('/wordcloud?days=7').then((r) => {
        wordsOff.value = Boolean(r.insufficient)
        return r.words || []
      }),
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

const deviceNames = computed(() => devices.value.map((d) => d.name))
const nameOf = (id) => devices.value.find((d) => d.device_id === id)?.name || id

// 每个设备最近 7 天越界窗口数：图上看分布，数字看总量
const counts = computed(() => {
  const m = {}
  for (const a of anomalies.value) m[a.device_id] = (m[a.device_id] || 0) + 1
  return devices.value.map((d) => ({ ...d, count: m[d.device_id] || 0 }))
})

const anomalyOption = computed(() => {
  const names = deviceNames.value
  return {
    grid: { left: 8, right: 12, top: 12, bottom: 28, containLabel: true },
    tooltip: {
      formatter: (p) => {
        const [ts, , z, label, dev] = p.value
        return `${dev}，${label}<br/>${fmtTime(ts)}，z ${z}`
      },
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: tk.value.split } },
      splitLine: { show: false },
      axisLabel: {
        fontSize: 11,
        color: tk.value.axis,
        formatter: (v) => {
          const d = new Date(v)
          return `${d.getMonth() + 1}/${d.getDate()}`
        },
      },
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLine: { lineStyle: { color: tk.value.split } },
      axisLabel: { fontSize: 12, color: tk.value.axis },
    },
    series: [{
      type: 'scatter',
      // 一个点是一个越界窗口，越偏越大；5 分钟窗口在 7 天尺度上会连成段
      symbolSize: (v) => 9 + Math.min(14, Math.abs(v[2]) * 3),
      itemStyle: { color: tk.value.line, opacity: 0.85 },
      data: anomalies.value
        .map((a) => {
          const name = nameOf(a.device_id)
          return [a.ts_from, names.indexOf(name), a.z, a.label, name]
        })
        .filter((row) => row[1] >= 0),
    }],
  }
})

const heatOption = computed(() => {
  const cells = heat.value?.cells || []
  const m = metrics.value.find((x) => x.metric === metric.value)
  // 编码偏差而不是绝对值：均值本身没有对错，对基线的偏离才有
  const data = cells.map((c) => [
    c.hour, c.dow,
    Number(Math.max(-Z_MAX, Math.min(Z_MAX, c.z ?? 0)).toFixed(2)),
  ])
  return {
    grid: { left: 8, right: 8, top: 8, bottom: 44, containLabel: true },
    tooltip: {
      position: 'top',
      formatter: (p) => {
        const c = cells.find((x) => x.hour === p.value[0] && x.dow === p.value[1])
        if (!c) return `${days[p.value[1]]} ${hours[p.value[0]]}：无数据`
        const unit = heat.value?.unit || ''
        return `${days[p.value[1]]} ${hours[p.value[0]]}：00<br/>`
          + `z ${c.z.toFixed(2)}，均值 ${c.mean.toFixed(m?.decimals ?? 1)} ${unit}<br/>`
          + `${c.n} 个窗口`
      },
    },
    xAxis: {
      type: 'category', data: hours, splitArea: { show: false },
      axisLine: { lineStyle: { color: tk.value.split } },
      axisLabel: { fontSize: 11, color: tk.value.axis },
    },
    yAxis: {
      type: 'category', data: days, splitArea: { show: false },
      axisLine: { lineStyle: { color: tk.value.split } },
      axisLabel: { color: tk.value.axis },
    },
    visualMap: {
      min: -Z_MAX, max: Z_MAX, calculable: false, orient: 'horizontal',
      left: 'center', bottom: 0,
      text: ['偏高', '偏低'],
      inRange: { color: tk.value.heatZ },
      textStyle: { fontSize: 11, color: tk.value.axis },
    },
    series: [{ type: 'heatmap', data, itemStyle: { borderColor: tk.value.border, borderWidth: 1 } }],
  }
})

const picked = ref('')
const pickedAdvice = ref([])

function drillWord(p) {
  picked.value = p.name
  pickedAdvice.value = allAdvice.value.filter((a) => (a.text || '').includes(p.name)).slice(0, 6)
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
    series: [{
      type: 'wordCloud',
      shape: 'square',
      left: 0, top: 0, right: 0, bottom: 0,
      sizeRange: [12, 26],
      gridSize: 8,
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
      data: words.value.slice(0, 30).map((w) => ({ name: w.word, value: w.score ?? w.count })),
    }],
  }
})
</script>

<template>
  <PageHeader title="分析" sub="24 h × 7 天时段矩阵按基线偏差着色；异常窗口按设备分行，同一横轴可比。">
    <select v-model="device" class="md-field" aria-label="设备">
      <option v-for="d in devices" :key="d.device_id" :value="d.device_id">{{ d.name }}</option>
    </select>
    <select v-model="metric" class="md-field" aria-label="指标">
      <option v-for="m in metrics" :key="m.metric" :value="m.metric">{{ m.label }}</option>
    </select>
  </PageHeader>

  <p v-if="error" class="error">读不到分析数据：{{ error }}</p>

  <section v-if="wordsOff" class="md-panel sample-off">
    <b>样本不足</b>
    <span class="md-muted">群体分析已关闭，只保留在线与健康计数（当前 {{ devices.length }} 台设备）；热力图、异常与词云都不显示。</span>
  </section>

  <section class="md-panel" v-if="!wordsOff">
    <div class="section-head">
      <h2>时段热力图</h2>
      <span class="md-muted">
        {{ heat?.label }}，色深是相对基线的 z（±2.5 截断）；悬停看均值与窗口数
      </span>
    </div>
    <ChartBox :option="heatOption" height="304px" />
  </section>

  <div class="duo" v-if="!wordsOff">
    <section class="md-panel">
      <div class="section-head">
        <h2>异常窗口</h2>
        <span class="md-muted">连续 2 个窗口 |z| ≥ 2.5，最近 7 天 {{ anomalies.length }} 个</span>
      </div>
      <ChartBox :option="anomalyOption" height="224px" />
      <ul class="counts">
        <li v-for="d in counts" :key="d.device_id">
          <span class="sev" :class="d.count ? 'sev--notice' : 'sev--ok'">
            <span class="sev-dot"></span>{{ d.name }}
          </span>
          <b class="md-num">{{ d.count }}</b>
        </li>
      </ul>
    </section>

    <section class="md-panel">
      <div class="section-head">
        <h2>建议用词</h2>
        <span class="md-muted">最近 7 天，词典分词</span>
      </div>
      <div v-if="wordsOff" class="sample-off">
        <b>样本不足</b>
        <span class="md-muted">群体分析已关闭，词云不显示；开启后才会聚合全体建议文本。</span>
      </div>
      <ChartBox v-else :option="wordOption" height="224px" :on-click="drillWord" />
      <p class="md-muted small">只统计用词频次，不表示严重程度；点词看原文。</p>
    </section>
  </div>

  <section v-if="picked && !wordsOff" class="md-panel drill">
    <div class="section-head">
      <h3>「{{ picked }}」相关的建议</h3>
      <button class="md-btn md-btn--text" @click="picked = ''">收起</button>
    </div>
    <div class="md-list">
      <div v-for="a in pickedAdvice" :key="a.id" class="md-list-row">
        <span class="sev-tag" :class="a.risk === 'alert' ? 'sev-tag--notice' : 'sev-tag--idle'">
          {{ a.risk === 'alert' ? '告警' : '关注' }}
        </span>
        <div class="md-grow">
          <div>{{ a.text }}</div>
          <div class="md-muted small">{{ a.device_id }}，{{ fmtTime(a.created_at) }}</div>
        </div>
      </div>
      <p v-if="!pickedAdvice.length" class="md-muted">没有包含这个词的建议。</p>
    </div>
  </section>
</template>

<style scoped>
.error {
  color: var(--md-error);
  margin-bottom: var(--space-3);
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}
.section-head h2,
.section-head h3 {
  font: var(--md-title-small);
  color: var(--md-on-surface);
}

.duo {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  gap: var(--space-4);
  margin-top: var(--space-4);
  align-items: start;
}
.counts {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--md-card-border);
  list-style: none;
}
.counts li {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}
.counts b {
  font: var(--md-title-small);
  color: var(--md-on-surface);
}

.drill {
  margin-top: var(--space-4);
}
.small {
  font: var(--md-body-small);
}

@media (max-width: 1080px) {
  .duo {
    grid-template-columns: minmax(0, 1fr);
  }
}
.sample-off { min-height: 224px; display: flex; flex-direction: column; gap: 6px;
  align-items: center; justify-content: center; text-align: center; }
</style>
