<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, fmtTime } from '../api'
import PageLead from '../components/PageLead.vue'
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
  // 只有一个跨度的数据时，只显示日期会让轴上全是同一天
  const ts = anomalies.value.map((a) => a.ts_from)
  const span = ts.length ? Math.max(...ts) - Math.min(...ts) : 0
  const short = span < 2 * 86_400_000
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
          const day = `${d.getMonth() + 1}/${d.getDate()}`
          return short ? `${day} ${String(d.getHours()).padStart(2, '0')}:00` : day
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
  <p v-if="error" class="error">读不到分析数据：{{ error }}</p>

  <PageLead sub="24 h × 7 天时段矩阵按基线偏差着色；异常窗口按设备分行，同一横轴可比。">
    <label class="md-field pick">
      <span>设备</span>
      <select v-model="device">
        <option v-for="d in devices" :key="d.device_id" :value="d.device_id">{{ d.name }}</option>
      </select>
    </label>
    <label class="md-field pick">
      <span>指标</span>
      <select v-model="metric">
        <option v-for="m in metrics" :key="m.metric" :value="m.metric">{{ m.label }}</option>
      </select>
    </label>
  </PageLead>

  <div class="md-grid">
    <section v-if="wordsOff" class="md-card span-12">
      <b>样本不足</b>
      <p class="md-muted">
        群体分析已关闭，只保留在线与健康计数（当前 {{ devices.length }} 台设备）；热力图、异常与词云都不显示。
      </p>
    </section>

    <template v-if="!wordsOff">
      <section class="md-card span-12">
        <div class="md-card-head">
          <h2>时段热力图</h2>
          <span class="meta">
            {{ heat?.label }}，色深是相对基线的 z（±2.5 截断）；悬停看均值与窗口数
          </span>
        </div>
        <ChartBox :option="heatOption" height="320px" label="24 小时乘 7 天的时段热力图" />
      </section>

      <section class="md-card span-7">
        <div class="md-card-head">
          <h2>异常窗口</h2>
          <span class="meta">连续 2 个窗口 |z| ≥ 2.5，最近 7 天 {{ anomalies.length }} 个</span>
        </div>
        <ChartBox :option="anomalyOption" height="224px" label="各设备的异常窗口" />
        <ul class="counts">
          <li v-for="d in counts" :key="d.device_id">
            <span class="sev" :class="d.count ? 'sev--notice' : 'sev--ok'">
              <span class="sev-dot"></span>{{ d.name }}
            </span>
            <b class="md-num">{{ d.count }}</b>
          </li>
        </ul>
      </section>

      <section class="md-card span-5">
        <div class="md-card-head">
          <h2>建议用词</h2>
          <span class="meta">最近 7 天，词典分词</span>
        </div>
        <ChartBox :option="wordOption" height="224px" :on-click="drillWord" label="建议文本的词云" />
        <p class="md-muted small hint">只统计用词频次，不表示严重程度；点词看原文。</p>
      </section>

      <section v-if="picked" class="md-card span-12">
        <div class="md-card-head">
          <h3>「{{ picked }}」相关的建议</h3>
          <button class="md-btn md-btn--text" @click="picked = ''">收起</button>
        </div>
        <div class="md-list">
          <div v-for="a in pickedAdvice" :key="a.id" class="md-list-item">
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
  </div>
</template>

<style scoped>
.error { color: var(--md-error); max-width: var(--content-max); margin: 0 auto var(--space-3); }
.pick { width: 220px; }
.counts {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--md-outline-variant);
  list-style: none;
}
.counts li { display: flex; align-items: baseline; gap: var(--space-2); }
.counts b { font: var(--md-title-small); color: var(--md-on-surface); }
.small { font: var(--md-body-small); }
.hint { margin-top: var(--space-2); }
</style>
