<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, fmtNum, fmtTime } from '../api'
import PageLead from '../components/PageLead.vue'
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
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
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
  <p v-if="error" class="error">{{ error }}</p>

  <PageLead
    :sub="detail ? `${detail.device.device_id}，${detail.device.scene}，最小 k ${detail.k_min || '—'}` : ''"
  >
    <RouterLink class="md-btn md-btn--text" to="/devices">返回列表</RouterLink>
  </PageLead>

  <div class="md-grid">
    <section v-if="detail?.insufficient" class="md-card span-12">
      <b>样本不足</b>
      <span class="md-muted">群体分析已关闭，只保留在线与健康计数；管理员开启后才显示趋势、指标与批次。</span>
    </section>

    <template v-if="detail && !detail.insufficient">
      <section class="md-card span-8 trend">
        <div class="md-card-head">
          <h2>趋势 · 24 小时</h2>
          <label class="md-field metric-pick">
            <span>指标</span>
            <select v-model="metric">
              <option v-for="m in detail.metrics" :key="m.metric" :value="m.metric">
                {{ m.label }}（{{ m.unit }}）
              </option>
            </select>
          </label>
        </div>
        <ChartBox :option="option" height="300px" :label="`${detail.device.name} 24 小时趋势`" />
      </section>

      <section class="md-card span-4">
        <div class="md-card-head">
          <h2>指标</h2>
          <span class="meta">最新聚合</span>
        </div>
        <div class="md-list">
          <div v-for="m in detail.metrics" :key="m.metric" class="md-list-item metric-row">
            <div class="md-grow">
              <div class="md-list-title">{{ m.label }}</div>
              <div class="md-list-sub">module {{ m.module_id }}，{{ m.table }}，k {{ m.k }}</div>
            </div>
            <span class="md-mono">{{ fmtNum(m.mean, m.decimals) }} {{ m.unit }}</span>
          </div>
        </div>
      </section>

      <section v-if="batches.length" class="md-card span-12">
        <div class="md-card-head">
          <h2>最近批次</h2>
          <span class="meta">只存聚合，不含逐条原始记录</span>
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
  </div>
</template>

<style scoped>
.error { color: var(--md-error); max-width: var(--content-max); margin: 0 auto var(--space-3); }
.metric-pick {
  width: 240px;
}
.metric-row + .metric-row {
  border-top: 1px solid var(--md-outline-variant);
}
</style>
