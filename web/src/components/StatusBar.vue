<script setup>
/**
 * 首屏第一块：现在有没有事。颜色只是辅助，结论用文字说清楚。
 */
const props = defineProps({
  status: { type: Object, default: () => ({}) },
  title: { type: String, default: '' },
  sub: { type: String, default: '' },
})


</script>

<template>
  <section class="status" :class="`status--${status.level || 'ok'}`" aria-live="polite">
    <span class="status-icon" aria-hidden="true">
      <svg v-if="(status.level || 'ok') === 'ok'" viewBox="0 0 16 16" width="14" height="14">
        <path d="M3 8.5l3.2 3.2L13 5" fill="none" stroke="currentColor"
              stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      <span v-else>!</span>
    </span>

    <div class="status-text">
      <h1>{{ title }}</h1>
      <p class="status-sub">{{ sub }}</p>
    </div>

    <div class="status-facts">
      <span v-if="status.critical" class="sev-tag sev-tag--critical">
        严重 {{ status.critical }}
      </span>
      <span v-if="status.notice" class="sev-tag sev-tag--notice">
        注意 {{ status.notice }}
      </span>
      <span v-if="status.acked" class="sev-tag sev-tag--idle">已确认 {{ status.acked }}</span>
      <span v-if="status.muted" class="sev-tag sev-tag--idle">已静音 {{ status.muted }}</span>
      <span v-if="status.stale_devices" class="sev-tag sev-tag--critical">
        掉线 {{ status.stale_devices }}
      </span>
      <span v-if="status.stale_edges" class="sev-tag sev-tag--critical">
        掉线 {{ status.stale_edges }}
      </span>
      <slot name="actions" />
    </div>
  </section>
</template>

<style scoped>
.status {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  border-radius: var(--md-shape-lg);
  border: 1px solid var(--md-card-border);
  border-left-width: 4px;
  background: var(--md-card-bg);
}
.status--ok {
  border-left-color: var(--md-outline-variant);
}
.status--notice {
  border-left-color: var(--md-notice);
}
.status--critical {
  border-left-color: var(--md-critical);
  background: color-mix(in srgb, var(--md-critical-container) 40%, var(--md-card-bg));
}

.status-icon {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  font: var(--md-label-large);
  flex: none;
  margin-top: 2px;
  background: var(--md-surface-container-highest);
  color: var(--md-on-surface-variant);
}
.status--notice .status-icon {
  background: var(--md-notice-container);
  color: var(--md-on-notice-container);
}
.status--critical .status-icon {
  background: var(--md-critical-container);
  color: var(--md-on-critical-container);
}

.status-text {
  flex: 1;
  min-width: 0;
}
.status-text h1 {
  font: var(--md-title-large);
  color: var(--md-on-surface);
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.status-sub {
  margin-top: 2px;
  font: var(--md-body-medium);
  color: var(--md-on-surface-variant);
}

.status-facts {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  justify-content: flex-end;
}

/* 窄屏把计数换到下一行，标题拿到整行宽度 */
@media (max-width: 640px) {
  .status {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
  }
  .status-facts {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
}
</style>
