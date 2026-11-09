<script setup>
defineProps({ variant: { type: String, default: 'edge' } })
</script>

<template>
  <svg class="brand-mark" viewBox="0 0 32 32" role="img" aria-label="Modular Terminal">
    <rect width="32" height="32" rx="8" class="tile" />
    <path d="M7.5 24V9.5L16 18l8.5-8.5V24" class="stroke" />
    <g v-if="variant === 'cloud'">
      <circle cx="16" cy="18" r="3.4" class="hub" />
      <circle cx="16" cy="18" r="1.3" class="hub-core" />
    </g>
    <g v-else class="nodes">
      <circle cx="7.5" cy="9.5" r="2.2" />
      <circle cx="16" cy="18" r="2.2" />
      <circle cx="24.5" cy="9.5" r="2.2" />
    </g>
  </svg>
</template>

<style scoped>
.brand-mark {
  width: 28px;
  height: 28px;
  display: block;
  flex: none;
}
.tile {
  fill: var(--md-primary);
}
.stroke {
  fill: none;
  stroke: var(--md-on-primary);
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.nodes circle {
  fill: var(--md-on-primary);
  stroke: var(--md-primary);
  stroke-width: 1.1;
}
.hub {
  fill: var(--md-primary);
  stroke: var(--md-on-primary);
  stroke-width: 1.8;
}
.hub-core {
  fill: var(--md-on-primary);
}
</style>
