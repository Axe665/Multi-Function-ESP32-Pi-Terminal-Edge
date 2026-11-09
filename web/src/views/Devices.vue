<script setup>
import { onMounted, ref } from 'vue'
import { api, fmtNum, fmtTime } from '../api'
import PageHeader from '../components/PageHeader.vue'

const devs = ref([])
const batches = ref([])
const error = ref('')

onMounted(async () => {
  try {
    ;[devs.value, batches.value] = await Promise.all([
      api('/devices'),
      api('/batches?limit=8').catch(() => []),
    ])
  } catch (e) {
    error.value = e.message
  }
})

const linkLabel = { wifi: 'Wi-Fi', ethernet: '有线', offline: '离线', unknown: '未知' }
</script>

<template>
  <PageHeader title="设备" sub="三台终端：一台带屏跑完整 QML，两台无头只上报数据。">
    <span class="md-chip">{{ devs.filter((d) => d.online).length }} / {{ devs.length }} 在线</span>
  </PageHeader>

  <p v-if="error" class="error">{{ error }}</p>

  <section class="md-card">
    <table class="md-table">
      <thead>
        <tr><th>设备</th><th>场景</th><th>链路</th><th>状态</th><th class="num">最近上报</th><th>最新聚合</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="d in devs" :key="d.device_id">
          <td>
            <RouterLink :to="`/devices/${d.device_id}`"><strong>{{ d.name }}</strong></RouterLink>
            <div class="md-mono md-muted">{{ d.device_id }}</div>
          </td>
          <td>{{ d.scene }}</td>
          <td>{{ linkLabel[d.link] || '未知' }}</td>
          <td>
            <span class="md-chip" :class="d.online ? 'md-chip--ok' : 'md-chip--warn'">
              {{ d.online ? '在线' : '离线' }}
            </span>
          </td>
          <td class="num">{{ fmtTime(d.last_seen) }}</td>
          <td>
            <span v-for="m in d.metrics.slice(0, 3)" :key="m.metric" class="metric">
              <span class="md-muted">{{ m.label }}</span>
              {{ fmtNum(m.mean, m.decimals) }}<span class="md-muted">{{ m.unit }}</span>
            </span>
          </td>
          <td class="num"><RouterLink class="md-btn md-btn--text" :to="`/devices/${d.device_id}`">查看</RouterLink></td>
        </tr>
      </tbody>
    </table>
    <p class="md-muted hint">
      边只保留聚合，不接收逐条原始记录。模块清单来自终端的 status 主题，新模块第一次上报时自动登记。
    </p>
  </section>

  <section class="md-card batches">
    <div class="section-head">
      <h2>最近批次</h2>
      <span class="md-muted">聚合窗口，不含逐条明细</span>
    </div>
    <table class="md-table">
      <thead>
        <tr><th>设备</th><th>窗口</th><th class="num">指标</th><th class="num">最小 k</th><th class="num">建议</th><th class="num">收到</th></tr>
      </thead>
      <tbody>
        <tr v-for="b in batches" :key="b.batch_id">
          <td class="md-mono">{{ b.device_id }}</td>
          <td>{{ fmtTime(b.ts_from) }} – {{ fmtTime(b.ts_to) }}</td>
          <td class="num">{{ b.metrics }}</td>
          <td class="num">{{ b.k_min }}</td>
          <td class="num">{{ b.advice || '—' }}</td>
          <td class="num">{{ fmtTime(b.received_at) }}</td>
        </tr>
        <tr v-if="!batches.length"><td colspan="6" class="md-muted">还没有收到批次。</td></tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.error { color: var(--md-error); margin-bottom: var(--space-3); }
.metric { display: block; white-space: nowrap; }
.metric span:first-child { margin-right: 4px; }
.hint { margin-top: var(--space-3); font: var(--md-body-small); }
.batches { margin-top: var(--space-4); }
.section-head {
  display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--space-3);
}
</style>
