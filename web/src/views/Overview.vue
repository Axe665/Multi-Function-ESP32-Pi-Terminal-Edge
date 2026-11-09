<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api, fmtNum, fmtTime } from '../api'
import { createFlow } from '../lib/flow'
import PageHeader from '../components/PageHeader.vue'
import KpiRow from '../components/KpiRow.vue'

const o = ref(null)
const advice = ref([])
const error = ref('')
const flowHost = ref(null)
let flow = null

const load = async () => {
  try {
    o.value = await api('/overview')
    advice.value = await api('/advice?limit=6').catch(() => [])
    error.value = ''
    if (flow && o.value) {
      flow.setData({
        batches: o.value.batches_24h,
        suppressed: o.value.suppressed_buckets,
        alerts: o.value.alerts_24h,
        online: o.value.lanes.map((l) => l.online),
      })
    }
  } catch (e) {
    error.value = e.message
  }
}

onMounted(async () => {
  if (flowHost.value) flow = createFlow(flowHost.value)
  await load()
  timer = setInterval(load, 15000)
})

let timer = 0
onBeforeUnmount(() => {
  clearInterval(timer)
  flow?.destroy?.()
})

const kpis = () => {
  if (!o.value) return []
  return [
    { label: '在线终端', value: `${o.value.devices_online}/${o.value.devices_total}`, note: '最近 15 分钟有批次' },
    { label: '24 h 批次', value: fmtNum(o.value.batches_24h, 0), note: '按 (device, batch_id) 去重' },
    { label: '24 h 建议', value: fmtNum(o.value.advice_24h, 0), note: `其中告警 ${o.value.alerts_24h}` },
    { label: '被抑制的桶', value: fmtNum(o.value.suppressed_buckets, 0), note: 'k<5，只在端内使用' },
  ]
}
</script>

<template>
  <PageHeader title="总览" :sub="`${o?.edge_name || '边节点'}，3 台终端，5 分钟聚合窗口，k≥5 才入库`">
    <button class="md-btn md-btn--tonal" @click="load">刷新</button>
    <RouterLink class="md-btn" to="/settings">上云设置</RouterLink>
  </PageHeader>

  <p v-if="error" class="error">读不到总览：{{ error }}</p>

  <KpiRow :items="kpis()" />

  <section class="md-card flow-card">
    <div class="flow-head">
      <div>
        <h2>数据流</h2>
        <p class="md-muted">端 → k≥5 聚合环 → 云。熄掉的粒子是被抑制的桶。</p>
      </div>
      <span class="md-chip" :class="o?.cloud_ok ? 'md-chip--ok' : 'md-chip--warn'">
        {{ o?.cloud_ok ? '云端可达' : '云端未连' }}
      </span>
    </div>
    <div class="flow-wrap">
      <canvas ref="flowHost" class="flow-canvas"></canvas>
      <div class="flow-legend" aria-hidden="true">
        <span class="flow-stage">终端</span>
        <span class="flow-arrow">→</span>
        <span class="flow-stage flow-stage--ring">k≥5 聚合环</span>
        <span class="flow-arrow">→</span>
        <span class="flow-stage">云端</span>
      </div>
    </div>
  </section>

  <section class="md-card lanes">
    <div class="section-head">
      <h2>链路</h2>
      <span class="md-muted">最近 24 个 5 分钟窗口，实心格为已收到</span>
    </div>
    <div class="lane-grid">
      <article v-for="lane in o?.lanes || []" :key="lane.device_id" class="lane">
        <header>
          <strong>{{ lane.name }}</strong>
          <span class="md-chip" :class="lane.online ? 'md-chip--ok' : 'md-chip--warn'">
            {{ lane.online ? '在线' : '离线' }}
          </span>
          <span class="md-chip">{{ lane.scene }}</span>
          <span v-if="lane.alerts_24h" class="md-chip md-chip--alert">告警 {{ lane.alerts_24h }}</span>
          <span class="md-mono md-muted">{{ lane.device_id }}</span>
        </header>
        <div class="ticks" :aria-label="`${lane.device_id} 最近 24 个窗口`">
          <span v-for="(t, i) in lane.ticks" :key="i" class="tick" :class="{ 'tick--on': t }"></span>
        </div>
        <div class="lane-meta">
          <span>最近上报 {{ fmtTime(lane.last_seen) }}</span>
          <span>最小 k {{ lane.k }}，{{ lane.fill }}% 到达</span>
        </div>
        <dl class="lane-metrics">
          <div v-for="m in lane.metrics.slice(0, 4)" :key="m.metric">
            <dt>{{ m.label }}</dt>
            <dd>{{ fmtNum(m.mean, m.decimals) }}<span class="unit">{{ m.unit }}</span></dd>
          </div>
        </dl>
      </article>
    </div>
  </section>

  <section class="md-card advice">
    <div class="section-head">
      <h2>最近建议</h2>
      <span class="md-muted">最近 6 条，共 {{ o?.advice_24h ?? 0 }}</span>
    </div>
    <div class="md-list">
      <div v-for="a in advice" :key="a.id" class="md-list-row">
        <span class="md-chip" :class="a.risk === 'alert' ? 'md-chip--alert' : 'md-chip--warn'">
          {{ a.risk === 'alert' ? '告警' : '关注' }}
        </span>
        <div class="md-grow">
          <div>{{ a.text }}</div>
          <div class="md-muted small">{{ a.device_id }}，{{ fmtTime(a.created_at) }}</div>
        </div>
      </div>
      <p v-if="!advice.length" class="md-muted">今天没有建议。</p>
    </div>
  </section>

  <section class="md-card">
    <div class="section-head">
      <h2>近 24 小时的变化</h2>
      <span class="md-muted">相对 7 天同段基线</span>
    </div>
    <div class="md-list">
      <div v-for="f in o?.findings || []" :key="f.metric" class="md-list-row">
        <div class="md-grow">
          <div>{{ f.text }}</div>
          <div class="md-muted small">{{ f.label }}，{{ f.delta > 0 ? '+' : '' }}{{ fmtNum(f.delta, 2) }}{{ f.unit }}</div>
        </div>
        <span class="md-chip" :class="Math.abs(f.pct) > 3 ? 'md-chip--warn' : ''">
          {{ f.pct > 0 ? '+' : '' }}{{ fmtNum(f.pct, 1) }}%
        </span>
      </div>
      <p v-if="!o?.findings?.length" class="md-muted empty">数据不足，暂不生成结论。</p>
    </div>
    <p class="md-muted small hint">
      比较口径：每个指标取最近 24 h 均值，对照同设备前 7 天同一时段的均值。
      最近一次更新 {{ fmtTime(o?.generated_at, true) }}。
    </p>
  </section>
</template>

<style scoped>
.error {
  color: var(--md-error);
  margin-bottom: var(--space-3);
}
.flow-card {
  margin-bottom: var(--space-4);
}
.flow-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.flow-wrap {
  position: relative;
}
.flow-canvas {
  width: 100%;
  height: 260px;
  display: block;
  border-radius: var(--md-shape-sm);
  background: var(--md-card-bg);
  border: 1px solid var(--md-card-border);
}
.flow-legend {
  position: absolute;
  left: 50%;
  bottom: var(--space-3);
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 4px 14px;
  border-radius: var(--md-shape-full);
  background: color-mix(in srgb, var(--md-surface-container-highest) 90%, transparent);
  border: 1px solid var(--md-card-border);
  color: var(--md-on-surface-variant);
  font: var(--md-label-medium);
  pointer-events: none;
}
.flow-stage {
  white-space: nowrap;
}
.flow-stage--ring {
  color: #8a5a00;
}
[data-theme='dark'] .flow-stage--ring {
  color: #ffd98a;
}

.flow-arrow {
  color: color-mix(in srgb, var(--md-on-surface-variant) 70%, transparent);
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.lanes {
  margin-bottom: var(--space-4);
}
.lane-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--space-4);
}
.lane {
  border: 1px solid var(--md-surface-container-highest);
  border-radius: var(--md-shape-sm);
  padding: var(--space-3);
}
.lane header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.ticks {
  display: flex;
  gap: 3px;
  margin: var(--space-3) 0 var(--space-2);
}
.tick {
  flex: 1;
  height: 18px;
  border-radius: 2px;
  background: var(--md-surface-container-highest);
}
.tick--on {
  background: var(--md-primary);
}
.lane-meta {
  display: flex;
  justify-content: space-between;
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}
.lane-metrics {
  margin: var(--space-3) 0 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}
.lane-metrics div {
  min-width: 0;
}
.lane-metrics dt {
  font: var(--md-label-small);
  color: var(--md-on-surface-variant);
}
.lane-metrics dd {
  margin: 0;
  font: var(--md-title-small);
}
.unit {
  margin-left: 3px;
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}
.small {
  font: var(--md-body-small);
}
.hint {
  margin-top: var(--space-3);
}
.empty {
  padding: var(--space-4) 0;
}
</style>
