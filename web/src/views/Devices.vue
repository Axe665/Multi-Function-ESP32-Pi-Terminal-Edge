<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, fmtNum, fmtTime } from '../api'
import PageLead from '../components/PageLead.vue'
import Icon from '../components/Icon.vue'

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
const allOnline = computed(() => devs.value.length > 0 && devs.value.every((d) => d.online))
</script>

<template>
  <p v-if="error" class="error">{{ error }}</p>

  <PageLead sub="三台终端：一台带屏跑完整 QML，两台无头只上报数据。边只保留聚合，不接收逐条原始记录。">
    <span class="sev" :class="allOnline ? 'sev--ok' : 'sev--notice'">
      <span class="sev-dot"></span>{{ devs.filter((d) => d.online).length }}/{{ devs.length }} 在线
    </span>
  </PageLead>

  <div class="md-grid">
    <section class="md-card span-12">
      <div class="md-card-head">
        <h2>设备</h2>
        <span class="meta">点一行看趋势与批次</span>
      </div>

      <div class="md-list">
        <RouterLink
          v-for="d in devs"
          :key="d.device_id"
          :to="`/devices/${d.device_id}`"
          class="md-list-item"
        >
          <span class="md-list-icon"><Icon name="devices" /></span>
          <div class="md-grow">
            <div class="md-list-title">{{ d.name }}</div>
            <div class="md-list-sub">
              <span class="md-mono">{{ d.device_id }}</span> · {{ d.scene }} ·
              {{ linkLabel[d.link] || '未知' }}
            </div>
          </div>
          <div class="md-list-trail">
            <span v-for="m in d.metrics.slice(0, 3)" :key="m.metric" class="metric">
              <span class="md-muted">{{ m.label }}</span>
              <b class="md-num">{{ fmtNum(m.mean, m.decimals) }}{{ m.unit }}</b>
            </span>
            <span class="sev" :class="d.online ? 'sev--ok' : 'sev--critical'">
              <span class="sev-dot"></span>{{ d.online ? '在线' : '离线' }}
            </span>
            <span class="md-muted last">{{ fmtTime(d.last_seen) }}</span>
            <Icon name="chevron_right" />
          </div>
        </RouterLink>
        <p v-if="!devs.length" class="md-muted">还没有设备上报。</p>
      </div>

      <p class="md-muted hint">
        模块清单来自终端的 status 主题，新模块第一次上报时自动登记。
      </p>
    </section>

    <section class="md-card span-12">
      <div class="md-card-head">
        <h2>最近批次</h2>
        <span class="meta">聚合窗口，不含逐条明细</span>
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
  </div>
</template>

<style scoped>
.error { color: var(--md-error); max-width: var(--content-max); margin: 0 auto var(--space-3); }
.metric { white-space: nowrap; }
.metric span:first-child { margin-right: 4px; }
.metric b { font-weight: 500; color: var(--md-on-surface); }
.last { font: var(--md-label-medium); }
.hint { margin-top: var(--space-3); font: var(--md-body-small); }
</style>
