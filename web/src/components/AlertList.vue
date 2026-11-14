<script setup>
/**
 * 待处理异常。一条 = 一段连续越界的窗口，不是每个窗口一条。
 * 确认只降低视觉优先级；静音必须填理由和有效期，两个动作都写审计。
 */
import { ref } from 'vue'
import { api, fmtTime } from '../api'

const props = defineProps({
  alerts: { type: Array, default: () => [] },
  target: { type: Function, default: (a) => ({ device_id: a.device_id, metric: a.metric, ts_from: a.ts_from }) },
  limit: { type: Number, default: 0 },
})
const emit = defineEmits(['changed'])

const busy = ref('')
const open = ref('')          // 正在填静音理由的那条
const reason = ref('')
const hours = ref(8)
const error = ref('')

const DURATIONS = [
  { h: 1, label: '1 小时' },
  { h: 8, label: '8 小时' },
  { h: 24, label: '1 天' },
  { h: 168, label: '7 天' },
]

const key = (a) => a.alert_key || `${a.device_id}:${a.metric}:${a.ts_from}`
const rows = () => (props.limit ? props.alerts.slice(0, props.limit) : props.alerts)

function ago(ms) {
  if (!ms) return '没有上报过'
  const mins = Math.max(0, Math.round((Date.now() - ms) / 60000))
  if (mins < 60) return `${mins} 分钟前上报`
  if (mins < 48 * 60) return `${Math.round(mins / 60)} 小时前上报`
  return `${Math.round(mins / 1440)} 天前上报`
}

function detail(a) {
  if (a.kind === 'stale') return `最后${ago(a.last_seen || a.ts_from)}`
  const span = a.windows > 1 ? `${a.windows} 窗连续` : '单窗'
  return `${span}，|z| ${Math.abs(a.max_z ?? a.z ?? 0).toFixed(1)}`
}

function span(a) {
  if (a.kind === 'stale' || !a.ts_from) return ''
  const from = fmtTime(a.ts_from)
  const to = fmtTime(a.ts_to)
  return from === to ? from : `${from}–${to}`
}

async function ack(a) {
  busy.value = key(a)
  error.value = ''
  try {
    await api('/alerts/ack', { method: 'POST', body: props.target(a) })
    emit('changed')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

function startMute(a) {
  open.value = key(a)
  reason.value = ''
  hours.value = 8
  error.value = ''
}

async function mute(a) {
  if (!reason.value.trim()) {
    error.value = '静音需要填写理由'
    return
  }
  busy.value = key(a)
  try {
    await api('/alerts/mute', {
      method: 'POST',
      body: { ...props.target(a), hours: hours.value, reason: reason.value.trim() },
    })
    open.value = ''
    emit('changed')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}

async function unmute(a) {
  busy.value = key(a)
  try {
    await api('/alerts/unmute', { method: 'POST', body: props.target(a) })
    emit('changed')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <div class="alerts">
    <p v-if="error" class="err">{{ error }}</p>

    <div v-if="!rows().length" class="quiet">
      没有待处理的异常。新窗口连续越界会出现在这里。
    </div>

    <article
      v-for="a in rows()"
      :key="key(a)"
      class="row"
      :class="[`row--${a.severity}`, { 'row--quiet': a.state !== 'pending' }]"
    >
      <span class="sev-tag" :class="`sev-tag--${a.severity}`">
        {{ a.severity === 'critical' ? '严重' : '注意' }}
      </span>

      <div class="body">
        <div class="line">
          <strong>{{ a.label }}</strong>
          <span class="who">{{ a.device_name || a.device_id }}</span>
          <span v-if="a.edge_id && !a.device_id" class="who">{{ a.edge_id }}</span>
          <span v-if="a.state === 'acked'" class="tag-idle">已确认</span>
          <span v-if="a.state === 'muted'" class="tag-idle">已静音</span>
        </div>
        <div class="meta">
          {{ detail(a) }}<template v-if="span(a)">，{{ span(a) }}</template>
        </div>
        <div v-if="a.state === 'muted'" class="meta">
          静音至 {{ fmtTime(a.muted_until) }}，理由：{{ a.mute_reason }}
        </div>

        <div v-if="open === key(a)" class="mute-form">
          <div class="durations" role="group" aria-label="静音时长">
            <button
              v-for="d in DURATIONS"
              :key="d.h"
              type="button"
              class="md-btn md-btn--text"
              :class="{ 'is-on': hours === d.h }"
              :aria-pressed="hours === d.h"
              @click="hours = d.h"
            >{{ d.label }}</button>
          </div>
          <label class="md-field mute-reason">
            <span>理由</span>
            <input
              v-model="reason"
              type="text"
              placeholder="写进审计"
              @keyup.enter="mute(a)"
            />
          </label>
          <button class="md-btn" :disabled="busy === key(a)" @click="mute(a)">静音</button>
          <button class="md-btn md-btn--text" @click="open = ''">取消</button>
        </div>
      </div>

      <div v-if="open !== key(a)" class="acts">
        <button
          v-if="a.state === 'pending'"
          class="md-btn md-btn--text"
          :disabled="busy === key(a)"
          @click="ack(a)"
        >确认</button>
        <button
          v-if="a.state !== 'muted'"
          class="md-btn md-btn--text"
          @click="startMute(a)"
        >静音</button>
        <button
          v-else
          class="md-btn md-btn--text"
          :disabled="busy === key(a)"
          @click="unmute(a)"
        >取消静音</button>
      </div>
    </article>
  </div>
</template>

<style scoped>
.err {
  color: var(--md-error);
  font: var(--md-body-medium);
  margin-bottom: var(--space-2);
}
.quiet {
  font: var(--md-body-medium);
  color: var(--md-on-surface-variant);
  padding: var(--space-3) 0;
}

.row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  border-top: 1px solid var(--md-outline-variant);
}
.row:first-of-type {
  border-top: 0;
  padding-top: var(--space-1);
}
.row--quiet {
  opacity: 0.72;
}

.body {
  flex: 1;
  min-width: 0;
}
.line {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  flex-wrap: wrap;
}
.line strong {
  font: var(--md-title-small);
  color: var(--md-on-surface);
}
.who {
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}
.meta {
  margin-top: 2px;
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}

.tag-idle {
  font: var(--md-label-small);
  color: var(--md-on-surface-variant);
  background: var(--md-surface-container-highest);
  border-radius: var(--md-shape-full);
  padding: 1px 8px;
}

.acts {
  display: flex;
  gap: var(--space-1);
  flex: none;
}

.mute-form {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-top: var(--space-2);
}
.durations {
  display: flex;
  gap: 2px;
}
.durations .is-on {
  background: var(--md-secondary-container);
  color: var(--md-on-secondary-container);
}
.mute-form .md-field {
  min-width: 220px;
  flex: 1;
}
.mute-reason > span {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
