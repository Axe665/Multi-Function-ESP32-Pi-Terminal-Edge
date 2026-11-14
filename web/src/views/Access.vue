<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, fmtTime } from '../api'
import PageLead from '../components/PageLead.vue'
import KpiRow from '../components/KpiRow.vue'
import ChartBox from '../components/ChartBox.vue'
import { chartTokens, useTheme } from '../lib/theme'
import { useSnack } from '../components/useSnack'

const disc = ref(null)
const certs = ref([])
const codes = ref([])
const error = ref('')
const picked = ref('')
const wifi = ref({ ssid: '', psk: '', country: 'CN' })
const wifiOut = ref(null)
const wifiOpen = ref(false)
const { toast } = useSnack()
const { theme } = useTheme()
const tk = computed(() => chartTokens(theme.value))

const linkLabel = { wifi: 'Wi-Fi', ethernet: '有线', offline: '离线', unknown: '未知' }
const devices = computed(() => disc.value?.devices || [])
const paired = computed(() => devices.value.filter((d) => d.paired).length)
const expiring = computed(() => certs.value.filter((c) => c.expiring).length)
const kpis = computed(() => [
  { label: '已接入', value: paired.value, note: `${devices.value.length - paired.value} 台待配对` },
  { label: '证书', value: certs.value.length, note: '365 天有效期' },
  { label: '30 天内到期', value: expiring.value, note: '到期前 30 天续期' },
  { label: '吊销', value: certs.value.filter((c) => c.revoked).length, note: 'CRL 可下载' },
])

// 证书到期分布：30 天内、31–90、91–180、更远
const certOption = computed(() => {
  const t = tk.value
  const n = [0, 0, 0, 0]
  for (const c of certs.value) {
    const d = c.days_left ?? 999
    n[d <= 30 ? 0 : d <= 90 ? 1 : d <= 180 ? 2 : 3] += 1
  }
  return {
    grid: { left: 4, right: 8, top: 18, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: ['≤30 天', '31–90', '91–180', '>180'], axisLabel: { fontSize: 11, color: t.axis },
             axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false } },
    yAxis: { type: 'value', minInterval: 1, splitNumber: 3, splitLine: { lineStyle: { color: t.split } },
             axisLabel: { fontSize: 10, color: t.axis } },
    series: [{
      type: 'bar', data: n, barMaxWidth: 30,
      itemStyle: { color: (p) => (p.dataIndex === 0 && p.value ? t.critical : t.line), borderRadius: [4, 4, 0, 0] },
      label: { show: true, position: 'top', fontSize: 10, color: t.axis },
    }],
  }
})

const linkOption = computed(() => {
  const t = tk.value
  const labels = ['有线', 'Wi-Fi', '未知']
  const n = [0, 0, 0]
  for (const d of devices.value) {
    n[d.link === 'ethernet' ? 0 : d.link === 'wifi' ? 1 : 2] += 1
  }
  return {
    grid: { left: 4, right: 8, top: 18, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 11, color: t.axis },
             axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false } },
    yAxis: { type: 'value', minInterval: 1, splitNumber: 3, splitLine: { lineStyle: { color: t.split } },
             axisLabel: { fontSize: 10, color: t.axis } },
    series: [{
      type: 'bar', data: n, barMaxWidth: 30,
      itemStyle: { color: t.palette[1], borderRadius: [3, 3, 0, 0] },
      label: { show: true, position: 'top', fontSize: 10, color: t.axis },
    }],
  }
})

async function load() {
  try {
    ;[disc.value, certs.value, codes.value] = await Promise.all([
      api('/discovery').catch(() => null),
      api('/certs').catch(() => []),
      api('/pair-codes').catch(() => []),
    ])
    if (!picked.value && devices.value.length) picked.value = devices.value[0].device_id
  } catch (e) {
    error.value = e.message
  }
}

async function pair() {
  try {
    const r = await api(`/devices/${encodeURIComponent(picked.value)}/pair`, { method: 'POST' })
    toast(`配对码 ${r.code}，${Math.round(r.ttl_s / 60)} 分钟内有效`)
    await load()
  } catch (e) {
    toast(`生成失败：${e.message}`)
  }
}

async function makeWifi() {
  try {
    wifiOut.value = await api(`/devices/${encodeURIComponent(picked.value)}/wifi-config`,
      { method: 'POST', body: wifi.value })
    toast('已生成配置，复制到 U 盘根目录')
  } catch (e) {
    toast(`生成失败：${e.message}`)
  }
}

onMounted(load)
</script>

<template>
  <p v-if="error" class="error">{{ error }}</p>

  <PageLead sub="mDNS 发现、一次性配对码、证书与吊销；组播不可用时退化为登记清单。">
    <span class="md-chip">CA {{ disc?.edge?.ca_fp || '—' }}</span>
  </PageLead>

  <div class="md-grid">
    <KpiRow :items="kpis" />

    <section class="md-card span-6">
      <div class="md-card-head">
        <h2>证书到期分布</h2>
        <span class="meta">按剩余天数分桶</span>
      </div>
      <ChartBox :option="certOption" height="140px" label="证书按剩余天数分桶" />
    </section>

    <section class="md-card span-6">
      <div class="md-card-head">
        <h2>链路类型</h2>
        <span class="meta">已登记设备</span>
      </div>
      <ChartBox :option="linkOption" height="140px" label="设备按链路类型统计" />
    </section>

    <section class="md-card span-7">
      <div class="md-card-head">
        <h2>发现的设备</h2>
        <span class="meta">{{ devices.length }} 台</span>
      </div>
      <table class="md-table">
        <thead><tr><th>设备</th><th>型号</th><th>版本</th><th>链路</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="d in devices" :key="d.device_id">
            <td>
              <strong>{{ d.device_id }}</strong>
              <div class="md-muted small">{{ d.scene || '—' }}，{{ d.source === 'mdns' ? 'mDNS' : '已登记' }}</div>
            </td>
            <td>{{ d.model || '—' }}</td>
            <td class="md-mono">{{ d.fw || '—' }}</td>
            <td>{{ linkLabel[d.link] || '未知' }}</td>
            <td>
              <span class="md-chip" :class="d.paired ? 'md-chip--ok' : 'md-chip--warn'">
                {{ d.paired ? '已配对' : '待配对' }}
              </span>
            </td>
          </tr>
          <tr v-if="!devices.length"><td colspan="5" class="md-muted">没有发现任何终端。</td></tr>
        </tbody>
      </table>

      <div class="pair">
        <label class="md-field">
          <span>要配对的设备</span>
          <select v-model="picked">
            <option v-for="d in devices" :key="d.device_id" :value="d.device_id">
              {{ d.device_id }}{{ d.paired ? '（已配对，将签发新码）' : '' }}
            </option>
          </select>
        </label>
        <button class="md-btn" :disabled="!picked" @click="pair">生成配对码</button>
      </div>
      <p class="md-muted small hint">
        配对码 6 位、10 分钟有效，绑定设备公钥指纹，一次性使用；同一设备 5 次失败锁 10 分钟。
      </p>

      <ol class="steps md-muted small">
        <li><b>发现</b>终端广播 _orpi-device._tcp，组播被挡时退回已登记清单</li>
        <li><b>配对</b>生成配对码，终端带自己的公钥指纹兑换一次</li>
        <li><b>签发</b>终端提交 CSR，边签 365 天证书，私钥不出终端</li>
        <li><b>续期</b>到期前 30 天提醒，终端带新 CSR 调 /devices/{id}/renew，边不代签</li>
      </ol>
    </section>

    <section class="md-card span-5">
      <div class="md-card-head">
        <h2>证书</h2>
        <span class="meta">{{ certs.length }} 张</span>
      </div>
      <table class="md-table">
        <thead><tr><th>设备</th><th class="num">剩余</th><th class="num">序列号</th></tr></thead>
        <tbody>
          <tr v-for="c in certs.slice(0, 8)" :key="c.serial">
            <td>
              {{ c.device_id }}
              <div class="md-muted small">{{ fmtTime(c.issued_at) }} 签发</div>
            </td>
            <td class="num">
              <span v-if="c.expiring" class="md-chip md-chip--warn">{{ c.days_left }} 天</span>
              <span v-else>{{ c.days_left }} 天</span>
            </td>
            <td class="num md-mono">{{ String(c.serial).slice(0, 10) }}</td>
          </tr>
          <tr v-if="!certs.length"><td colspan="3" class="md-muted">还没有签发过证书。</td></tr>
        </tbody>
      </table>

      <div class="links">
        <a class="md-btn md-btn--outline" href="/api/v1/ca.crt" target="_blank" rel="noopener">下载 CA</a>
        <a class="md-btn md-btn--outline" href="/api/v1/crl.pem" target="_blank" rel="noopener">下载 CRL</a>
        <button class="md-btn md-btn--outline" @click="wifiOpen = !wifiOpen">WiFi 配置</button>
      </div>

      <div v-if="wifiOpen" class="wifi">
        <h3 class="wifi-title">给无头终端生成 WiFi 配置</h3>
        <div class="wifi-grid">
          <label class="md-field">
            <span>SSID</span>
            <input v-model="wifi.ssid" />
          </label>
          <label class="md-field">
            <span>WPA2 口令（8–63）</span>
            <input v-model="wifi.psk" type="password" />
          </label>
          <label class="md-field country">
            <span>国家码</span>
            <input v-model="wifi.country" maxlength="2" />
          </label>
        </div>
        <button class="md-btn" :disabled="!wifi.ssid || !wifi.psk" @click="makeWifi">生成</button>
        <p class="md-muted small">口令只在本次请求中使用，不落库，不写审计。</p>
        <pre v-if="wifiOut" class="conf">{{ wifiOut.content }}</pre>
      </div>
    </section>

    <section class="md-card span-12">
      <div class="md-card-head">
        <h2>最近的配对码</h2>
        <span class="meta">{{ codes.length }} 个</span>
      </div>
      <div class="md-list">
        <div v-for="c in codes.slice(0, 5)" :key="c.code" class="md-list-item">
          <div class="md-grow">
            <div class="md-mono code">{{ c.code }}</div>
            <div class="md-muted small">{{ c.device_id || '—' }}，{{ c.attempts }} 次尝试</div>
          </div>
          <span class="md-chip" :class="c.used_at ? 'md-chip--ok' : c.locked_until ? 'md-chip--alert' : 'md-chip--warn'">
            {{ c.used_at ? '已使用' : c.locked_until ? '已锁定' : '待使用' }}
          </span>
        </div>
        <p v-if="!codes.length" class="md-muted">还没有生成过配对码。</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.error { color: var(--md-error); max-width: var(--content-max); margin: 0 auto var(--space-3); }
.steps {
  margin: var(--space-3) 0 0;
  padding-left: 18px;
  display: grid;
  gap: var(--space-2);
}
.steps b { color: var(--md-on-surface); font-weight: 500; }
.pair {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-4);
  flex-wrap: wrap;
}
.pair .md-field { flex: 1; min-width: 200px; }
.links { display: flex; gap: var(--space-2); margin-top: var(--space-4); flex-wrap: wrap; }
.hint { margin-top: var(--space-3); }
.code { font-size: 15px; letter-spacing: 0.08em; }
.wifi {
  margin-top: var(--space-4);
  border-top: 1px solid var(--md-outline-variant);
  padding-top: var(--space-3);
}
.wifi-title { margin-bottom: var(--space-2); }
.wifi-grid {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-bottom: var(--space-2);
}
.wifi-grid .md-field { flex: 1; min-width: 140px; }
.wifi-grid .country { flex: 0 0 96px; }
.conf {
  margin-top: var(--space-3);
  padding: var(--space-3);
  background: var(--md-surface-container-high);
  border-radius: var(--md-shape-xs);
  font: var(--md-body-small);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.small { font: var(--md-body-small); }
</style>
