<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, fmtNum, fmtTime } from '../api'
import PageHeader from '../components/PageHeader.vue'
import ChartBox from '../components/ChartBox.vue'
import { chartTokens, useTheme } from '../lib/theme'

const route = useRoute()
const detail = ref(null)
const series = ref(null)
const batches = ref([])
const metric = ref('')
const error = ref('')
const { theme } = useTheme()
const tk = computed(() => chartTokens(theme.value))

const id = computed(() => route.params.id)

async function loadDetail() {
  try {
    detail.value = await api(`/devices/${id.value}`)
    batches.value = await api(`/batches?device=${encodeURIComponent(id.value)}&limit=8`).catch(() => [])
    metric.value = detail.value.metrics[0]?.metric || ''
    await loadSeries()
  } catch (e) {
    error.value = e.message
  }
}

async function loadSeries() {
  if (!metric.value) return
  series.value = await api(`/devices/${id.value}/series?metric=${encodeURIComponent(metric.value)}&hours=24`)
}

onMounted(loadDetail)
watch(id, loadDetail)
watch(metric, loadSeries)

const option = computed(() => {
  const pts = series.value?.points || []
  const unit = series.value?.unit || ''
  return {
    grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => `${Number(v).toFixed(series.value?.decimals ?? 1)} ${unit}`,
    },
    xAxis: {
      type: 'category',
      data: pts.map((p) => fmtTime(p.ts)),
      axisLine: { lineStyle: { color: tk.value.split } },
      axisLabel: { color: tk.value.axis, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: { lineStyle: { color: tk.value.split } },
      axisLabel: { color: tk.value.axis, fontSize: 11 },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: tk.value.line },
        areaStyle: { color: tk.value.area },
        data: pts.map((p) => p.mean),
      },
    ],
  }
})
</script>

<template>
  <PageHeader :title="detail?.device?.name || '设备'" :sub="detail ? `${detail.device.device_id}，${detail.device.scene}，最小 k ${detail.k_min || '—'}` : ''">
    <RouterLink class="md-btn md-btn--text" to="/devices">返回列表</RouterLink>
  </PageHeader>

  <p v-if="error" class="error">{{ error }}</p>

  <section class="md-card" v-if="detail">
    <div class="section-head">
      <h2>趋势</h2>
      <select v-model="metric" class="md-field" aria-label="选择指标">
        <option v-for="m in detail.metrics" :key="m.metric" :value="m.metric">
          {{ m.label }}（{{ m.unit }}）
        </option>
      </select>
    </div>
    <ChartBox :option="option" height="260px" />
  </section>

  <section class="md-card meta" v-if="detail">
    <h2>指标</h2>
    <div class="md-list">
      <div v-for="m in detail.metrics" :key="m.metric" class="md-list-row">
        <div class="md-grow">
          <div>{{ m.label }}</div>
          <div class="md-muted small">module {{ m.module_id }}，{{ m.table }}，k {{ m.k }}</div>
        </div>
        <span class="md-mono">{{ fmtNum(m.mean, m.decimals) }} {{ m.unit }}</span>
      </div>
    </div>
  </section>

  <section class="md-card batches" v-if="batches.length">
    <div class="section-head">
      <h2>最近批次</h2>
      <span class="md-muted">只存聚合，不含逐条原始记录</span>
    </div>
    <table class="md-table">
      <thead><tr><th>窗口</th><th class="num">指标</th><th class="num">最小 k</th><th class="num">建议</th><th class="num">收到</th></tr></thead>
      <tbody>
        <tr v-for="b in batches" :key="b.batch_id">
          <td>{{ fmtTime(b.ts_from) }} – {{ fmtTime(b.ts_to) }}</td>
          <td class="num">{{ b.metrics }}</td>
          <td class="num">{{ b.k_min }}</td>
          <td class="num">{{ b.advice || '—' }}</td>
          <td class="num">{{ fmtTime(b.received_at) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.error { color: var(--md-error); margin-bottom: var(--space-3); }
.section-head {
  display: flex; justify-content: space-between; align-items: center; gap: var(--space-3);
  margin-bottom: var(--space-3); flex-wrap: wrap;
}
.meta { margin-top: var(--space-4); }
.batches { margin-top: var(--space-4); }
.section-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--space-3); }
.small { font: var(--md-body-small); }
</style>
