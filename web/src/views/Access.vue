<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, fmtTime } from '../api'
import PageHeader from '../components/PageHeader.vue'
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

const linkLabel = { wifi: 'Wi-Fi', ethernet: '有线', offline: '离线', unknown: '未知' }
const devices = computed(() => disc.value?.devices || [])
const paired = computed(() => devices.value.filter((d) => d.paired).length)
const expiring = computed(() => certs.value.filter((c) => c.expiring).length)

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
  <PageHeader title="接入" sub="mDNS 发现、一次性配对码、证书与吊销；组播不可用时退化为登记清单。">
    <span class="md-chip">CA {{ disc?.edge?.ca_fp || '—' }}</span>
  </PageHeader>

  <p v-if="error" class="error">{{ error }}</p>

  <section class="kpis">
    <div class="kpi"><div class="label">已接入</div><div class="value">{{ paired }}</div><div class="note">{{ devices.length - paired }} 台待配对</div></div>
    <div class="kpi"><div class="label">证书</div><div class="value">{{ certs.length }}</div><div class="note">365 天有效期</div></div>
    <div class="kpi"><div class="label">30 天内到期</div><div class="value">{{ expiring }}</div><div class="note">到期前 30 天续期</div></div>
    <div class="kpi"><div class="label">吊销</div><div class="value">{{ certs.filter((c) => c.revoked).length }}</div><div class="note">CRL 可下载</div></div>
  </section>

  <div class="duo">
    <section class="md-card">
      <div class="section-head">
        <h2>发现的设备</h2>
        <span class="md-muted">{{ devices.length }} 台</span>
      </div>
      <table class="md-table">
        <thead><tr><th>设备</th><th>型号</th><th>版本</th><th>链路</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="d in devices" :key="d.device_id">
            <td>
              <strong>{{ d.device_id }}</strong>
              <div class="md-muted small">{{ d.scene || '—' }} · {{ d.source === 'mdns' ? 'mDNS' : '已登记' }}</div>
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
        <select v-model="picked" class="md-field" aria-label="选择要配对的设备">
          <option v-for="d in devices" :key="d.device_id" :value="d.device_id">
            {{ d.device_id }}{{ d.paired ? '（已配对，将签发新码）' : '' }}
          </option>
        </select>
        <button class="md-btn" @click="pair" :disabled="!picked">生成配对码</button>
      </div>
      <p class="md-muted small hint">
        配对码 6 位、10 分钟有效，绑定设备公钥指纹，一次性使用；同一设备 5 次失败锁 10 分钟。
        终端广播 _orpi-device._tcp，边广播 _orpi-edge._tcp。
      </p>
    </section>

    <section class="md-card">
      <div class="section-head">
        <h2>证书</h2>
        <span class="md-muted">{{ certs.length }} 张</span>
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
      <div v-if="wifiOpen" class="wifi">
        <div class="section-head"><h3>给无头终端生成 WiFi 配置</h3></div>
        <div class="wifi-grid">
          <input v-model="wifi.ssid" class="md-field" placeholder="SSID" aria-label="SSID" />
          <input v-model="wifi.psk" class="md-field" type="password" placeholder="WPA2 口令（8–63）" aria-label="WiFi 口令" />
          <input v-model="wifi.country" class="md-field" maxlength="2" aria-label="国家码" />
          <button class="md-btn" :disabled="!wifi.ssid || !wifi.psk" @click="makeWifi">生成</button>
        </div>
        <p class="md-muted small">口令只在这次请求里用，不落库也不进审计。</p>
        <pre v-if="wifiOut" class="conf">{{ wifiOut.content }}</pre>
      </div>

      <div class="links">
        <a class="md-btn md-btn--outline" href="/api/v1/ca.crt" target="_blank" rel="noopener">下载 CA</a>
        <a class="md-btn md-btn--outline" href="/api/v1/crl.pem" target="_blank" rel="noopener">下载 CRL</a>
        <button class="md-btn md-btn--outline" @click="wifiOpen = !wifiOpen">WiFi 配置</button>
      </div>
      <p class="md-muted small hint">
        证书 365 天有效，到期前 30 天标红；续期由终端提交 CSR 调 /devices/{id}/renew，边不代签。
      </p>
    </section>
  </div>

  <section class="md-card codes">
    <div class="section-head">
      <h2>最近的配对码</h2>
      <span class="md-muted">{{ codes.length }} 个</span>
    </div>
    <div class="md-list">
      <div v-for="c in codes.slice(0, 5)" :key="c.code" class="md-list-row">
        <div class="md-grow">
          <div class="md-mono code">{{ c.code }}</div>
          <div class="md-muted small">{{ c.device_id || '—' }} · {{ c.attempts }} 次尝试</div>
        </div>
        <span class="md-chip" :class="c.used_at ? 'md-chip--ok' : c.locked_until ? 'md-chip--alert' : 'md-chip--warn'">
          {{ c.used_at ? '已使用' : c.locked_until ? '已锁定' : '待使用' }}
        </span>
      </div>
      <p v-if="!codes.length" class="md-muted">还没有生成过配对码。</p>
    </div>
  </section>
</template>

<style scoped>
.error { color: var(--md-error); margin-bottom: var(--space-3); }
.kpis {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 1px;
  background: var(--md-surface-container-highest); border: 1px solid var(--md-surface-container-highest);
  border-radius: var(--md-shape-md); overflow: hidden; margin-bottom: var(--space-4);
}
.kpi { background: var(--md-surface-container-low); padding: var(--space-3) var(--space-4); }
.label { font: var(--md-label-medium); color: var(--md-on-surface-variant); }
.value { font: var(--md-headline-small); }
.note { font: var(--md-body-small); color: var(--md-on-surface-variant); }
.duo {
  display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: var(--space-4); align-items: stretch;
}
.section-head {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: var(--space-3); gap: var(--space-3);
}
.pair { display: flex; gap: var(--space-2); margin-top: var(--space-4); flex-wrap: wrap; }
.pair .md-field { flex: 1; min-width: 160px; }
.links { display: flex; gap: var(--space-2); margin-top: var(--space-4); flex-wrap: wrap; }
.hint { margin-top: var(--space-3); font: var(--md-body-small); }
.codes { margin-top: var(--space-4); }
.code { font-size: 15px; letter-spacing: 0.08em; }
.wifi { margin-top: var(--space-4); border-top: 1px solid var(--md-surface-container-highest); padding-top: var(--space-3); }
.wifi-grid { display: flex; gap: var(--space-2); flex-wrap: wrap; margin-top: var(--space-2); }
.wifi-grid .md-field { flex: 1; min-width: 120px; }
.conf {
  margin-top: var(--space-3); padding: var(--space-3);
  background: var(--md-surface-container-high); border-radius: var(--md-shape-xs);
  font: var(--md-body-small); white-space: pre-wrap; overflow-wrap: anywhere;
}
.small { font: var(--md-body-small); }
@media (max-width: 900px) {
  .duo { grid-template-columns: minmax(0, 1fr); }
}
</style>
