<script setup>
defineProps({ items: { type: Array, default: () => [] } })

// 7 点小趋势：0–100 的百分比直接映射到 18px 高的折线
const sparkPoints = (arr) =>
  arr.map((v, i) => `${(i / Math.max(1, arr.length - 1)) * 58 + 1},${16 - (v / 100) * 14}`).join(' ')

const arrow = (v) => (v > 0 ? '▲' : v < 0 ? '▼' : '—')
</script>

<template>
  <section class="kpis" aria-label="关键指标">
    <div v-for="k in items" :key="k.label" class="kpi">
      <div class="label">{{ k.label }}</div>
      <div class="value-row">
        <span class="value">{{ k.value }}<span v-if="k.unit" class="unit">{{ k.unit }}</span></span>
        <svg v-if="k.spark?.length > 1" class="spark" viewBox="0 0 60 18" aria-hidden="true">
          <polyline :points="sparkPoints(k.spark)" />
        </svg>
        <span v-if="k.delta !== undefined && k.delta !== null" class="delta">
          {{ arrow(k.delta) }} {{ Math.abs(k.delta) }}%
          <span class="delta-note">{{ k.deltaLabel || 'vs 前 24 h' }}</span>
        </span>
      </div>
      <div class="note">{{ k.note }}</div>
    </div>
  </section>
</template>

<style scoped>
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  background: var(--md-card-bg);
  border: 1px solid var(--md-card-border);
  border-radius: var(--md-shape-md);
  overflow: hidden;
  grid-column: span 12;
}
.kpi {
  padding: var(--space-3) var(--space-4);
  min-width: 0;
}
.kpi + .kpi {
  border-left: 1px solid var(--md-outline-variant);
}
.label {
  font: var(--md-label-medium);
  color: var(--md-on-surface-variant);
}
.value-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  margin-top: 2px;
}
.value {
  font: var(--md-headline-medium);
  color: var(--md-on-surface);
  letter-spacing: -0.01em;
}
.unit {
  margin-left: 3px;
  font: var(--md-body-medium);
  color: var(--md-on-surface-variant);
}
.spark {
  width: 60px;
  height: 18px;
  flex: none;
  align-self: center;
}
.spark polyline {
  fill: none;
  stroke: var(--md-primary);
  stroke-width: 1.5;
  stroke-linejoin: round;
  stroke-linecap: round;
}
/* 变化量只做提示，不抢颜色：方向靠箭头，颜色留给告警 */
.delta {
  margin-left: auto;
  font: var(--md-label-medium);
  color: var(--md-on-surface-variant);
  white-space: nowrap;
}
.delta-note {
  margin-left: 2px;
  font: var(--md-label-small);
  color: color-mix(in srgb, var(--md-on-surface-variant) 72%, transparent);
}
.note {
  margin-top: 2px;
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}
</style>
