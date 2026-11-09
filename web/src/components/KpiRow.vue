<script setup>
defineProps({ items: { type: Array, default: () => [] } })
</script>

<template>
  <section class="kpis" aria-label="关键指标">
    <div v-for="k in items" :key="k.label" class="kpi">
      <div class="label">{{ k.label }}</div>
      <div class="value">{{ k.value }}<span v-if="k.unit" class="unit">{{ k.unit }}</span></div>
      <div class="note">{{ k.note }}</div>
    </div>
  </section>
</template>

<style scoped>
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1px;
  background: var(--md-surface-container-highest);
  border: 1px solid var(--md-surface-container-highest);
  border-radius: var(--md-shape-md);
  overflow: hidden;
  margin-bottom: var(--space-4);
}
.kpi {
  background: var(--md-surface-container-low);
  padding: var(--space-3) var(--space-4);
}
.label {
  font: var(--md-label-medium);
  color: var(--md-on-surface-variant);
}
.value {
  margin-top: 2px;
  font: var(--md-headline-small);
  color: var(--md-on-surface);
}
.unit {
  margin-left: 3px;
  font: var(--md-body-medium);
  color: var(--md-on-surface-variant);
}
.note {
  margin-top: 2px;
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}
</style>
