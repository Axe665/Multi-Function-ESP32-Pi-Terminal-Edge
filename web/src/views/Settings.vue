<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, fmtTime } from '../api'
import PageHeader from '../components/PageHeader.vue'
import KpiRow from '../components/KpiRow.vue'
import ChartBox from '../components/ChartBox.vue'
import { chartTokens, useTheme } from '../lib/theme'
import { useSnack } from '../components/useSnack'

const settings = ref(null)
const outbox = ref([])
const overview = ref(null)
const preview = ref(null)
const privacy = ref(null)
const certs = ref([])
const paired = ref(0)
const error = ref('')
const busy = ref(false)
const { toast } = useSnack()
const { theme } = useTheme()
const tk = computed(() => chartTokens(theme.value))

const outboxOption = computed(() => {
  const t = tk.value
  const rows = outbox.value || []
  const sent = rows.filter((r) => r.sent_at).length
  const failed = rows.filter((r) => !r.sent_at && r.last_error).length
  const pending = rows.length - sent - failed
  return {
    grid: { left: 4, right: 8, top: 18, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: ['已发送', '待发送', '失败'],
             axisLabel: { fontSize: 11, color: t.axis }, axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: t.split } },
             axisLabel: { fontSize: 10, color: t.axis } },
    series: [{
      type: 'bar', data: [sent, pending, failed], barMaxWidth: 30,
      itemStyle: {
        color: (p) => [t.line, t.palette[2], '#c0392b'][p.dataIndex],
        borderRadius: [3, 3, 0, 0],
      },
      label: { show: true, position: 'top', fontSize: 10, color: t.axis },
    }],
  }
})

const intervalOption = computed(() => {
  const t = tk.value
  const ts = (outbox.value || []).map((r) => r.created_at).sort((a, b) => a - b)
  const buckets = [0, 0, 0, 0]
  for (let i = 1; i < ts.length; i++) {
    const mins = (ts[i] - ts[i - 1]) / 60000
    buckets[mins <= 15 ? 0 : mins <= 30 ? 1 : mins <= 60 ? 2 : 3] += 1
  }
  return {
    grid: { left: 4, right: 8, top: 18, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: ['≤15 分', '16–30', '31–60', '>60'],
             axisLabel: { fontSize: 11, color: t.axis }, axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false } },
    yAxis: { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: t.split } },
             axisLabel: { fontSize: 10, color: t.axis } },
    series: [{
      type: 'bar', data: buckets, barMaxWidth: 30,
      itemStyle: { color: t.palette[1], borderRadius: [3, 3, 0, 0] },
      label: { show: true, position: 'top', fontSize: 10, color: t.axis },
    }],
  }
})

const previewLoading = ref(false)

async function load() {
  try {
    ;[settings.value, outbox.value, overview.value, privacy.value] = await Promise.all([
      api('/settings'),
      api('/outbox').catch(() => []),
      api('/overview').catch(() => null),
      api('/privacy').catch(() => null),
    ])
    const [c, d] = await Promise.all([api('/certs').catch(() => []), api('/discovery').catch(() => null)])
    certs.value = c
    paired.value = (d?.devices || []).filter((x) => x.paired).length
    preview.value = await api('/report/preview').catch(() => null)
  } catch (e) {
    error.value = e.message
  }
}

async function save() {
  busy.value = true
  try {
    settings.value = await api('/settings', { method: 'PUT', body: settings.value })
    toast('设置已保存')
  } catch (e) {
    toast(`保存失败：${e.message}`)
  } finally {
    busy.value = false
  }
}

async function pushNow() {
  busy.value = true
  try {
    const r = await api('/report/cloud', { method: 'POST' })
    toast(r.cloud === 'ok' ? `已上报 ${r.report_id}` : `已入发件箱（${r.cloud}）`)
    await load()
  } catch (e) {
    toast(`上报失败：${e.message}`)
  } finally {
    busy.value = false
  }
}

// 云连接：手动配置（/cloud/config）+ mDNS 搜索（/cloud/discovery）
const cloudUrl = ref('')
const cloudToken = ref('')
const cloudFound = ref([])
const cloudSearching = ref(false)

async function saveCloud() {
  busy.value = true
  try {
    const r = await api('/cloud/config', {
      method: 'POST',
      body: { url: cloudUrl.value.trim(), token: cloudToken.value.trim() },
    })
    toast(r.configured ? `云已配置：${r.url}` : '已清空云配置')
    await pushNow()
    await load()
  } catch (e) {
    toast(`保存失败：${e.message}`)
  } finally {
    busy.value = false
  }
}

async function searchCloud() {
  cloudSearching.value = true
  cloudFound.value = []
  try {
    const r = await api('/cloud/discovery')
    cloudFound.value = r.found || []
    if (!cloudFound.value.length) toast('没有发现云节点；确认云仓在局域网内广播 _orpi-cloud._tcp')
  } catch (e) {
    toast(`搜索失败：${e.message}`)
  } finally {
    cloudSearching.value = false
  }
}

async function connectCloud(url) {
  cloudUrl.value = url
  await saveCloud()
}

onMounted(load)
const cloud = () => [
  { label: '云地址', value: overview.value?.cloud_url || '未配置', note: overview.value?.cloud_enabled ? '自动上报已开启' : '报表只留在本机' },
  { label: '待发送', value: outbox.value.filter((x) => !x.sent_at).length, note: '按 report_id 幂等' },
  { label: '已发送', value: outbox.value.filter((x) => x.sent_at).length, note: `最近一次 ${fmtTime(outbox.value.find((x) => x.sent_at)?.sent_at, true)}` },
]
</script>

<template>
  <PageHeader title="设置" sub="上报节奏、云连接、保留期与隐私计数。">
    <button class="md-btn" :disabled="busy" @click="pushNow">立即上报</button>
  </PageHeader>

  <p v-if="error" class="error">{{ error }}</p>

  <KpiRow :items="cloud()" />

  <div class="charts">
    <section class="md-card">
      <div class="section-head">
        <h2>发件箱</h2>
        <span class="md-muted">{{ outbox.length }} 份</span>
      </div>
      <ChartBox :option="outboxOption" height="132px" />
    </section>
    <section class="md-card">
      <div class="section-head">
        <h2>上报间隔</h2>
        <span class="md-muted">相邻报表的生成间隔</span>
      </div>
      <ChartBox :option="intervalOption" height="132px" />
    </section>
  </div>

  <div class="duo">
    <section class="md-card">
      <div class="section-head">
        <h2>云连接</h2>
        <span class="md-muted">{{ overview?.cloud_enabled ? '自动上报已开启' : '报表只留在本机' }}</span>
      </div>
      <div class="form">
        <label>
          <span>云地址</span>
          <input v-model="cloudUrl" class="md-field" placeholder="https://cloud.local:8443" />
        </label>
        <label>
          <span>访问令牌（可选）</span>
          <input v-model="cloudToken" class="md-field" />
        </label>
      </div>
      <div class="actions">
        <button class="md-btn" :disabled="busy" @click="saveCloud">保存并连接</button>
        <button class="md-btn" :disabled="cloudSearching" @click="searchCloud">
          {{ cloudSearching ? '搜索中…' : '搜索云' }}
        </button>
      </div>
      <ul v-if="cloudFound.length" class="cloud-list">
        <li v-for="item in cloudFound" :key="item.url">
          <div>
            <strong class="md-mono">{{ item.url }}</strong>
            <span class="md-muted"> · {{ item.ca_fp || '无指纹' }} · {{ item.trusted ? '可信' : '未校验' }}</span>
          </div>
          <button class="md-btn" :disabled="busy" @click="connectCloud(item.url)">连接</button>
        </li>
      </ul>
    </section>

    <section class="md-card">
      <h2>上报</h2>
      <div v-if="settings" class="form">
        <label>
          <span>上报节奏（分钟）</span>
          <input v-model.number="settings.report_cadence_min" type="number" min="5" class="md-field" />
        </label>
        <label>
          <span>保留天数</span>
          <input v-model.number="settings.retention_days" type="number" min="7" class="md-field" />
        </label>
        <label class="check">
          <input v-model="settings.cloud_enabled" type="checkbox" />
          <span>启用自动上报</span>
        </label>
        <label class="check">
          <input v-model="settings.personalization" type="checkbox" />
          <span>个性化建议</span>
        </label>
        <label class="check">
          <input v-model="settings.group_analysis" type="checkbox" />
          <span>启用群体分析（k≥5）</span>
        </label>
      </div>
      <p v-else class="md-muted">读取中…</p>
      <button class="md-btn" :disabled="busy || !settings" @click="save">保存</button>
      <p class="md-muted small hint">
        失败按 1 / 5 / 30 分钟、2 小时退避；报表最多保留 7 天。
        上报节奏决定自动打包间隔；保留天数影响本机聚合与发件箱。
      </p>
    </section>

    <section class="md-card">
      <div class="section-head">
        <h2>隐私计数</h2>
        <span class="md-muted">只增不减</span>
      </div>
      <div class="md-list">
        <div class="md-list-row"><div class="md-grow">k 门槛</div><span class="md-mono">{{ privacy?.k_min ?? '—' }}</span></div>
        <div class="md-list-row"><div class="md-grow">被抑制的桶</div><span class="md-mono">{{ privacy?.suppressed_buckets ?? '—' }}</span></div>
        <div class="md-list-row"><div class="md-grow">原始字段拦截</div><span class="md-mono">{{ privacy?.raw_rejected ?? '—' }}</span></div>
        <div class="md-list-row"><div class="md-grow">假名方式</div><span class="md-mono">{{ privacy?.pseudonym || '—' }}</span></div>
        <div class="md-list-row"><div class="md-grow">保留天数</div><span class="md-mono">{{ privacy?.retention ?? settings?.retention_days ?? '—' }}</span></div>
      </div>
      <p class="md-muted small hint">
        出端前剥掉 min/max/subject/user_id；出现原始字段整份拒收，不做静默清洗。
      </p>
    </section>
  </div>


  <section class="md-card access-summary">
    <div class="section-head">
      <h2>证书与设备接入</h2>
      <RouterLink class="md-btn md-btn--text" to="/access">去接入页</RouterLink>
    </div>
    <div class="md-list">
      <div class="md-list-row"><div class="md-grow">已配对设备</div><span class="md-mono">{{ paired }}</span></div>
      <div class="md-list-row"><div class="md-grow">签发证书</div><span class="md-mono">{{ certs.length }}</span></div>
      <div class="md-list-row">
        <div class="md-grow">30 天内到期</div>
        <span class="md-mono">{{ certs.filter((c) => c.expiring).length }}</span>
      </div>
    </div>
  </section>

  <section class="md-card report">
    <div class="section-head">
      <h2>报表预览</h2>
      <span class="md-muted">
        {{ preview ? `report_id ${preview.report_id} 前 8 行` : '预览不可用' }}
      </span>
    </div>
    <table v-if="preview?.sample?.length" class="md-table">
      <thead>
        <tr><th>设备</th><th>日期</th><th>指标</th><th class="num">均值</th><th class="num">斜率</th><th class="num">z</th><th class="num">k</th></tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in preview.sample" :key="i">
          <td class="md-mono">{{ r.device_id }}</td>
          <td>{{ r.day }}</td>
          <td>{{ r.metric }}</td>
          <td class="num">{{ r.mean }}</td>
          <td class="num">{{ r.slope }}</td>
          <td class="num">{{ r.z }}</td>
          <td class="num">{{ r.k }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="md-muted">暂时没有可上报的日聚合。</p>
  </section>

  <section class="md-card outbox">
    <div class="section-head">
      <h2>发件箱</h2>
      <span class="md-muted">{{ outbox.length }} 份报表</span>
    </div>
    <table class="md-table">
      <thead><tr><th>报告</th><th>生成</th><th>状态</th><th class="num">次数</th><th>最后一次错误</th></tr></thead>
      <tbody>
        <tr v-for="x in outbox" :key="x.report_id">
          <td class="md-mono">{{ x.report_id }}</td>
          <td>{{ fmtTime(x.created_at, true) }}</td>
          <td>
            <span class="md-chip" :class="x.sent_at ? 'md-chip--ok' : 'md-chip--warn'">
              {{ x.sent_at ? '已送达' : '等待' }}
            </span>
          </td>
          <td class="num">{{ x.attempts }}</td>
          <td class="md-muted">{{ x.last_error || '—' }}</td>
        </tr>
        <tr v-if="!outbox.length"><td colspan="5" class="md-muted">还没有报表。</td></tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.error { color: var(--md-error); margin-bottom: var(--space-3); }
.charts {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4); margin-top: var(--space-4);
}
@media (max-width: 1000px) { .charts { grid-template-columns: minmax(0, 1fr); } }
.duo {
  display: grid; grid-template-columns: minmax(0, 1fr);
  gap: var(--space-4);
  max-width: 760px;
}
.form { display: flex; flex-direction: column; gap: var(--space-3); margin: var(--space-3) 0; }
.form label { display: flex; flex-direction: column; gap: 4px; font: var(--md-label-medium); color: var(--md-on-surface-variant); }
.form .check { flex-direction: row; align-items: center; gap: var(--space-2); }
.section-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: var(--space-3); }
.small { font: var(--md-body-small); }
.hint { margin-top: var(--space-3); }
.report { margin-top: var(--space-4); }
.access-summary { margin-top: var(--space-4); }
.outbox { margin-top: var(--space-4); }
@media (max-width: 900px) {
  .duo { grid-template-columns: minmax(0, 1fr); }
}
.cloud-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: grid;
  gap: 8px;
}
.cloud-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--md-outline-variant);
  border-radius: 10px;
}
.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}
</style>
