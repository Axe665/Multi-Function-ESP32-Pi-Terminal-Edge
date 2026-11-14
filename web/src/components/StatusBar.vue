<script setup>
/**
 * 首屏第一块：现在有没有事。颜色只是辅助，结论用文字说清楚。
 * 标题是结论本身，不占 heading 层级（页面名在顶栏 h1）。
 */
defineProps({
  status: { type: Object, default: () => ({}) },
  title: { type: String, default: '' },
  sub: { type: String, default: '' },
})
</script>

<template>
  <section class="status" :class="`status--${status.level || 'ok'}`" aria-live="polite">
    <span class="status-icon" aria-hidden="true">
      <svg v-if="(status.level || 'ok') === 'ok'" viewBox="0 0 16 16" width="16" height="16">
        <path d="M3 8.5l3.2 3.2L13 5" fill="none" stroke="currentColor"
              stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      <span v-else>!</span>
    </span>

    <div class="status-text">
      <p class="status-title">{{ title }}</p>
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
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-5);
  border-radius: var(--md-shape-lg);
  background: var(--md-surface-container-low);
  grid-column: span 12;
}
.status--notice {
  background: var(--md-notice-container);
}
.status--critical {
  background: var(--md-critical-container);
}

.status-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: var(--md-shape-full);
  font: var(--md-title-medium);
  flex: none;
  background: var(--md-primary-container);
  color: var(--md-on-primary-container);
}
.status--notice .status-icon {
  background: var(--md-notice);
  color: var(--md-on-primary);
}
.status--critical .status-icon {
  background: var(--md-critical);
  color: var(--md-on-error);
}

.status-text {
  flex: 1;
  min-width: 0;
}
.status-title {
  font: var(--md-headline-small);
  color: var(--md-on-surface);
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  flex-wrap: wrap;
}
.status-sub {
  margin-top: 2px;
  font: var(--md-body-small);
  color: var(--md-on-surface-variant);
}
.status--notice .status-sub,
.status--critical .status-sub {
  color: color-mix(in srgb, var(--md-on-surface) 70%, transparent);
}

.status-facts {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  justify-content: flex-end;
}
</style>
