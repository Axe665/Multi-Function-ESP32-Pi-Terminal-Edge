<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, fmtNum, fmtTime } from '../api'
import { createFlow } from '../lib/flow'
import StatusBar from '../components/StatusBar.vue'
import AlertList from '../components/AlertList.vue'

const o = ref(null)
const alerts = ref([])
const advice = ref([])
const error = ref('')
const flowHost = ref(null)
let flow = null
let timer = 0

async function load() {
  try {
    const [over, al, adv] = await Promise.all([
      api('/overview'),
      api('/alerts').catch(() => []),
      api('/advice?limit=5').catch(() => []),
    ])
    o.value = over
    alerts.value = al
    advice.value = adv
    error.value = ''
    flow?.setData?.({
      batches: over.batches_24h,
      suppressed: over.suppressed_buckets,
      alerts: over.alerts_24h,
      online: over.lanes.map((l) => l.online),
    })
  } catch (e) {
    error.value = e.message
  }
}

onMounted(async () => {
  if (flowHost.value) flow = createFlow(flowHost.value)
  await load()
  timer = setInterval(load, 15000)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  flow?.destroy?.()
})

const status = computed(() => o.value?.status || { level: 'ok' })

// 结论先给，数字后给；颜色只是辅助
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

const pct = (cur, prev) => (prev ? Math.round(((cur - prev) / prev) * 100) : null)

const measures = computed(() => {
  const v = o.value
  if (!v) return []
  return [
    { label: '24 h 批次', value: fmtNum(v.batches_24h, 0),
      delta: pct(v.batches_24h, v.batches_prev_24h), note: '按批次去重' },
    { label: '24 h 建议', value: fmtNum(v.advice_24h, 0),
      delta: pct(v.advice_24h, v.advice_prev_24h),
      note: `其中告警 ${v.alerts_24h}` },
    { label: '最小 k', value: String(v.k_min || '—'), delta: null,
      note: '低于 5 的桶只在端内使用' },
  ]
})

const risky = (r) => r === 'alert'

// 同一句话在一批窗口里会重复出现，按文本合并，只留条数
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

  <StatusBar :status="status" :title="headline" :sub="sub">
    <template #actions>
      <button class="md-btn md-btn--tonal" @click="load">刷新</button>
      <RouterLink class="md-btn" to="/settings">上云设置</RouterLink>
    </template>
  </StatusBar>

  <div class="top">
    <div class="main">
    <section class="md-panel">
      <div class="section-head">
        <h2>待处理</h2>
        <span class="md-muted">{{ alerts.length }} 条</span>
      </div>
      <AlertList :alerts="alerts" :limit="4" @changed="load" />
      <RouterLink v-if="alerts.length > 4" class="more" to="/analysis">
        全部 {{ alerts.length }} 条 →
      </RouterLink>
    </section>

    <section class="md-panel">
      <div class="section-head">
        <h2>链路</h2>
        <span class="md-muted">最近 24 个 5 分钟窗口，实心格为已收到</span>
      </div>
      <div class="lanes">
        <article v-for="lane in o?.lanes || []" :key="lane.device_id" class="lane">
          <div class="lane-row">
            <div class="lane-id">
              <strong>{{ lane.name }}</strong>
              <span class="sev" :class="lane.online ? 'sev--ok' : 'sev--critical'">
                <span class="sev-dot"></span>{{ lane.online ? '在线' : '掉线' }}
              </span>
              <span class="md-mono md-muted">{{ lane.device_id }}</span>
            </div>
            <div class="ticks" :aria-label="`${lane.device_id} 最近 24 个窗口`">
              <span v-for="(t, i) in lane.ticks" :key="i" class="tick" :class="{ 'tick--on': t }"></span>
            </div>
            <div class="lane-meta">
              <span>{{ fmtTime(lane.last_seen) }}</span>
              <span>k {{ lane.k }}</span>
              <span>{{ lane.fill }}%</span>
            </div>
          </div>
          <div class="lane-metrics">
            <span v-for="m in lane.metrics.slice(0, 4)" :key="m.metric">
              {{ m.label }} <b class="md-num">{{ fmtNum(m.mean, m.decimals) }}{{ m.unit }}</b>
            </span>
          </div>
        </article>
      </div>
    </section>
    </div>

    <div class="side">
      <section class="md-panel thumb">
        <div class="section-head">
          <h2>数据流</h2>
          <span class="md-chip" :class="o?.cloud_ok ? 'md-chip--ok' : 'md-chip--warn'">
            {{ o?.cloud_ok ? '云端可达' : '云端未连' }}
          </span>
        </div>
        <canvas ref="flowHost" class="flow-canvas" aria-hidden="true"></canvas>
        <p class="thumb-note">端 → k≥5 聚合环 → 云，熄掉的粒子是被抑制的桶</p>
      </section>

      <section class="md-panel">
        <div class="section-head">
          <h2>近 24 小时</h2>
          <span class="md-muted">相对前 24 小时</span>
        </div>
        <dl class="measures">
          <div v-for="m in measures" :key="m.label">
            <dt>{{ m.label }}</dt>
            <dd>
              <span class="md-num">{{ m.value }}</span>
              <span v-if="m.delta" class="delta" :class="m.delta > 0 ? 'up' : 'down'">
                {{ m.delta > 0 ? '+' : '' }}{{ m.delta }}%
              </span>
              <span v-else-if="m.delta === 0" class="delta flat">持平</span>
              <span class="note">{{ m.note }}</span>
            </dd>
          </div>
        </dl>
      </section>
    </div>
  </div>

  <div class="bottom">
    <section class="md-section">
      <div class="section-head">
        <h2>最近建议</h2>
        <span class="md-muted">最近 5 条，24 h 共 {{ o?.advice_24h ?? 0 }} 条</span>
      </div>
      <div class="md-list">
        <div v-for="a in adviceRows" :key="a.id" class="md-list-row">
          <span class="sev-tag" :class="risky(a.risk) ? 'sev-tag--notice' : 'sev-tag--idle'">
            {{ risky(a.risk) ? '告警' : '关注' }}
          </span>
          <div class="md-grow">
            <div>{{ a.text }}</div>
            <div class="md-muted small">
              {{ a.device_id }}，{{ fmtTime(a.created_at) }}<template v-if="a.count > 1">，近 5 条里出现 {{ a.count }} 次</template>
            </div>
          </div>
        </div>
        <p v-if="!adviceRows.length" class="md-muted">今天没有建议。</p>
      </div>
    </section>

    <section class="md-section">
      <div class="section-head">
        <h2>近 24 小时的变化</h2>
      </div>
      <div class="md-list">
        <div v-for="f in o?.findings || []" :key="f.metric" class="md-list-row">
          <div class="md-grow">
            <div>{{ f.text }}</div>
            <div class="md-muted small">
              {{ f.label }}，{{ f.delta > 0 ? '+' : '' }}{{ fmtNum(f.delta, 2) }}{{ f.unit }}
            </div>
          </div>
          <span class="md-num md-muted">
            {{ f.pct > 0 ? '+' : '' }}{{ fmtNum(f.pct, 1) }}%
          </span>
        </div>
        <p v-if="!o?.findings?.length" class="md-muted empty">数据不足，暂不生成结论。</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.error {
  color: var(--md-error);
  margin-bottom: var(--space-3);
}

.main {
  display: grid;
  gap: var(--space-4);
  align-content: start;
}
.top {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(280px, 1fr);
  gap: var(--space-4);
  margin-top: var(--space-4);
  align-items: stretch;
}
.side {
  display: grid;
  gap: var(--space-4);
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}
.section-head h2 {
  font: var(--md-title-small);
  color: var(--md-on-surface);
}

.more {
  display: inline-block;
  margin-top: var(--space-2);
  font: var(--md-label-large);
  color: var(--md-primary);
}

.flow-canvas {
  width: 100%;
  height: 116px;
  display: block;
  border-radius: var(--md-shape-sm);
}
.thumb-note {
  margin-top: var(--space-1);
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}

.measures {
  display: grid;
  gap: var(--space-2);
}
.measures div {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: baseline;
  gap: var(--space-2);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--md-card-border);
}
.measures div:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}
.measures dt {
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}
.measures dd {
  text-align: right;
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  justify-content: flex-end;
  flex-wrap: wrap;
}
.measures .md-num {
  font: var(--md-title-medium);
  color: var(--md-on-surface);
}
.delta {
  font: var(--md-label-medium);
}
.delta.up { color: var(--md-ok); }
.delta.down { color: var(--md-notice); }
.delta.flat { color: var(--md-on-surface-variant); }
.note {
  flex-basis: 100%;
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}

.lanes {
  display: grid;
}
.lane {
  padding: var(--space-2) 0;
  border-top: 1px solid var(--md-card-border);
}
.lane:first-child {
  border-top: 0;
}
.lane-row {
  display: grid;
  grid-template-columns: minmax(250px, 1.3fr) minmax(120px, 1.2fr) auto;
  align-items: center;
  gap: var(--space-3);
}
.lane-id {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  min-width: 0;
}
.lane-id strong {
  font: var(--md-title-small);
}
.ticks {
  display: grid;
  grid-template-columns: repeat(24, 1fr);
  gap: 2px;
}
.tick {
  height: 12px;
  border-radius: 2px;
  background: var(--md-surface-container-highest);
}
.tick--on {
  background: var(--md-ok);
}
.lane-meta {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
  font-variant-numeric: tabular-nums;
}
.lane-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-4);
  margin-top: 4px;
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}
.lane-metrics b {
  font: var(--md-body-medium);
  color: var(--md-on-surface);
  font-weight: 500;
}
.unit {
  margin-left: 2px;
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}

.bottom {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(280px, 1fr);
  gap: var(--space-4);
  align-items: stretch;
}

.small {
  font: var(--md-body-small);
}
.empty {
  padding: var(--space-3) 0;
}

@media (max-width: 1080px) {
  .top,
  .bottom {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
