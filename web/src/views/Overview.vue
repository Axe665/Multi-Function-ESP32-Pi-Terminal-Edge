<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, fmtNum, fmtTime } from '../api'
import { chartTokens, useTheme } from '../lib/theme'
import PageLead from '../components/PageLead.vue'
import StatusBar from '../components/StatusBar.vue'
import AlertList from '../components/AlertList.vue'
import ChartBox from '../components/ChartBox.vue'

const o = ref(null)
const alerts = ref([])
const advice = ref([])
const devices = ref([])
const heat = ref(null)
const lines = ref([])
const error = ref('')
let timer = 0
const router = useRouter()
const { theme } = useTheme()
const tk = computed(() => chartTokens(theme.value))

async function load() {
  try {
    const [over, al, adv, dev] = await Promise.all([
      api('/overview'),
      api('/alerts').catch(() => []),
      api('/advice?limit=100').catch(() => []),
      api('/devices').catch(() => []),
    ])
    o.value = over
    alerts.value = al
    advice.value = adv
    devices.value = dev
    error.value = ''
    await loadCharts(over, dev)
  } catch (e) {
    error.value = e.message
  }
}

async function loadCharts(over, dev) {
  const lanes = over?.lanes || []
  if (over?.insufficient) { lines.value = []; heat.value = null; return }
  const first = lanes[0]
  if (first) {
    const metric = (first.metrics || [])[0]?.metric
    if (metric) {
      heat.value = await api(
        `/heatmap?device=${encodeURIComponent(first.device_id)}&metric=${encodeURIComponent(metric)}&days=7`,
      ).catch(() => null)
    }
  }
  const rows = await Promise.all(lanes.map(async (lane) => {
    const metric = (lane.metrics || [])[0]
    if (!metric) return { lane, points: [], metric: null }
    const s = await api(
      `/devices/${encodeURIComponent(lane.device_id)}/series?metric=${encodeURIComponent(metric.metric)}&hours=24`,
    ).catch(() => null)
    return { lane, metric, points: s?.points || [] }
  }))
  lines.value = rows
}

onMounted(async () => {
  await load()
  timer = setInterval(load, 20000)
})
onBeforeUnmount(() => clearInterval(timer))

const status = computed(() => o.value?.status || { level: 'ok' })

const headline = computed(() => {
  const v = o.value
  if (!v) return '总览'
  const s = v.status
  if (s.level === 'critical') {
    return s.stale_devices && s.stale_devices === s.critical
      ? `${s.stale_devices} 台设备掉线`
      : `${s.critical} 条严重异常待处理`
  }
  if (s.level === 'notice') return `${s.notice} 条异常待确认`
  const handled = (s.acked || 0) + (s.muted || 0)
  return `${v.devices_online}/${v.devices_total} 台在线，${handled ? `${handled} 条已处理` : '没有待处理异常'}`
})

const sub = computed(() => {
  const v = o.value
  if (!v) return ''
  return `${v.edge_name}，5 分钟聚合窗口，k≥5 才入库；更新于 ${fmtTime(v.generated_at, true)}`
})

// 1. 链路 24 窗口
const lanesOption = computed(() => {
  const t = tk.value
  const lanes = o.value?.lanes || []
  const data = []
  lanes.forEach((lane, y) => {
    lane.ticks.forEach((v, x) => data.push([x, y, v]))
  })
  const hours = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
  return {
    grid: { left: 4, right: 8, top: 6, bottom: 22, containLabel: true },
    tooltip: { formatter: (p) => `${lanes[p.value[1]]?.name || ''}<br/>${p.value[2] ? '已收到' : '缺这个窗口'}` },
    xAxis: { type: 'category', data: hours, axisLabel: { fontSize: 12, color: t.axis, interval: 3 },
             axisLine: { show: false }, axisTick: { show: false } },
    yAxis: { type: 'category', data: lanes.map((l) => l.name), axisLabel: { fontSize: 12, color: t.text, interval: 0 },
             axisLine: { show: false }, axisTick: { show: false } },
    visualMap: { show: false, min: 0, max: 1, inRange: { color: [t.split, t.line] } },
    series: [{ type: 'heatmap', data, itemStyle: { borderRadius: 2, borderColor: t.border, borderWidth: 1 } }],
  }
})

// 2. 每设备 24h 走势（小倍数，同一面板）
const spark = computed(() => lines.value.map(({ lane, metric, points }) => {
  // 24h 是 288 个点，全画出来是一条毛线；抽到 ~96 个点，趋势才看得出
  const step = Math.max(1, Math.ceil(points.length / 96))
  const pts = points.filter((_, i) => i % step === 0)
  const vals = pts.map((p) => p.mean)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const span = max - min || 1
  const d = pts.map((p, i) => {
    const x = (i / Math.max(1, pts.length - 1)) * 100
    const y = 28 - ((p.mean - min) / span) * 24
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')
  return {
    name: lane.name, metric,
    last: pts.length ? `${fmtNum(pts[pts.length - 1].mean, metric?.decimals ?? 1)}${metric?.unit || ''}` : '—',
    range: pts.length ? `${fmtNum(min, metric?.decimals ?? 1)}–${fmtNum(max, metric?.decimals ?? 1)}${metric?.unit || ''}` : '',
    d, color: tk.value.line, unit: metric?.unit || '',
  }
}))

// 3. 7×24 异常热力
const heatOption = computed(() => {
  const t = tk.value
  const cells = heat.value?.cells || []
  const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
  return {
    grid: { left: 4, right: 8, top: 2, bottom: 18, containLabel: true },
    tooltip: {
      formatter: (p) => `${days[p.value[1]]} ${String(p.value[0]).padStart(2, '0')}:00<br/>z ${p.value[2].toFixed(2)}`,
    },
    xAxis: { type: 'category', data: Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0')),
             axisLabel: { fontSize: 10, color: t.axis, interval: 3 }, axisLine: { show: false }, axisTick: { show: false } },
    // 7 行挤在 ~100px 里，两个字会叠在一起；轴上只留「日/一/二」，完整星期名放 tooltip
    yAxis: { type: 'category', data: days.map((d) => d[1]), axisLabel: { fontSize: 10, color: t.axis, interval: 0 },
             axisLine: { show: false }, axisTick: { show: false } },
    visualMap: { show: false, min: -2.5, max: 2.5, inRange: { color: t.heatZ } },
    series: [{
      type: 'heatmap',
      data: cells.map((c) => [c.hour, c.dow, Math.max(-2.5, Math.min(2.5, c.z || 0))]),
      itemStyle: { borderRadius: 2, borderColor: t.border, borderWidth: 1 },
    }],
  }
})

// 4. 建议风险分布
const riskOption = computed(() => {
  const t = tk.value
  const rows = advice.value || []
  const counts = { alert: 0, watch: 0, info: 0 }
  for (const a of rows) counts[a.risk] = (counts[a.risk] || 0) + 1
  const labels = ['告警', '关注', '提示']
  const data = [counts.alert, counts.watch, counts.info]
  const step = Math.max(1, Math.ceil(Math.max(...data, 1) / 3))
  return {
    grid: { left: 4, right: 26, top: 6, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', max: step * 3, interval: step, splitLine: { lineStyle: { color: t.split } }, axisLabel: { fontSize: 12, color: t.axis } },
    yAxis: { type: 'category', data: labels, axisLabel: { fontSize: 13, color: t.text },
             axisLine: { show: false }, axisTick: { show: false } },
    series: [{
      type: 'bar', data, barWidth: '58%',
      itemStyle: { color: (p) => [t.critical, t.notice, t.line][p.dataIndex], borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', fontSize: 12, color: t.axis },
    }],
  }
})

// 5. 24h 对比
const deltaOption = computed(() => {
  const t = tk.value
  const v = o.value || {}
  const rows = [
    { label: '批次数', cur: v.batches_24h || 0, prev: v.batches_prev_24h || 0 },
    { label: '建议数', cur: v.advice_24h || 0, prev: v.advice_prev_24h || 0 },
  ]
  return {
    grid: { left: 4, right: 8, top: 28, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, itemWidth: 8, itemHeight: 8, textStyle: { fontSize: 12, color: t.axis } },
    xAxis: { type: 'category', data: rows.map((r) => r.label), axisLabel: { fontSize: 12, color: t.axis },
             axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false } },
    yAxis: { type: 'value', splitNumber: 3, splitLine: { lineStyle: { color: t.split } }, axisLabel: { fontSize: 12, color: t.axis } },
    series: [
      // 只有 2 个类目：不给上限 58% 会撑到 100px 以上，两根柱贴在一起把类目标签夹住
      { name: '近 24 小时', type: 'bar', data: rows.map((r) => r.cur), barWidth: '58%', barMaxWidth: 32,
        itemStyle: { color: t.line, borderRadius: [4, 4, 0, 0] } },
      { name: '前 24 小时', type: 'bar', data: rows.map((r) => r.prev), barWidth: '58%', barMaxWidth: 32,
        itemStyle: { color: t.muted, borderRadius: [4, 4, 0, 0] } },
    ],
  }
})

// 6. 指标覆盖：每个指标有几台设备在报
const coverOption = computed(() => {
  const t = tk.value
  const devs = devices.value || []
  const metrics = [...new Set(devs.flatMap((d) => (d.metrics || []).map((m) => m.metric)))].sort()
  const counts = metrics.map((m) => ({
    metric: m,
    label: devs.flatMap((d) => (d.metrics || [])).find((x) => x.metric === m)?.label || m,
    devices: devs.filter((d) => (d.metrics || []).some((x) => x.metric === m)).map((d) => d.device_id),
  }))
  return {
    grid: { left: 4, right: 26, top: 6, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (p) => `${counts[p[0].dataIndex].label}<br/>${counts[p[0].dataIndex].devices.join('，')}`,
    },
    xAxis: { type: 'value', max: Math.max(1, devs.length), minInterval: 1,
             splitLine: { lineStyle: { color: t.split } }, axisLabel: { fontSize: 12, color: t.axis } },
    yAxis: { type: 'category', data: counts.map((c) => c.label), axisLabel: { fontSize: 13, color: t.text },
             axisLine: { show: false }, axisTick: { show: false } },
    series: [{
      type: 'bar', data: counts.map((c) => c.devices.length), barWidth: '58%',
      itemStyle: { color: t.line, borderRadius: [0, 4, 4, 0] },
      label: {
        show: true, position: 'right', fontSize: 12, color: t.axis,
        formatter: (p) => `${p.value}/${devs.length}`,
      },
    }],
  }
})

const adviceRows = computed(() => {
  const seen = new Map()
  for (const a of advice.value) {
    const hit = seen.get(a.text)
    if (hit) { hit.count += 1; continue }
    seen.set(a.text, { ...a, count: 1 })
  }
  return [...seen.values()].slice(0, 5)
})

</script>

<template>
  <p v-if="error" class="error">读不到总览：{{ error }}</p>

  <PageLead sub="5 分钟聚合窗口，k≥5 才入库；点设备进详情">
    <button class="md-btn md-btn--tonal" @click="load">刷新</button>
    <RouterLink class="md-btn" to="/settings">上云设置</RouterLink>
  </PageLead>

  <div class="md-grid dense">
    <StatusBar :status="status" :title="headline" :sub="sub" />

    <section v-if="o?.insufficient" class="md-card span-12">
      <div class="md-card-head">
        <h2>样本不足</h2>
        <span class="meta">{{ o.reason }}</span>
      </div>
      <p class="md-muted">
        当前 {{ o.devices_online }}/{{ o.devices_total }} 台在线，告警 {{ o.status?.critical }} 条严重、
        {{ o.status?.notice }} 条待确认。开启群体分析后才会显示分设备的走势与聚合。
      </p>
      <RouterLink class="md-btn md-btn--tonal" to="/settings">去设置里开启群体分析</RouterLink>
    </section>

    <template v-else>
      <section class="md-card span-8 card-b">
        <div class="md-card-head">
          <h2>链路 · 最近 24 个窗口</h2>
          <span class="meta">实心格为已收到</span>
        </div>
        <div class="chart-fill">
          <ChartBox :option="lanesOption" height="100%" label="各设备最近 24 个窗口的收取情况"
                    @click="router.push('/devices')" />
        </div>
      </section>

      <aside class="md-card span-4 card-b">
        <div class="md-card-head">
          <h2>待处理</h2>
          <span class="meta">{{ o ? alerts.length : '—' }} 条</span>
        </div>
        <AlertList :alerts="alerts" :limit="3" @changed="load" />
      </aside>

      <section class="md-card span-8 card-c">
        <div class="md-card-head">
          <h2>每设备 24h 走势</h2>
          <span class="meta">各自主指标，独立刻度</span>
        </div>
        <div class="spark-list">
          <div v-for="s in spark" :key="s.name" class="spark-row">
            <span class="spark-name">{{ s.name }}</span>
            <svg class="spark" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true">
              <line x1="0" y1="16" x2="100" y2="16" :stroke="tk.split" stroke-width="1" vector-effect="non-scaling-stroke" />
              <polyline :points="s.d" fill="none" :stroke="s.color" stroke-width="1.4"
                        vector-effect="non-scaling-stroke"
                        stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <span class="spark-val">
              <b class="md-num">{{ s.last }}</b>
              <span class="md-muted">{{ s.range }}</span>
            </span>
          </div>
          <p v-if="!spark.length" class="md-muted">没有可画的序列。</p>
        </div>
      </section>

      <section class="md-card span-4 card-c">
        <div class="md-card-head">
          <h2>最近建议</h2>
          <span class="meta">{{ o?.advice_24h ?? 0 }} 条 / 24 h</span>
        </div>
        <div class="md-list">
          <div v-for="a in adviceRows.slice(0, 3)" :key="a.id" class="advice-row">
            <span class="sev-tag" :class="a.risk === 'alert' ? 'sev-tag--notice' : 'sev-tag--idle'">
              {{ a.risk === 'alert' ? '告警' : '关注' }}
            </span>
            <div class="md-grow">
              <div class="advice-text">{{ a.text }}</div>
              <div class="md-muted small">{{ a.device_id }}，{{ fmtTime(a.created_at) }}</div>
            </div>
          </div>
          <p v-if="!adviceRows.length" class="md-muted">今天没有建议。</p>
        </div>
      </section>

      <section class="md-card span-4 card-d">
        <div class="md-card-head">
          <h2>7×24 异常</h2>
          <span class="meta">{{ heat?.label || '—' }} 相对基线 z</span>
        </div>
        <div class="chart-fill"><ChartBox :option="heatOption" height="100%" label="按星期与小时统计的异常热力" /></div>
      </section>

      <section class="md-card span-4 card-d">
        <div class="md-card-head">
          <h2>建议风险分布</h2>
          <span class="meta">最近 100 条</span>
        </div>
        <div class="chart-fill"><ChartBox :option="riskOption" height="100%" label="建议按风险等级的条数" /></div>
      </section>

      <section class="md-card span-4 card-d">
        <div class="md-card-head">
          <h2>24h 对比</h2>
          <span class="meta">相对前 24 小时</span>
        </div>
        <div class="chart-fill"><ChartBox :option="deltaOption" height="100%" label="近 24 小时与前 24 小时对比" /></div>
      </section>

      <section class="md-card span-12 card-e">
        <div class="md-card-head">
          <h2>指标覆盖</h2>
          <span class="meta">每个指标有几台设备在报</span>
        </div>
        <div class="chart-fill"><ChartBox :option="coverOption" height="100%" label="每个指标上报的设备数" /></div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.error {
  color: var(--md-error);
  max-width: var(--content-max);
  margin: 0 auto var(--space-3);
}
.dense {
  gap: var(--space-3);
}
/* 整屏不滚动：每行给固定高度，图表撑满剩下的空间 */
.card-b, .card-c, .card-d, .card-e {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.card-b { height: 170px; }
.card-c { height: 194px; }
.card-d { height: 194px; }
.card-e { height: 144px; }
.chart-fill {
  flex: 1;
  min-height: 0;
}
.chart-fill > :deep(div) {
  height: 100%;
}

.spark-list {
  display: flex;
  flex-direction: column;
  justify-content: space-around;
  gap: var(--space-1);
  flex: 1;
  min-height: 0;
}
.spark-row {
  display: grid;
  grid-template-columns: minmax(110px, auto) minmax(0, 1fr) minmax(96px, auto);
  align-items: center;
  gap: var(--space-3);
}
.spark-name {
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.spark { width: 100%; height: 26px; display: block; overflow: visible; }
.spark-val { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.2; }
.spark-val b { font: var(--md-label-large); color: var(--md-on-surface); }
.spark-val span { font: var(--md-label-small); }

.advice-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: 3px 0;
}
.advice-text {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font: var(--md-body-small);
}
.small { font: var(--md-body-small); }
</style>
